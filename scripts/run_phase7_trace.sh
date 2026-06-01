#!/usr/bin/env bash
# ============================================================
# run_phase7_trace.sh — Phase 7: Task Placement Trace
# ============================================================
# Two-step pipeline inside a tmux session:
#
#   Step 1: Atomic boot → checkpoint (m5out_fs_atomic_p7/)
#           Skip if checkpoint already exists.
#
#   Step 2: Timing sim restoring from checkpoint,
#           running fs_phase7_task_trace.rcS via the
#           fs_boot_dynamic.rcS readfile mechanism.
#           Output → m5out_phase7/
#
# Usage:
#   bash run_phase7_trace.sh            # start / attach
#   bash run_phase7_trace.sh status     # show session / log status
#   bash run_phase7_trace.sh attach     # re-attach existing session
#   bash run_phase7_trace.sh atomic-only  # only create checkpoint
# ============================================================

SESSION="gem5-phase7"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
GEM5_DIR="${GEM5_DIR:-${HOME}/gem5}"
GEM5_OPT="${GEM5_DIR}/build/ARM/gem5.opt"
FS_BIGLITTLE="${GEM5_DIR}/configs/example/arm/fs_bigLITTLE.py"
FS_THERMAL="${GEM5_DIR}/configs/example/arm/fs_thermal.py"
KERNEL="${KERNEL:-$(cd "${PROJECT}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"
ATOMIC_OUTDIR="${PROJECT}/m5out_fs_atomic_p7"
PHASE7_OUTDIR="${PROJECT}/m5out_phase7"
LOGFILE="${PROJECT}/logs/phase7_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "${PROJECT}/logs" "$ATOMIC_OUTDIR" "$PHASE7_OUTDIR"

# ── Status ──────────────────────────────────────────────────────────────────
if [ "${1:-}" = "status" ]; then
    echo "=== tmux session ==="
    tmux ls 2>/dev/null || echo "(none)"
    echo ""
    echo "=== checkpoint ==="
    find "$ATOMIC_OUTDIR" -name "cpt.*" -type d 2>/dev/null | sort -V | tail -3 || echo "(none)"
    echo ""
    echo "=== latest log ==="
    ls -lt "${PROJECT}/logs/"phase7*.log 2>/dev/null | head -3
    echo ""
    echo "=== output dir ==="
    ls -lh "$PHASE7_OUTDIR" 2>/dev/null || echo "(empty)"
    exit 0
fi

if [ "${1:-}" = "attach" ]; then
    tmux attach-session -t "$SESSION" 2>/dev/null \
        || echo "No session '$SESSION'. Run without args to start."
    exit 0
fi

# ── Validate prerequisites ─────────────────────────────────────────────────
for f in "$GEM5_OPT" "$KERNEL" "$DISK" "$BOOTLOADER" \
          "${SCRIPT_DIR}/fs_boot_dynamic.rcS" \
          "${SCRIPT_DIR}/fs_phase7_task_trace.rcS"; do
    if [ ! -f "$f" ]; then
        echo "[ERROR] Required file not found: $f"
        exit 1
    fi
done

# ── Already running ────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[!] Session '$SESSION' already exists — attaching."
    tmux attach-session -t "$SESSION"
    exit 0
fi

BS='\'

# ── Build inner script ──────────────────────────────────────────────────────
INNER=$(cat <<INNER_EOF
#!/usr/bin/env bash
set -euo pipefail

PROJECT="$PROJECT"
GEM5_OPT="$GEM5_OPT"
FS_BIGLITTLE="$FS_BIGLITTLE"
FS_THERMAL="$FS_THERMAL"
KERNEL="$KERNEL"
DISK="$DISK"
BOOTLOADER="$BOOTLOADER"
ATOMIC_OUTDIR="$ATOMIC_OUTDIR"
PHASE7_OUTDIR="$PHASE7_OUTDIR"
LOGFILE="$LOGFILE"

log() { echo "[\$(date '+%H:%M:%S')] \$*" | tee -a "\$LOGFILE"; }

log "======================================================="
log "  Phase 7: Task Placement Trace"
log "======================================================="
log "Session: $SESSION  |  Log: \$LOGFILE"
log ""

# ── Step 1: Atomic boot → checkpoint ─────────────────────────────────────
CHECKPOINT=\$(find "\$ATOMIC_OUTDIR" -name "cpt.*" -type d 2>/dev/null | sort -V | tail -1)

if [ -n "\$CHECKPOINT" ] && [ -f "\$CHECKPOINT/m5.cpt" ]; then
    log "STEP 1/2: Checkpoint found — skipping atomic boot"
    log "  Using: \$CHECKPOINT"
else
    log "STEP 1/2: Atomic boot — creating checkpoint"
    log "  Output: \$ATOMIC_OUTDIR"
    log "  This boots Linux with AtomicSimpleCPU and saves a checkpoint."
    log "  Expected time: 10–30 minutes"
    log ""

    "\$GEM5_OPT" $BS
        --outdir="\$ATOMIC_OUTDIR" $BS
        "\$FS_BIGLITTLE" $BS
        --kernel="\$KERNEL" $BS
        --disk="\$DISK" $BS
        --bootloader="\$BOOTLOADER" $BS
        --bootscript="\${PROJECT}/scripts/fs_boot_dynamic.rcS" $BS
        --cpu-type=atomic $BS
        --big-cpus=1 $BS
        --little-cpus=1 $BS
        --mem-size=2GiB $BS
        --machine-type=VExpress_GEM5_Foundation $BS
        2>&1 | tee -a "\$LOGFILE"

    CHECKPOINT=\$(find "\$ATOMIC_OUTDIR" -name "cpt.*" -type d 2>/dev/null | sort -V | tail -1)
    if [ -z "\$CHECKPOINT" ] || [ ! -f "\$CHECKPOINT/m5.cpt" ]; then
        log "[ERROR] Checkpoint not found after atomic boot. Check log."
        exit 1
    fi
    log "Checkpoint created: \$CHECKPOINT"
fi

# ── Step 2: Timing sim with Phase 7 workload ─────────────────────────────
log ""
log "STEP 2/2: Phase 7 Timing Simulation"
log "  Checkpoint : \$CHECKPOINT"
log "  Bootscript : \${PROJECT}/scripts/fs_phase7_task_trace.rcS"
log "  Output     : \$PHASE7_OUTDIR"
log "  Thermal    : 3-node Cauer (R1=5,R2=2,R3=8 K/W; C1=1,C2=5,C3=15 J/K)"
log "  Expected   : 30–90 min (workload is short C binary, not Python)"
log ""

"\$GEM5_OPT" $BS
    --outdir="\$PHASE7_OUTDIR" $BS
    "\$FS_THERMAL" $BS
    --kernel="\$KERNEL" $BS
    --disk="\$DISK" $BS
    --bootloader="\$BOOTLOADER" $BS
    --bootscript="\${PROJECT}/scripts/fs_phase7_task_trace.rcS" $BS
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
log "======================================================="
log "Phase 7 complete!"
log ""
log "Evidence files:"
log "  Terminal output : \${PHASE7_OUTDIR}/system.terminal"
log "  Stats           : \${PHASE7_OUTDIR}/stats.txt"
log "  Config          : \${PHASE7_OUTDIR}/config.ini"
log ""
log "Parse [SAMPLER] and [STRESS] lines from terminal for"
log "CPU placement evidence."
log "======================================================="

INNER_EOF
)

if [ "${1:-}" = "atomic-only" ]; then
    INNER=$(echo "$INNER" | sed 's/^# ── Step 2.*$/exit 0/')
fi

INNER_FILE=$(mktemp /tmp/gem5_phase7_XXXXXX.sh)
printf "%s\n" "$INNER" > "$INNER_FILE"
chmod +x "$INNER_FILE"

# ── Launch tmux ─────────────────────────────────────────────────────────────
tmux new-session -d -s "$SESSION" -x 220 -y 50
tmux send-keys -t "$SESSION" "bash '$INNER_FILE'; rm -f '$INNER_FILE'" Enter

echo "============================================="
echo "  Phase 7 simulation launched"
echo "============================================="
echo ""
echo "  Session : $SESSION"
echo "  Log     : $LOGFILE"
echo "  Atomic  : $ATOMIC_OUTDIR"
echo "  Phase 7 : $PHASE7_OUTDIR"
echo ""
echo "  Attach  : tmux attach -t $SESSION"
echo "  Detach  : Ctrl-b  d"
echo "  Status  : bash $(basename "$0") status"
echo "============================================="
echo ""

tmux attach-session -t "$SESSION"
