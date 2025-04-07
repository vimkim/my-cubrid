objdump-vector:
    # objdump -d -M intel vector.so | grep -E 'addps|mulps|vmov|vadd|vmul|vfma|vxor' | wc -l
    objdump -d -M intel vector.so | rg 'addps|mulps|vmov|vadd|vmul|vfma|vxor' | wc -l

objdump-libcubrid:
    # objdump -d ./vector.so | rg 'vmovaps|vaddps|vmulps|addps|mulps' | wc -l
    objdump -d -M intel $CUBRID/lib/libcubrid.so | rg 'addps|mulps|vmov|vadd|vmul|vfma|vxor' | wc -l
