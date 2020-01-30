# il - inline assembly in Python 3

Example on `il` decorator API
-----------------------------

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

Dependencies
------------

- No dependencies outside Python standard library if object code ships
  with Python file that includes inlined assembly (FILE.py.il).
  `ctypes` from the standard library is needed for loading and running
  object code.

- `as` and `objcopy` (from `binutils`) are required for compiling
  assembly if object code is not already available.

Install
-------
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
   $ python3
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
