#!/bin/bash
# run_full_simulation.sh
# Runs the full 4K 100-iteration gem5 simulations for all kernels.
# WARNING: This will take several hours.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
GEM5_DIR="${GEM5_DIR:-${HOME}/gem5}"
GEM5_OPT="${GEM5_OPT:-${GEM5_DIR}/build/ARM/gem5.opt}"
GEM5_CONFIG="${GEM5_CONFIG:-${GEM5_DIR}/configs/deprecated/example/se.py}"

cd "$PROJECT_DIR"

mkdir -p "$PROJECT_DIR/results"
mkdir -p "$PROJECT_DIR/logs"

echo "[1/5] Starting Scalar Simulation..."
$GEM5_OPT --outdir="$PROJECT_DIR/m5out_scalar" $GEM5_CONFIG \
  --cmd="$PROJECT_DIR/src/scalar.aarch64" \
  --cpu-type=AtomicSimpleCPU \
  --mem-type=LPDDR5_6400_1x16_8B_BL32 \
  --mem-size=512MB > "$PROJECT_DIR/logs/gem5_scalar.log" 2>&1
cp "$PROJECT_DIR/m5out_scalar/stats.txt" "$PROJECT_DIR/results/stats_scalar.txt"

echo "[2/5] Starting NEON Simulation..."
$GEM5_OPT --outdir="$PROJECT_DIR/m5out_neon" $GEM5_CONFIG \
  --cmd="$PROJECT_DIR/src/neon.aarch64" \
  --cpu-type=AtomicSimpleCPU \
  --mem-type=LPDDR5_6400_1x16_8B_BL32 \
  --mem-size=512MB > "$PROJECT_DIR/logs/gem5_neon.log" 2>&1
cp "$PROJECT_DIR/m5out_neon/stats.txt" "$PROJECT_DIR/results/stats_neon.txt"

echo "[3/5] Starting SVE2 (256-bit) Simulation..."
$GEM5_OPT --outdir="$PROJECT_DIR/m5out_sve2" $GEM5_CONFIG \
  --cmd="$PROJECT_DIR/src/sve2.aarch64" \
  --cpu-type=AtomicSimpleCPU \
  --mem-type=LPDDR5_6400_1x16_8B_BL32 \
  --mem-size=512MB \
  --param 'system.cpu[:].isa[:].sve_vl_se = 2' > "$PROJECT_DIR/logs/gem5_sve2.log" 2>&1
cp "$PROJECT_DIR/m5out_sve2/stats.txt" "$PROJECT_DIR/results/stats_sve2.txt"

echo "[4/5] Parsing Results..."
python3 - << 'EOF'
import json, os
def parse_stat(path, key):
    if not os.path.exists(path): return None
    with open(path) as f:
        for line in f:
            if key in line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    try: return float(parts[1])
                    except: pass
    return None

results = {}
for mode in ['scalar', 'neon', 'sve2']:
    path = f'results/stats_{mode}.txt'
    results[mode] = {
        'simSeconds':      parse_stat(path, 'simSeconds'),
        'numCycles':       parse_stat(path, 'system.cpu.numCycles'),
        'committedInsts':  parse_stat(path, 'system.cpu.commitStats0.numInsts'),
    }
    cycles = results[mode]['numCycles']
    insts  = results[mode]['committedInsts']
    results[mode]['ipc'] = round(insts/cycles, 3) if cycles else None

with open('results/gem5_real_results.json', 'w') as f:
    json.dump(results, f, indent=2)
EOF

echo "[5/5] Running Thermal Simulation..."
python3 scripts/thermal_governor.py --out results

echo "Full simulation complete! Committing results..."
git add results/ scripts/ src/
git commit -m "feat: complete full 4K 100-iteration simulation results"
# git push origin main  # Manual push recommended due to potential hang

echo "Done! Check results/ for final data and charts."
