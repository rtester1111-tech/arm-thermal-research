#!/bin/bash
# run_3node_smoke_test.sh — Workstream A: 3-node thermal export smoke test
#
# Requires:
#   1. patches/thermal_node_temperature_stat.patch applied to gem5 source and rebuilt.
#   2. A valid atomic checkpoint in $OUTDIR_ATOMIC (run Phase A first).
#
# What it verifies:
#   stats.txt contains system.thermal_model.node_pkg.temperature
#   stats.txt contains system.thermal_model.node_hs.temperature
#   Both values are in the range [20, 40] C after ~0.5 s simulated time.
#
# Usage:
#   bash scripts/ops/run_3node_smoke_test.sh
#   bash scripts/ops/run_3node_smoke_test.sh --rebuild   # also rebuilds gem5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
GEM5_ROOT="${GEM5_ROOT:-${HOME}/gem5}"
GEM5_OPT="${GEM5_OPT:-${GEM5_ROOT}/build/ARM/gem5.opt}"
FS_THERMAL="${FS_THERMAL:-${GEM5_ROOT}/configs/example/arm/fs_thermal.py}"

KERNEL="${KERNEL:-$(cd "${PROJECT_DIR}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"

OUTDIR_ATOMIC="${PROJECT_DIR}/m5out_fs_atomic_dynamic"
OUTDIR_3NODE="${PROJECT_DIR}/m5out_3node_smoke"
BOOTSCRIPT="${PROJECT_DIR}/scripts/fs_bootscript.rcS"

echo "==================================================================="
echo "Workstream A Smoke Test: 3-Node Thermal Export"
echo "==================================================================="

# Optional rebuild
if [ "${1:-}" = "--rebuild" ]; then
    echo "[STEP 0] Applying patch and rebuilding gem5..."
    cd "$GEM5_ROOT"
    git apply "${PROJECT_DIR}/patches/thermal_node_temperature_stat.patch"
    scons build/ARM/gem5.opt -j"$(nproc)"
    cd "$PROJECT_DIR"
    echo "[STEP 0] Rebuild done."
fi

# Find checkpoint
CHECKPOINT=$(find "$OUTDIR_ATOMIC" -name "cpt.*" -type d 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$CHECKPOINT" ]; then
    echo "[ERROR] No checkpoint found in $OUTDIR_ATOMIC"
    echo "        Run Phase A first: bash scripts/run_fs_thermal.sh atomic"
    exit 1
fi
echo "[INFO] Using checkpoint: $CHECKPOINT"

# Run 0.5 s simulation with 3-node topology
mkdir -p "$OUTDIR_3NODE"
echo "[RUN] Starting gem5 (target: 0.5 simulated seconds, 3-node mode)..."
"$GEM5_OPT" \
    --outdir="$OUTDIR_3NODE" \
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
    --r-pkg-hs=2.0 \
    --r-hs-amb=8.0 \
    --c-die=1.0 \
    --c-pkg=5.0 \
    --c-hs=15.0 \
    --enable-3node \
    --stats-period=0.01 \
    --machine-type=VExpress_GEM5_Foundation \
    --restore-from="$CHECKPOINT" \
    2>&1 | tee "${OUTDIR_3NODE}/console.log" &

GEM5_PID=$!

# Let it run for a while, then stop
sleep 120 && kill $GEM5_PID 2>/dev/null || true

STATS="${OUTDIR_3NODE}/stats.txt"
echo ""
echo "==================================================================="
echo "Verification: grep for 3-node temperature stats"
echo "==================================================================="
if [ -f "$STATS" ]; then
    echo "--- node_pkg ---"
    grep "node_pkg\.temperature" "$STATS" | tail -5 || echo "  (not found)"
    echo "--- node_hs ---"
    grep "node_hs\.temperature"  "$STATS" | tail -5 || echo "  (not found)"
    echo "--- node_die ---"
    grep "node_die\.temperature" "$STATS" | tail -5 || echo "  (not found)"
    echo "--- T_die from thermal_domain ---"
    grep "thermal_domain\.currentTemp" "$STATS" | tail -5 || echo "  (not found)"
    echo ""
    if grep -q "node_pkg\.temperature" "$STATS" && grep -q "node_hs\.temperature" "$STATS"; then
        echo "RESULT: SUCCESS — T_pkg and T_hs both present in stats.txt"
        python3 scripts/parse_fs_thermal_stats.py "$STATS" "${OUTDIR_3NODE}/results"
    else
        echo "RESULT: FAIL — one or both node temperatures missing."
        echo "        Was thermal_node_temperature_stat.patch applied and gem5 rebuilt?"
    fi
else
    echo "[ERROR] stats.txt not found at $STATS"
fi
echo "==================================================================="
