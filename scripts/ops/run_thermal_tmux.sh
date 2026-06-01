#!/usr/bin/env bash
# ============================================================
# run_thermal_tmux.sh
# ============================================================
# Runs the full gem5 thermal simulation pipeline inside a
# persistent tmux session. Safe against VPN disconnection.
#
# Usage:
#   bash scripts/ops/run_thermal_tmux.sh          # start / resume session
#   bash scripts/ops/run_thermal_tmux.sh attach   # just attach to existing
#   bash scripts/ops/run_thermal_tmux.sh status   # show session/log status
# ============================================================

SESSION="gem5-thermal"
SCRIPT_NAME="scripts/ops/run_thermal_tmux.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
GEM5_DIR="${GEM5_DIR:-${HOME}/gem5}"
LOGFILE="${PROJECT}/logs/thermal_run_$(date +%Y%m%d_%H%M%S).log"
OUTDIR="${PROJECT}/m5out_fs_thermal_v2"
KERNEL="${KERNEL:-$(cd "${PROJECT}/.." && pwd)/linux-stable/vmlinux}"
DISK="${DISK:-${HOME}/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0}"
BOOTLOADER="${BOOTLOADER:-${HOME}/.cache/gem5/arm64-bootloader-foundation-2.0.0}"

mkdir -p "${PROJECT}/logs" "$OUTDIR"

# ── Status ────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "status" ]; then
    echo "=== tmux session ==="
    tmux ls 2>/dev/null || echo "(none)"
    echo ""
    echo "=== latest log ==="
    ls -lt "${PROJECT}/logs/"*.log 2>/dev/null | head -3
    echo ""
    echo "=== output dir ==="
    ls -lh "$OUTDIR" 2>/dev/null || echo "(empty)"
    exit 0
fi

# ── Attach only ───────────────────────────────────────────────────────────────
if [ "${1:-}" = "attach" ]; then
    tmux attach-session -t "$SESSION" 2>/dev/null \
        || echo "No session '$SESSION' found. Run without args to start."
    exit 0
fi

# ── Already running: just attach ─────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[!] Session '$SESSION' already exists — attaching."
    echo "    Detach anytime with: Ctrl-b  d"
    tmux attach-session -t "$SESSION"
    exit 0
fi

# ── Build the inner script that runs inside tmux ──────────────────────────────
INNER=$(cat <<INNER_EOF
#!/usr/bin/env bash
set -euo pipefail

GEM5_DIR="$GEM5_DIR"
PROJECT="$PROJECT"
OUTDIR="$OUTDIR"
LOGFILE="$LOGFILE"
KERNEL="$KERNEL"
DISK="$DISK"
BOOTLOADER="$BOOTLOADER"
GEM5_OPT="\${GEM5_DIR}/build/ARM/gem5.opt"
CHECKPOINT="\${PROJECT}/m5out_fs_atomic/cpt.427133267000"

log() { echo "[\$(date '+%H:%M:%S')] \$*" | tee -a "\$LOGFILE"; }

log "========================================"
log "  gem5 Thermal Simulation — Bug-Fix Run "
log "========================================"
log "Session: $SESSION"
log "Log:     \$LOGFILE"
log ""

# ── Step 1: Incremental rebuild ───────────────────────────────────────────────
log "STEP 1/2: Incremental gem5 rebuild (thermal_model.cc changed)"
log "          Estimated: 2-4 minutes"

cd "\$GEM5_DIR"
scons build/ARM/gem5.opt -j\$(nproc) 2>&1 | tee -a "\$LOGFILE"

log "Build complete."
log ""

# ── Step 2: Phase B — Timing + Thermal ───────────────────────────────────────
log "STEP 2/2: Phase B — O3CPU Timing Simulation with extended workload"
log "          Checkpoint: \$CHECKPOINT"
log "          Output:     \$OUTDIR"
log "          Bootscript: \${PROJECT}/scripts/fs_thermal_long.rcS"
log ""
log "  Thermal parameters:"
log "    R_die_pkg = 5.0 K/W   C_die = 1.0 J/K  (tau_die = 5 s)"
log "    R_pkg_amb = 10.0 K/W  C_pkg = 5.0 J/K  (tau_pkg = 50 s)"
log "    Thermal step = 0.01 s"
log "    Stats period = 0.2 ms"
log ""
log "  Target: 3-5 simulated seconds of Python3 compute workload"
log "  Expected real-time: several hours (VPN-safe via tmux)"
log ""

"\$GEM5_OPT" \
    --outdir="\$OUTDIR" \
    "\${GEM5_DIR}/configs/example/arm/fs_thermal.py" \
    --kernel="\$KERNEL" \
    --disk="\$DISK" \
    --bootloader="\$BOOTLOADER" \
    --bootscript="\${PROJECT}/scripts/fs_thermal_long.rcS" \
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
    --restore-from="\$CHECKPOINT" \
    2>&1 | tee -a "\$LOGFILE"

log ""
log "========================================"
log "Simulation complete!"
log ""
log "Parse results with:"
log "  python3 \${PROJECT}/scripts/parse_fs_thermal_stats.py \\"
log "          --stats \${OUTDIR}/stats.txt \\"
log "          --output \${PROJECT}/results/phase5_v2/"
log "========================================"

INNER_EOF
)

INNER_FILE=$(mktemp /tmp/gem5_inner_XXXXXX.sh)
echo "$INNER" > "$INNER_FILE"
chmod +x "$INNER_FILE"

# ── Launch tmux session ───────────────────────────────────────────────────────
tmux new-session -d -s "$SESSION" -x 220 -y 50
tmux send-keys -t "$SESSION" "bash '$INNER_FILE'; rm -f '$INNER_FILE'" Enter

echo "============================================="
echo "  gem5 simulation launched in tmux session"
echo "============================================="
echo ""
echo "  Session name : $SESSION"
echo "  Log file     : $LOGFILE"
echo "  Output dir   : $OUTDIR"
echo ""
echo "  Attach now   : tmux attach -t $SESSION"
echo "  Detach later : Ctrl-b  d"
echo "  Re-attach    : bash $SCRIPT_NAME attach"
echo "  Check status : bash $SCRIPT_NAME status"
echo ""
echo "  VPN-safe: session survives disconnection."
echo "  Reconnect to the server and run 'attach' to resume watching."
echo "============================================="
echo ""

tmux attach-session -t "$SESSION"
