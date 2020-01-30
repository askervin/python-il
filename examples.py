import ctypes
import os

import il

# Example: Decorator API, 64-bit Linux/MacOS call convention
@il.asm
def add_ints(rdi=ctypes.c_int, rsi=ctypes.c_int):
    """
    # returns sum of two parameters
    #
    .intel_syntax noprefix
    xor rax, rax
    mov eax, edi
    add eax, esi
    ret
    """
    return ctypes.c_int

# Example: Function API, 64-bit Windows call convention
add_ints_win = il.def_asm(
    name="add_ints_win",

    prototype=ctypes.CFUNCTYPE(ctypes.c_int32,  # return value (eax)
                               ctypes.c_int32,  # 1st param (ecx)
                               ctypes.c_int32), # 2nd param (edx)

    code="""
    # returns sum of two parameters
    #
    .intel_syntax noprefix
    xor rax, rax
    mov eax, ecx
    add eax, edx
    ret
    """)

# Example: Returning an array from asm
@il.asm
def cpuid(rdi=ctypes.c_int, rsi=ctypes.c_int, rdx=ctypes.c_void_p):
    """
    # Function/instruction parameter mapping:
    #
    # cpuid(input-to-CPUID int32 EAX,
    #       input-to-CPUID int32 ECX,
    #       output-from-CPUID int32[4] EAX_EBX_ECX_EDX)
    #
    .intel_syntax noprefix
    push rbx
    mov r8, rdx
    mov eax, edi
    mov ecx, esi
    cpuid
    mov [r8], eax
    mov [r8+4], ebx
    mov [r8+8], ecx
    mov [r8+12], edx
    pop rbx
    ret
    """
    return ctypes.c_int

@il.asm
def cpuid_win(rcx=ctypes.c_int, rdx=ctypes.c_int, r8=ctypes.c_void_p):
    """
    # Function/instruction parameter mapping:
    #
    # cpuid(input-to-CPUID int32 EAX,
    #       input-to-CPUID int32 ECX,
    #       output-from-CPUID int32[4] EAX_EBX_ECX_EDX)
    #
    .intel_syntax noprefix
    push rbx
    mov eax, ecx
    mov ecx, edx
    cpuid
    mov [r8], eax
    mov [r8+4], ebx
    mov [r8+8], ecx
    mov [r8+12], edx
    pop rbx
    ret
    """
    return ctypes.c_int

if __name__ == "__main__":
    # reserve array: int32[4] for cpuid's output (EAX, EBX, ECX, EDX)
    abcd = (ctypes.c_int32 * 4)(0)

    if os.name != "nt":
        print("add_ints(1, -2) == ", add_ints(1, -2))
        highest_leaf = cpuid(0, 0, abcd)
    else:
        print("add_ints_win(1, -2) == ", add_ints_win(1, -2))
        highest_leaf = cpuid_win(0, 0, abcd)

    # manufacturer id
    manuf = ctypes.create_string_buffer(4*4+1)
    ctypes.memmove(ctypes.addressof(manuf),   ctypes.addressof(abcd)+4,  4)
    ctypes.memmove(ctypes.addressof(manuf)+4, ctypes.addressof(abcd)+12, 4)
    ctypes.memmove(ctypes.addressof(manuf)+8, ctypes.addressof(abcd)+8,  4)

    print("CPUID: highest leaf: %x, manufacturer id: %s" %
          (highest_leaf, manuf.value.decode("utf-8")))
