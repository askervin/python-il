# il - inline assembly in Python 3

Examples
--------

1. Decorator API - simple

```python
import il
import ctypes

@il.asm
def add_ints(rdi=ctypes.c_int32, rsi=ctypes.c_int32):
    """
    # return sum of two 32-bit integers
    # 64-bit Linux/MacOS call convention
    #
    .intel_syntax noprefix
    mov rax, 0
    mov eax, edi
    add eax, esi
    ret
    """
    return ctypes.c_int32

print(add_ints(43, -1))
```

2. Function API - powerful

```python
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
```

Dependencies
------------

- If object code is available: no dependencies outside Python standard
  library. `ctypes` from the standard library is needed for loading
  and running object code.

- If object code is not available: `as` and `objcopy` (from
  `binutils`) are required for compiling assembly.

Install
-------

From PyPI:

```sh
$ pip3 install il
```

From source tree:

```sh
$ sudo python3 setup.py install
```

Library API documentation and call conventions
----------------------------------------------

```sh
$ python3 -c 'import il; help(il)'
```

How it works
------------

- Assume that `mylib.py` contains inlined assembly. By default, `il`
  looks for object code from `mylib.py.il`. If found, that code will
  be executed when inlined functions are called.

- If object code is not found, `il` uses binutils: `as` (assembler)
  and `objcopy` to compile the assembly on-the-fly and extract object
  code from the result. Object code is saved to `mylib.py.il` for
  later use.

- Note: `il` does not link object code before running it.

- You can view contents of `mylib.py.il` using `il`:
  ```sh
  $ python3 -c 'import il; print(il.dump_lib("mylib.py.il", disasm=False))'
  ```
  (Use `disasm=True` to disassemble the code in the dump. Requires `objdump`.)

Debugging inlined assembly
--------------------------

1. Import the library, print the pid of the Python process and the
   address of the function that you want to debug:
   ```python
   >>> import mylib
   >>> import os
   >>> os.getpid()
   12345
   >>> print(mylib.myfunc.il_addr)
   21954560
   ```

2. Attach GDB to the Python process, set a breakpoint to the address
   and let the Python process continue.
   ```bash
   $ gdb -p 12345
   (gdb) layout asm
   (gdb) break *21954560
   (gdb) cont
   ```

3. Call the function in Python
   ```python
   >>> mylib.myfunc()
   ```

4. Now you can step assembly instructions and see register values in
   GDB:

   ```bash
   (gdb) ni
   (gdb) info registers
   ```
