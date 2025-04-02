objdump-vector:
  objdump -d ./vector.so | rg 'vmovaps|vaddps|vmulps|addps|mulps' | wc -l

