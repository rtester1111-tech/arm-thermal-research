#!/usr/bin/env bash
# reproduce.sh — One-command reproduction of the gem5 Absolute-Zero Heat Sink Bug
#
# Prerequisites:
#   - gem5 25.1.x built for ARM: $GEM5_HOME/build/ARM/gem5.opt
#   - AArch64 Linux disk image and bootloader (gem5 resources)
#   - An existing AtomicSimpleCPU checkpoint (fast-boot)
#
# This script runs gem5 with an UNPATCHED thermal model and a 2-node Cauer RC
# network. You should observe the junction temperature drop from 25°C to ~12°C
# in the stats output, demonstrating the bug.
#
# To reproduce with the PATCHED model, apply gem5_thermal_fix.patch first:
#   cd $GEM5_HOME && git apply /path/to/gem5_thermal_fix.patch
#   python3 build/ARM/gem5.opt -j$(nproc) ARM
#   bash reproduce.sh
# Then junction temperature should rise monotonically above 25°C.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
GEM5_HOME="${GEM5_HOME:-$HOME/gem5}"
GEM5="${GEM5_HOME}/build/ARM/gem5.opt"

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
OUTDIR="${PROJECT_DIR}/m5out_reproduce_bug"

KERNEL="${KERNEL:-${PROJECT_DIR}/../linux-stable/vmlinux}"
DISK="${DISK:-$HOME/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-$HOME/.cache/gem5/arm64-bootloader-foundation-2.0.0}"
CHECKPOINT="${CHECKPOINT:-${PROJECT_DIR}/m5out_fs_atomic/cpt.427133267000}"
BOOTSCRIPT="${PROJECT_DIR}/scripts/fs_bootscript.rcS"

# ── Sanity checks ─────────────────────────────────────────────────────────────
check() {
    if [[ ! -e "$1" ]]; then
        echo "[ERROR] Missing: $1"
        echo "        Set ${2:-the relevant} env var or check the path."
        exit 1
    fi
}

check "$GEM5"       "GEM5_HOME"
check "$KERNEL"     "KERNEL"
check "$DISK"       "DISK"
check "$BOOTLOADER" "BOOTLOADER"
check "$CHECKPOINT" "CHECKPOINT"

mkdir -p "$OUTDIR"

echo "========================================================"
echo "  gem5 Absolute-Zero Heat Sink Bug — Reproduction Run"
echo "========================================================"
echo "  gem5:        $GEM5"
echo "  outdir:      $OUTDIR"
echo "  checkpoint:  $CHECKPOINT"
echo "  Expected:    Junction temp drops 25°C → ~12°C"
echo "========================================================"
echo ""

# ── Run gem5 ──────────────────────────────────────────────────────────────────
"$GEM5" \
    --outdir="$OUTDIR" \
    "$GEM5_HOME/configs/example/arm/fs_thermal.py" \
    --kernel="$KERNEL" \
    --disk="$DISK" \
    --bootloader="$BOOTLOADER" \
    --bootscript="$BOOTSCRIPT" \
    --cpu-type=timing \
    --big-cpus=1 \
    --little-cpus=0 \
    --caches \
    --big-cpu-clock=3.3GHz \
    --mem-size=2GiB \
    --thermal-step=0.01 \
    --ambient-temp=25C \
    --r-die-pkg=5.0 \
    --r-pkg-amb=10.0 \
    --c-die=1.0 \
    --c-pkg=5.0 \
    --stats-period=0.0002 \
    --machine-type=VExpress_GEM5_Foundation \
    --restore-from="$CHECKPOINT" \
    2>&1 | tee "$OUTDIR/gem5.log"

# ── Extract result ─────────────────────────────────────────────────────────────
echo ""
echo "========================================================"
echo "  Results (from $OUTDIR/stats.txt)"
echo "========================================================"

MIN_TEMP=$(grep "thermal_domain.currentTemp" "$OUTDIR/stats.txt" \
           | awk '{print $2}' | sort -n | head -1)

echo "  Min junction temp observed: ${MIN_TEMP} °C"
echo ""

if python3 -c "exit(0 if float('${MIN_TEMP}') < 20.0 else 1)" 2>/dev/null; then
    echo "  ✅ BUG REPRODUCED: Junction temperature dropped below 20°C"
    echo "     (expected ~12.34°C for unpatched gem5 with these RC parameters)"
else
    echo "  ℹ️  Temperature did not drop below 20°C."
    echo "     If you applied the patch, this is expected (bug is fixed)."
    echo "     If running unpatched, check that --c-pkg > 0 and the bootscript"
    echo "     generates CPU activity in the first few ms."
fi

echo "========================================================"
