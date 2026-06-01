#!/bin/bash
# ============================================================
# run_atomic_dynamic.sh — Generate a dynamic checkpoint
# ============================================================
# This script boots Linux with AtomicSimpleCPU and runs
# fs_boot_dynamic.rcS to create a clean checkpoint that
# waits for external scripts upon resumption.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

GEM5_ROOT="${GEM5_ROOT:-${HOME}/gem5}"
GEM5_OPT="${GEM5_ROOT}/build/ARM/gem5.opt"
FS_BIGLITTLE="${GEM5_ROOT}/configs/example/arm/fs_bigLITTLE.py"
KERNEL="$(cd "${PROJECT_DIR}/.." && pwd)/linux-stable/vmlinux"
DISK="${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0"
BOOTLOADER="${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0"

OUTDIR_ATOMIC="${PROJECT_DIR}/m5out_fs_atomic_dynamic"
BOOTSCRIPT="${PROJECT_DIR}/scripts/fs_boot_dynamic.rcS"

echo "=== Phase 7: Atomic CPU Dynamic Checkpoint Gen ==="
echo "  Output: $OUTDIR_ATOMIC"
echo ""

mkdir -p "$OUTDIR_ATOMIC"

"$GEM5_OPT" \
    --outdir="$OUTDIR_ATOMIC" \
    "$FS_BIGLITTLE" \
    --kernel="$KERNEL" \
    --disk="$DISK" \
    --bootloader="$BOOTLOADER" \
    --bootscript="$BOOTSCRIPT" \
    --cpu-type=atomic \
    --big-cpus=1 \
    --little-cpus=1 \
    --mem-size=2GiB \
    --machine-type=VExpress_GEM5_Foundation \
    2>&1 | tee "${OUTDIR_ATOMIC}/console.log"

echo ""
echo "=== Checkpoint Generation Finished ==="
