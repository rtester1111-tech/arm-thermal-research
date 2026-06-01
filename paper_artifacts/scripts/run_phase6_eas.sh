#!/usr/bin/env bash
# ============================================================
# run_phase6_eas.sh — Phase 6: EAS Task Migration Simulation
# ============================================================
# Runs a three-step pipeline inside a tmux session:
#
#   Step 1: Patch base DTB with EAS properties
#   Step 2: gem5 Phase 6 timing simulation with EAS-enabled DTB
#   Step 3: Parse and compare thermal + CPU stats
#
# Usage:
#   bash run_phase6_eas.sh            # start / attach
#   bash run_phase6_eas.sh status     # show session / log status
#   bash run_phase6_eas.sh attach     # re-attach existing session
#   bash run_phase6_eas.sh patch-only # only generate EAS DTB, no sim
# ============================================================

SESSION="gem5-phase6"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
GEM5_DIR="${GEM5_DIR:-${HOME}/gem5}"
OUTDIR="${PROJECT}/m5out_phase6"
LOGFILE="${PROJECT}/logs/phase6_$(date +%Y%m%d_%H%M%S).log"
CHECKPOINT="$(find "${PROJECT}/m5out_fs_atomic_dynamic" -name "cpt.*" -type d | sort -V | tail -1)"
EAS_DTB="${OUTDIR}/eas_patched.dtb"
GEM5_OPT="${GEM5_DIR}/build/ARM/gem5.opt"
FS_SCRIPT="${GEM5_DIR}/configs/example/arm/fs_thermal.py"
KERNEL="${KERNEL:-$(cd "${PROJECT}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"

mkdir -p "${PROJECT}/logs" "$OUTDIR"

# ── Status ─────────────────────────────────────────────────────────────────
if [ "${1:-}" = "status" ]; then
    echo "=== tmux session ==="
    tmux ls 2>/dev/null || echo "(none)"
    echo ""
    echo "=== latest log ==="
    ls -lt "${PROJECT}/logs/"phase6*.log 2>/dev/null | head -3
    echo ""
    echo "=== output dir ==="
    ls -lh "$OUTDIR" 2>/dev/null || echo "(empty)"
    exit 0
fi

if [ "${1:-}" = "attach" ]; then
    tmux attach-session -t "$SESSION" 2>/dev/null \
        || echo "No session '$SESSION'. Run without args to start."
    exit 0
fi

# ── Patch-only mode ────────────────────────────────────────────────────────
if [ "${1:-}" = "patch-only" ]; then
    echo "[patch-only] Generating EAS DTB..."
    python3 "${PROJECT}/scripts/patch_eas_dtb.py" \
        --input  "${PROJECT}/m5out_fs_atomic_dynamic/system.dtb" \
        --output "${EAS_DTB}" \
        --dump-dts
    echo "Done: $EAS_DTB"
    exit 0
fi

# ── Already running ────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[!] Session '$SESSION' already exists — attaching."
    tmux attach-session -t "$SESSION"
    exit 0
fi

# ── Validate prerequisites ─────────────────────────────────────────────────
if [ ! -f "$GEM5_OPT" ]; then
    echo "[ERROR] gem5 binary not found: $GEM5_OPT"
    echo "        Build with: cd ${GEM5_DIR} && scons build/ARM/gem5.opt -j\$(nproc)"
    exit 1
fi
if [ ! -f "$CHECKPOINT/m5.cpt" ]; then
    echo "[ERROR] Checkpoint not found: $CHECKPOINT"
    echo "        Run Phase A (Atomic boot) first to create a checkpoint."
    exit 1
fi

BS='\'
# ── Build inner script ──────────────────────────────────────────────────────
INNER=$(cat <<INNER_EOF
#!/usr/bin/env bash
set -euo pipefail

PROJECT="$PROJECT"
OUTDIR="$OUTDIR"
LOGFILE="$LOGFILE"
GEM5_OPT="$GEM5_OPT"
FS_SCRIPT="$FS_SCRIPT"
CHECKPOINT="$CHECKPOINT"
EAS_DTB="$EAS_DTB"
GEM5_DIR="$GEM5_DIR"
KERNEL="$KERNEL"
DISK="$DISK"
BOOTLOADER="$BOOTLOADER"

log() { echo "[\$(date '+%H:%M:%S')] \$*" | tee -a "\$LOGFILE"; }

log "======================================================="
log "  Phase 6: EAS Task Migration Simulation"
log "======================================================="
log "Session: $SESSION  |  Log: \$LOGFILE"
log ""

# ── Step 1: Generate EAS DTB ──────────────────────────────────────────────
log "STEP 1/3: Patching DTB with EAS properties"
log "  Input : \${PROJECT}/m5out_fs_atomic_dynamic/system.dtb"
log "  Output: \$EAS_DTB"

python3 "\${PROJECT}/scripts/patch_eas_dtb.py" $BS
    --input  "\${PROJECT}/m5out_fs_atomic_dynamic/system.dtb" $BS
    --output "\$EAS_DTB" $BS
    --dump-dts $BS
    2>&1 | tee -a "\$LOGFILE"

log "DTB patch complete."
log ""

# ── Step 2: Run gem5 Phase 6 simulation ──────────────────────────────────
log "STEP 2/3: Phase 6 Timing Simulation with EAS DTB"
log "  Checkpoint: \$CHECKPOINT"
log "  DTB:        \$EAS_DTB"
log "  Bootscript: \${PROJECT}/scripts/fs_eas_phase6.rcS"
log ""
log "  Thermal: R_die=5 K/W, C_die=1 J/K, R_pkg=10 K/W, C_pkg=5 J/K"
log "  DVFS: big 3.3/3.0/2.8/2.4/2.0 GHz, little 2.0/1.5/1.0 GHz"
log "  EAS: big cap=1024, little cap=540 (capacity-dmips-mhz)"
log ""

"\$GEM5_OPT" $BS
    --outdir="\$OUTDIR" $BS
    "\$FS_SCRIPT" $BS
    --kernel="\$KERNEL" $BS
    --disk="\$DISK" $BS
    --bootloader="\$BOOTLOADER" $BS
    --dtb="\$EAS_DTB" $BS
    --bootscript="\${PROJECT}/scripts/fs_eas_phase6.rcS" $BS
    --cpu-type=timing $BS
    --big-cpus=1 $BS
    --little-cpus=1 $BS
    --caches $BS
    --big-cpu-clock=3.3GHz $BS
    --little-cpu-clock=2.0GHz $BS
    --mem-size=2GiB $BS
    --thermal-step=0.01 $BS
    --ambient-temp=25C $BS
    --r-die-pkg=5.0 $BS
    --r-pkg-amb=10.0 $BS
    --c-die=1.0 $BS
    --c-pkg=5.0 $BS
    --enable-3node $BS
    --stats-period=0.005 $BS
    --machine-type=VExpress_GEM5_Foundation $BS
    --restore-from="\$CHECKPOINT" $BS
    2>&1 | tee -a "\$LOGFILE"

log ""
log "Simulation complete."
log ""

# ── Step 3: Parse results ─────────────────────────────────────────────────
log "STEP 3/3: Parsing Phase 6 results"
RESULTS_DIR="\${PROJECT}/results/phase6"
mkdir -p "\$RESULTS_DIR"

python3 "\${PROJECT}/scripts/parse_fs_thermal_stats.py" $BS
    "\${OUTDIR}/stats.txt" $BS
    "\$RESULTS_DIR" $BS
    2>&1 | tee -a "\$LOGFILE"

log ""
log "======================================================="
log "Phase 6 complete!"
log ""
log "Results in: \$RESULTS_DIR"
log "  Thermal trace : \${RESULTS_DIR}/fs_temp_vs_time.png"
log "  Power trace   : \${RESULTS_DIR}/fs_power_vs_time.png"
log "  Frequency     : \${RESULTS_DIR}/fs_frequency_vs_time.png"
log "  Raw JSON      : \${RESULTS_DIR}/fs_simulation_results.json"
log ""
log "EAS terminal output: \${OUTDIR}/system.terminal"
log "======================================================="

INNER_EOF
)

INNER_FILE=$(mktemp /tmp/gem5_phase6_XXXXXX.sh)
printf "%s\n" "$INNER" > "$INNER_FILE"
chmod +x "$INNER_FILE"

# ── Launch tmux ─────────────────────────────────────────────────────────────
tmux new-session -d -s "$SESSION" -x 220 -y 50
tmux send-keys -t "$SESSION" "bash '$INNER_FILE'; rm -f '$INNER_FILE'" Enter

echo "============================================="
echo "  Phase 6 EAS simulation launched"
echo "============================================="
echo ""
echo "  Session : $SESSION"
echo "  Log     : $LOGFILE"
echo "  Output  : $OUTDIR"
echo ""
echo "  Attach  : tmux attach -t $SESSION"
echo "  Detach  : Ctrl-b  d"
echo "  Status  : bash $(basename "$0") status"
echo "============================================="
echo ""

tmux attach-session -t "$SESSION"
