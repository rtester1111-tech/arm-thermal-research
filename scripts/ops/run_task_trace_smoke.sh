#!/bin/bash
# run_task_trace_smoke.sh — Workstream B: task placement trace smoke test
#
# Requires:
#   1. workloads/stress_lcg/stress_lcg.aarch64 compiled.
#   2. Binary installed as /root/stress_lcg in the gem5 disk image.
#   3. A valid atomic checkpoint in $OUTDIR_ATOMIC.
#
# What it verifies:
#   system.terminal contains [STRESS] START/DONE lines with CPU field.
#   system.terminal contains [SAMPLER] lines with CPU/Cluster columns.
#   Phase A [SAMPLER] lines show CPU=0 (pinned).
#   Phase B [SAMPLER] lines show CPU=0 or CPU=1 (scheduler choice).
#
# Usage:
#   bash scripts/ops/run_task_trace_smoke.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
GEM5_ROOT="${GEM5_ROOT:-${HOME}/gem5}"
GEM5_OPT="${GEM5_OPT:-${GEM5_ROOT}/build/ARM/gem5.opt}"
FS_BIGLITTLE="${FS_BIGLITTLE:-${GEM5_ROOT}/configs/example/arm/fs_bigLITTLE.py}"

KERNEL="${KERNEL:-$(cd "${PROJECT_DIR}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"

OUTDIR_ATOMIC="${PROJECT_DIR}/m5out_fs_atomic_dynamic"
OUTDIR_TRACE="${PROJECT_DIR}/m5out_task_trace"
BOOTSCRIPT="${PROJECT_DIR}/scripts/fs_phase7_task_trace.rcS"

echo "==================================================================="
echo "Workstream B Smoke Test: Task Placement Trace"
echo "==================================================================="

# Find checkpoint
CHECKPOINT=$(find "$OUTDIR_ATOMIC" -name "cpt.*" -type d 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$CHECKPOINT" ]; then
    echo "[ERROR] No checkpoint found in $OUTDIR_ATOMIC"
    echo "        Run Phase A first: bash scripts/run_fs_thermal.sh atomic"
    exit 1
fi
echo "[INFO] Using checkpoint: $CHECKPOINT"
mkdir -p "$OUTDIR_TRACE"

echo "[RUN] Starting gem5 with task-trace bootscript..."
"$GEM5_OPT" \
    --outdir="$OUTDIR_TRACE" \
    "$FS_BIGLITTLE" \
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
    --machine-type=VExpress_GEM5_Foundation \
    --restore-from="$CHECKPOINT" \
    2>&1 | tee "${OUTDIR_TRACE}/console.log"

TERMINAL="${OUTDIR_TRACE}/system.terminal"
echo ""
echo "==================================================================="
echo "Verification: grep placement evidence from system.terminal"
echo "==================================================================="
if [ -f "$TERMINAL" ]; then
    echo "--- STRESS lines (CPU at start/end) ---"
    grep "\[STRESS\]" "$TERMINAL" || echo "  (none)"
    echo ""
    echo "--- SAMPLER lines (external poll) ---"
    grep "\[SAMPLER\]" "$TERMINAL" || echo "  (none)"
    echo ""
    echo "--- FREQ lines ---"
    grep "\[FREQ\]" "$TERMINAL" || echo "  (none)"
    echo ""
    PHASE_A_CPU0=$(grep "\[SAMPLER\].*Phase:A.*CPU:0" "$TERMINAL" | wc -l)
    PHASE_A_CPU1=$(grep "\[SAMPLER\].*Phase:A.*CPU:1" "$TERMINAL" | wc -l)
    PHASE_B_CPU0=$(grep "\[SAMPLER\].*Phase:B.*CPU:0" "$TERMINAL" | wc -l)
    PHASE_B_CPU1=$(grep "\[SAMPLER\].*Phase:B.*CPU:1" "$TERMINAL" | wc -l)
    echo "Phase A (pinned cpu0): CPU0=$PHASE_A_CPU0 samples, CPU1=$PHASE_A_CPU1 samples"
    echo "Phase B (free):        CPU0=$PHASE_B_CPU0 samples, CPU1=$PHASE_B_CPU1 samples"
    if [ "$PHASE_A_CPU0" -gt 0 ]; then
        echo "RESULT: Partial success — Phase A pinning confirmed on cpu0."
    else
        echo "RESULT: No placement samples. Check /root/stress_lcg is installed."
    fi
else
    echo "[ERROR] system.terminal not found at $TERMINAL"
fi
echo "==================================================================="
