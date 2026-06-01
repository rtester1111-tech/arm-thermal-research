# Makefile for stress_lcg — AArch64 compute-stress workload
#
# Usage:
#   make                      # cross-compile (requires aarch64-linux-gnu-gcc)
#   make STATIC=1             # produce fully static binary
#   make native               # compile native x86_64 for local smoke-test
#   make clean

CC_CROSS  ?= aarch64-linux-gnu-gcc
CC_NATIVE ?= gcc
CFLAGS    := -O2 -Wall

ifdef STATIC
CFLAGS += -static
endif

TARGET     := stress_lcg
SRC        := stress_lcg.c

.PHONY: all native clean

all: $(TARGET).aarch64

$(TARGET).aarch64: $(SRC)
	$(CC_CROSS) $(CFLAGS) -o $@ $<
	@file $@ || true

native: $(SRC)
	$(CC_NATIVE) $(CFLAGS) -o $(TARGET) $<

clean:
	rm -f $(TARGET) $(TARGET).aarch64

# Install into a mounted gem5 disk image:
#   sudo mount -o loop <disk.img> <mount-point>
#   sudo cp stress_lcg.aarch64 <mount-point>/root/stress_lcg
#   sudo chmod +x <mount-point>/root/stress_lcg
#   sudo umount <mount-point>
