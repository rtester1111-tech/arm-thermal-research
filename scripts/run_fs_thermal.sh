#!/bin/bash
# ============================================================
# run_fs_thermal.sh — gem5 FS 熱模擬啟動腳本
# ============================================================
# 使用方法:
#   bash scripts/run_fs_thermal.sh [atomic|timing]
#
# 分兩階段使用:
#   Phase A: bash scripts/run_fs_thermal.sh atomic
#            → 使用 AtomicSimpleCPU 快速引導 Linux，建立 checkpoint
#   Phase B: bash scripts/run_fs_thermal.sh timing
#            → 從 checkpoint 恢復，使用 O3CPU + 熱模擬執行工作負載
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
GEM5_ROOT="${GEM5_ROOT:-${HOME}/gem5}"
GEM5_OPT="${GEM5_OPT:-${GEM5_ROOT}/build/ARM/gem5.opt}"
FS_THERMAL="${FS_THERMAL:-${GEM5_ROOT}/configs/example/arm/fs_thermal.py}"
FS_BIGLITTLE="${FS_BIGLITTLE:-${GEM5_ROOT}/configs/example/arm/fs_bigLITTLE.py}"

KERNEL="${KERNEL:-$(cd "${PROJECT_DIR}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"

OUTDIR_ATOMIC="${PROJECT_DIR}/m5out_fs_atomic"
OUTDIR_THERMAL="${PROJECT_DIR}/m5out_fs_thermal"
BOOTSCRIPT="${PROJECT_DIR}/scripts/fs_boot_with_workload.rcS"

# --- Argument parsing ---
MODE="${1:-atomic}"

# --- Verify resources ---
echo "=== Verifying resources ==="
for f in "$GEM5_OPT" "$KERNEL" "$DISK" "$BOOTLOADER"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required file not found: $f"
        exit 1
    fi
    echo "  OK: $f"
done
echo ""

if [ "$MODE" = "atomic" ]; then
    # ========================================================
    # Phase A: Atomic CPU fast boot + checkpoint
    # ========================================================
    echo "=== Phase A: Atomic CPU Fast Boot ==="
    echo "  Output: $OUTDIR_ATOMIC"
    echo "  This will boot Linux quickly with AtomicSimpleCPU"
    echo "  and save a checkpoint for later use."
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

elif [ "$MODE" = "timing" ]; then
    # ========================================================
    # Phase B: Timing CPU + Thermal Model from checkpoint
    # ========================================================

    # Find latest checkpoint
    CHECKPOINT=""
    if [ -d "$OUTDIR_ATOMIC" ]; then
        CHECKPOINT=$(find "$OUTDIR_ATOMIC" -name "cpt.*" -type d | sort -V | tail -1)
    fi

    echo "=== Phase B: Timing CPU + Thermal Simulation ==="
    echo "  Output:     $OUTDIR_THERMAL"
    echo "  Checkpoint: ${CHECKPOINT:-NONE (direct boot)}"
    echo ""

    mkdir -p "$OUTDIR_THERMAL"

    RESTORE_ARG=""
    if [ -n "$CHECKPOINT" ]; then
        RESTORE_ARG="--restore-from=$CHECKPOINT"
    fi

    "$GEM5_OPT" \
        --outdir="$OUTDIR_THERMAL" \
        "$FS_THERMAL" \
        --kernel="$KERNEL" \
        --disk="$DISK" \
        --bootloader="$BOOTLOADER" \
        --bootscript="$BOOTSCRIPT" \
        --cpu-type=timing \
        --big-cpus=1 \
        --little-cpus=1 \
        --caches \
        --big-cpu-clock=3.3GHz \
        --little-cpu-clock=2.0GHz \
        --mem-size=2GiB \
        --thermal-step=0.01 \
        --ambient-temp=25C \
        --r-die-pkg=5.0 \
        --r-pkg-amb=10.0 \
        --c-die=1.0 \
        --c-pkg=5.0 \
        --stats-period=0.0002 \
        --machine-type=VExpress_GEM5_Foundation \
        $RESTORE_ARG \
        2>&1 | tee "${OUTDIR_THERMAL}/console.log"

else
    echo "Usage: $0 [atomic|timing]"
    echo "  atomic  — Fast boot with AtomicSimpleCPU (Phase A)"
    echo "  timing  — Thermal simulation with O3CPU (Phase B)"
    exit 1
fi

echo ""
echo "=== Simulation finished ==="
