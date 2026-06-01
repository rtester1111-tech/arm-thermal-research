# Makefile for ARM brightness kernels
# Cross-compile for AArch64 on x86 host
#
# Usage:
#   make all          -> build all three variants
#   make run_scalar   -> run scalar benchmark
#   make run_neon     -> run NEON benchmark
#   make run_sve2     -> run SVE2 benchmark (requires SVE2 hardware)
#   make compare      -> run all three and show comparison

CC_ARM  = aarch64-linux-gnu-gcc
CC_HOST = gcc
CFLAGS_COMMON = -O3 -Wall -Wextra -static -mbranch-protection=none

# AArch64 targets
CFLAGS_SCALAR = $(CFLAGS_COMMON) -march=armv8-a
CFLAGS_NEON   = $(CFLAGS_COMMON) -march=armv8-a+simd
CFLAGS_SVE2   = $(CFLAGS_COMMON) -march=armv8.2-a+sve2

all: scalar.aarch64 neon.aarch64 sve2.aarch64 idct_scalar.aarch64 idct_neon.aarch64 idct_sve2.aarch64

scalar.aarch64: brightness_scalar.c
	$(CC_ARM) $(CFLAGS_SCALAR) -o $@ $< -lm

neon.aarch64: brightness_neon.c
	$(CC_ARM) $(CFLAGS_NEON) -o $@ $< -lm

sve2.aarch64: brightness_sve2.c
	$(CC_ARM) $(CFLAGS_SVE2) -o $@ $< -lm

idct_scalar.aarch64: idct_scalar.c
	$(CC_ARM) $(CFLAGS_SCALAR) -o $@ $< -lm

idct_neon.aarch64: idct_neon.c
	$(CC_ARM) $(CFLAGS_NEON) -o $@ $< -lm

idct_sve2.aarch64: idct_sve2.c
	$(CC_ARM) $(CFLAGS_SVE2) -o $@ $< -lm

# Run with QEMU user-mode emulation
run_scalar: scalar.aarch64
	qemu-aarch64 ./scalar.aarch64

run_neon: neon.aarch64
	qemu-aarch64 ./neon.aarch64

run_sve2: sve2.aarch64
	# SVE2 with 256-bit vector length simulation
	qemu-aarch64 -cpu max,sve256=on ./sve2.aarch64

run_idct: idct_scalar.aarch64 idct_neon.aarch64 idct_sve2.aarch64
	@echo "--- IDCT Scalar (baseline) ---"
	@qemu-aarch64 ./idct_scalar.aarch64
	@echo "--- IDCT NEON 128-bit ---"
	@qemu-aarch64 ./idct_neon.aarch64
	@echo "--- IDCT SVE2 256-bit ---"
	@qemu-aarch64 -cpu max,sve256=on ./idct_sve2.aarch64

compare: all
	@echo "======================================"
	@echo " Phase 1: SIMD Performance Comparison (Brightness)"
	@echo "======================================"
	@echo "--- Scalar (baseline) ---"
	@qemu-aarch64 ./scalar.aarch64
	@echo "--- NEON 128-bit ---"
	@qemu-aarch64 ./neon.aarch64
	@echo "--- SVE2 256-bit ---"
	@qemu-aarch64 -cpu max,sve256=on ./sve2.aarch64
	@echo "======================================"
	@echo " Phase 1.5: Compute-Intensive 8x8 2D IDCT Performance Comparison"
	@echo "======================================"
	@echo "--- IDCT Scalar (baseline) ---"
	@qemu-aarch64 ./idct_scalar.aarch64
	@echo "--- IDCT NEON 128-bit ---"
	@qemu-aarch64 ./idct_neon.aarch64
	@echo "--- IDCT SVE2 256-bit ---"
	@qemu-aarch64 -cpu max,sve256=on ./idct_sve2.aarch64
	@echo "======================================"

clean:
	rm -f *.aarch64

.PHONY: all run_scalar run_neon run_sve2 run_idct compare clean

