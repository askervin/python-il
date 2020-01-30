# Inline assembly in Python
#
# Copyright (c) 2020 Antti Kervinen <antti.kervinen@gmail.com>
#
# License (MIT):
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

'''Inline assembly in Python

Implementing a Python function in assembly
------------------------------------------

The il library API provides two ways of inlining assembly.

1. Decorator `@il.asm` uses Python function definition. Assembly
   source code is in the docstring. Parameter and return value types
   are defined with function parameters and returned type. Example:

   @il.asm
   def add_ints(edi=ctypes.c_int32, esi=ctypes.c_int32):
       """
       .intel_syntax noprefix
       mov rax, 0
       mov eax, edi
       add eax, esi
       ret
       """
       return ctypes.c_int32

   print(add_ints(43, -1))

2. Function `il.def_asm(name, prototype, code)` is more flexible than
   the decorator. It enables using templated assembly source code and
   reading it from a file, for instance. Parameter and return value
   types are defined using the prototype parameter. Example:

   add_ints = il.def_asm(
        name="add_ints",
        prototype=ctypes.CFUNCTYPE(ctypes.c_int32,  # return value (eax)
                                   ctypes.c_int32,  # 1st param (edi)
                                   ctypes.c_int32), # 2nd param (esi)
        code="""
        .intel_syntax noprefix
        mov rax, 0
        mov eax, edi
        add eax, esi
        ret
        """)

   print(add_ints(43, -1))

Note that call convention in Linux/MacOS/FreeBSD differs from Windows:
function parameters are in different registers and functions need
to save/restore (push/pop) different set of registers if they are used.
See help(il.asm) for more information.

Compiling assembly
------------------

The il library does not use compiler if object code is already
available for the source code. If it is not, il uses the GNU assembler
and objcopy (from binutils) to compile and extract object code. The
object code is saved to LIBNAME.py.il (zipped pickled dictionary) for
later use by default, but loading and storing to Python dictionaries
and other filepaths is supported, too. `il.dump_lib()` helps viewing
`LIBNAME.py.il` file contents.

Note that the il library does not link object code before running it.

Loading and running
-------------------

The il library loads and runs object code on Linux/MacOS/FreeBSD and
Windows platforms.

'''

import atexit
import pickle
import ctypes
import hashlib
import inspect
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zlib

platform_name = os.name
platform_arch = "x86-%s" % (ctypes.sizeof(ctypes.c_void_p)*8,)

_g_tmpdir = None
def _tmpdir():
    global _g_tmpdir
    if _g_tmpdir:
        return _g_tmpdir
    _g_tmpdir = tempfile.mkdtemp(prefix="python-il.%s." % (os.getpid(),))
    atexit.register(_rmtempdir)
    return _g_tmpdir

def _rmtempdir():
    shutil.rmtree(_g_tmpdir)

########################################################################
# Make object code executable

if platform_name == "posix":
    def _executable_addr(code):
        """Copy code to executable memory location, return the address.
        """
        valloc = ctypes.pythonapi.valloc
        valloc.restype = ctypes.c_void_p
        valloc.argtypes = [ctypes.c_ulong]

        mprotect = ctypes.pythonapi.mprotect
        mprotect.restype = ctypes.c_int
        mprotect.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]

        PROT_READ = 1
        PROT_WRITE = 2
        PROT_EXEC = 4

        buf_p = ctypes.c_char_p(code)
        size = len(code)
        addr = valloc(size)

        if not addr:
            raise MemoryError("Failed to allocate memory")

        ctypes.memmove(addr, buf_p, size)
        if ctypes.pythonapi.mprotect(addr, len(code),
                                     PROT_READ | PROT_WRITE | PROT_EXEC):
            raise SystemError("Failed to make memory executable")
        return addr

elif platform_name == "nt": # Windows
    def _executable_addr(code):
        """Copy code to executable memory location, return the address.
        """
        VirtualAlloc = ctypes.windll.kernel32.VirtualAlloc
        VirtualAlloc.restype = ctypes.c_void_p
        VirtualAlloc.argtypes = [
            ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_long]

        NULL = 0x0
        MEM_COMMIT = 0x00001000
        PAGE_EXECUTE_READWRITE = 0x40

        buf_p = ctypes.c_char_p(code)
        size = len(code)
        addr = VirtualAlloc(NULL, size, MEM_COMMIT,
                            PAGE_EXECUTE_READWRITE)
        if not addr:
            raise MemoryError("Failed to allocate executable memory")

        ctypes.memmove(addr, buf_p, len(code))
        return addr

########################################################################
# Object code library handling

def _lib_filename():
    """Returns default il library filename"""
    # The name is FILENAME.il where FILENAME is the first Python
    # code filename (outside il.py) from which this code is called.
    f = inspect.currentframe().f_back
    while os.path.basename(f.f_code.co_filename) == "il.py":
        f = f.f_back
    lib_filename = f.f_code.co_filename + ".il"
    return lib_filename

_g_loaded_libs = {}
def _load_lib(libspec):
    """Load il library according to the libspec. Returns the library (dict).

    If libspec is None, load from the default il library name.

    If libspec is a dictionary, use that as a il library directly.

    If libspec is a filename, load the library from the file.
    """
    if libspec == None:
        libspec = _lib_filename()
    if isinstance(libspec, dict):
        lib = libspec
    elif isinstance(libspec, str):
        # libspec is a filename
        if libspec in _g_loaded_libs:
            lib = _g_loaded_libs[libspec]
        else:
            if os.access(libspec, os.R_OK):
                try:
                    lib = pickle.loads(zlib.decompress(open(libspec, "rb").read()))
                    lib["il-lib-filename"] = libspec
                except zlib.error:
                    raise ValueError(('invalid il library "%s", '
                                     'zlib decompress failed') % (libspec,))
                except pickle.UnpicklingError:
                    raise ValueError(('invalid il library "%s", '
                                      'unpickling failed') % (libspec,))
            else:
                lib = {}
                # create a writable file
                try:
                    open(libspec, "w").close()
                    lib["il-lib-filename"] = libspec
                except OSError:
                    pass
            _g_loaded_libs[libspec] = lib
    else:
        raise TypeError("invalid libspec type (%s), string or dict expected")
    return lib

def _lib_fetch_exec(lib, key, prototype):
    d = lib.get(key, None)
    if not d:
        func_handle = None
    else:
        func_code_p = _executable_addr(d["code"])
        func_handle = ctypes.cast(func_code_p, prototype)
        func_handle.il_addr = func_code_p
    return func_handle

def _save_lib(lib, lib_filename):
    if lib_filename == None:
        if "il-lib-filename" in lib:
            lib_filename = lib["il-lib-filename"]
        else:
            lib_filename = _lib_filename()
    elif isinstance(lib_filename, dict):
        if "il-lib-filename" in lib_filename:
            lib_filename = lib_filename["il-lib-filename"]
        else:
            return # skip save
    libdata = zlib.compress(pickle.dumps(lib))
    if isinstance(lib_filename, str):
        if os.access(lib_filename, os.W_OK):
            try:
                open(lib_filename, "wb").write(libdata)
            except OSError as e:
                raise ValueError('saving library "%s" failed: %s' %
                                 (lib_filename, e))
    elif hasattr(lib_filename, "write"):
        lib_filename.write(libdata)
    else:
        raise TypeError('invalid lib_filename "%s"' % (lib_filename,))
    _g_loaded_libs[lib_filename] = lib

def dump_lib(lib_filename, disasm=None):
    """Returns library dump as a string

    Parameters:
      lib_filename (string):
            name of the il precompiled library.
            Example: "mylib.py.il"

      disasm (bool, optional):
            True if dump includes disassembled functions (needs objdump)
            The default is False.
    """
    out_list = []
    lib = _load_lib(lib_filename)
    if disasm:
        binfile = os.path.join(_tmpdir(), "dump_lib.bin")
        disasm_cmd = ["objdump", "-b", "binary", "-D", "-m", "i386:x86-64", "-M", "intel", binfile]
    for key in sorted(lib.keys()):
        if not key.startswith("il-"):
            _hash = key
            out_list.append(_hash)
            out_list.append("    name: %s" % (lib[key]["name"],))
            out_list.append("    time: %f" % (lib[key]["time"],))
            if disasm and lib[key]:
                out_list.append("    code:")
                objcode = lib[key]["code"]
                open(binfile, "wb").write(objcode)
                out = subprocess.check_output(disasm_cmd)
                data_started = False
                for line in out.decode("utf-8").splitlines():
                    if line.endswith("<.data>:"):
                        data_started = True
                    elif data_started:
                        out_list.append(line)
                os.remove(binfile)
            else:
                out_list.append("    code: %s" % (repr(lib[key]["code"]),))
        else:
            out_list.append("%s:\n    %s" % (key, lib[key]))
    return "\n".join(out_list)

########################################################################
# Convert inlined assembly to callable Python functions

def _asm_pick_bin(object_filename):
    out_filename = os.path.join(_tmpdir(), "bin")
    try:
        picker = subprocess.Popen(
            ["objcopy", "-Obinary", "-j.text",
             object_filename, out_filename],
            shell=False)
        picker.wait()
        binary = open(out_filename, "rb").read()
    finally:
        try:
            os.remove(out_filename)
        except IOError:
            pass
    return binary

def _asm_compile(code, compiler_opts):
    """returns executable code as string"""
    out_filename = os.path.join(_tmpdir(), "asmout")
    compiler_command = ["as", "-o", out_filename] + list(compiler_opts)
    try:
        compiler = subprocess.Popen(
            compiler_command,
            shell=False,
            stdin=subprocess.PIPE)
        compiler.stdin.write(code.encode("utf-8"))
        compiler.stdin.close()
        exit_status = compiler.wait()
        if exit_status:
            return None
        return _asm_pick_bin(out_filename)
    finally:
        try:
            os.remove(out_filename)
        except IOError:
            pass

########################################################################
# Function API

def def_asm(name=None, prototype=None, code="", lib=None, compiler_opts=[]):
    '''Return Python function implemented in assembly

    Parameters:
      name (string):
            save the function to the library with this name

      prototype (ctypes.CFUNCTYPE):
            function prototype that specifices types for
            the return value and parameters. Example:
            return 64-bit integer from a function that takes
            two 32-bit integers as parameters:
            ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int32, ctypes.c_int32)

      code (string):
            assembly source code

      lib (string or dictionary, optional):
            string: the name of the il library file.
            dictionary: use the dictionary as the il library.
            The default is the filename + ".il" of the module in
            which this decorator is used.

      compiler_opts (list of strings, optional):
            options passed to assembly compiler

    See help(il.asm) for call convention.
    '''
    _lib = _load_lib(lib)
    key = hashlib.sha1(code.encode("utf-8")).hexdigest()
    if not key in _lib:
        _lib[key] = {
            'name': name,
            'code': _asm_compile(code, compiler_opts),
            'time': time.time(),
        }
        _save_lib(_lib, lib)
    return _lib_fetch_exec(_lib, key, prototype)

########################################################################
# Decorator API

def asm(func=None, lib=None, compiler_opts=[]):
    '''Decorator for functions with inlined assembly in docstring

    Parameters:
      lib (string or dictionary, optional):
            string: the name of the il library file.
            dictionary: use the dictionary as the il library.
            The default is the filename + ".il" of the module in
            which this decorator is used.

      compiler_opts (list of strings, optional):
            options passed to assembly compiler

    Note the call convention on your platform.

    * System V AMD64 ABI (x86-64 FreeBSD, Linux, macOS, Solaris)
      call:  First integers and pointers in registers
             RDI, RSI, RDX, RCX, R8, R9
             First floating point arguments:
             XMM0, XMM1, ..., XMM7

      return: Integer return values:
             RAX up to 64 bits
             RAX:RDX up to 128 bits
             Float return values:
             XMM0:XMM1 up to 128 bits

      other registers: callee must restore these registers if used:
             RBX, RBP, R12, R13, R14, R15

    * Microsoft x64 (Windows, UEFI):
      call:  First integers and pointers in registers
             RCX, RDX, R8, R9
             First floating point arguments:
             XMM0, XMM1, XMM2, XMM3
             Additional arguments pushed to stack from right to left.

      return: Integer return values:
             RAX up to 64 bits
             Floating point return values:
             XMM0 up to 64 bits.

      other registers: callee must restore these registers if used:
             RBX, RBP, RDI, RSI, RSP, R12, R13, R14, and R15

    Example:

    @il.asm
    def add_ints(rdi=ctypes.c_int, rsi=ctypes.c_int):
        """
        .intel_syntax noprefix
        xor rax, rax
        mov eax, edi
        add eax, esi
        ret
        """
        return ctypes.c_int
    '''
    def _asm_decor(func):
        arg_names = func.__code__.co_varnames
        args = func.__defaults__
        if args == None:
            args = tuple()
        return_value = func()
        asm_code = func.__doc__

        prototype = ctypes.CFUNCTYPE(*((return_value,) + args))
        return def_asm(func.__name__, prototype, asm_code, lib, compiler_opts)
    if func: # called directly without decorator arguments
        return _asm_decor(func)
    else:
        def _new_decorator(func):
            return _asm_decor(func)
        return _new_decorator

########################################################################
# if il.py is executed, help viewing library file contents

if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.access(sys.argv[1], os.R_OK):
        print("Usage: python3 il.py LIBRARY.il")
    print(dump_lib(sys.argv[1],
                   disasm=(os.getenv("IL_DISASM", "") !=  "")))
