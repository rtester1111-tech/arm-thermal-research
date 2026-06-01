#!/bin/bash
# run_o3cpu_idct.sh - Run gem5 simulation for compute-intensive 8x8 2D IDCT kernels
# Estimated time: ~10-40 mins per kernel, ~30-120 mins total.
#
# Suitable for execution on the user's Linux server.
# Ensures that gem5 and aarch64 cross-compiled binaries are correctly pathed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
GEM5_DIR="${GEM5_DIR:-${HOME}/gem5}"
GEM5_OPT="${GEM5_OPT:-${GEM5_DIR}/build/ARM/gem5.opt}"
GEM5_CONFIG="${GEM5_CONFIG:-${GEM5_DIR}/configs/deprecated/example/se.py}"

# Custom ArmO3CPU settings modeled after ARM Cortex-X4 design features
O3_PARAMS="--cpu-type=ArmO3CPU \
  --l1d_size=64kB --l1d_assoc=4 \
  --l1i_size=64kB --l1i_assoc=4 \
  --l2cache --l2_size=512kB --l2_assoc=8 \
  --caches \
  --mem-type=LPDDR5_6400_1x16_8B_BL32 \
  --mem-size=512MB"

echo "=== Starting gem5 Out-of-Order CPU (ArmO3CPU) IDCT Simulation ==="
echo "Project Directory: $PROJECT_DIR"
echo "gem5 Binary:       $GEM5_OPT"
echo "gem5 Config:       $GEM5_CONFIG"
echo "============================================================"

# Create outputs directories if they do not exist
mkdir -p "$PROJECT_DIR/m5out_idct_scalar_o3"
mkdir -p "$PROJECT_DIR/m5out_idct_neon_o3"
mkdir -p "$PROJECT_DIR/m5out_idct_sve2_o3"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/results"

# 1. Run IDCT Scalar simulation
echo -e "\n[1/3] Running IDCT Scalar O3CPU..."
time "$GEM5_OPT" --outdir="$PROJECT_DIR/m5out_idct_scalar_o3" "$GEM5_CONFIG" \
  --cmd="$PROJECT_DIR/src/idct_scalar.aarch64" \
  $O3_PARAMS > "$PROJECT_DIR/logs/gem5_idct_scalar_o3.log" 2>&1

# 2. Run IDCT NEON simulation
echo -e "\n[2/3] Running IDCT NEON 128-bit O3CPU..."
time "$GEM5_OPT" --outdir="$PROJECT_DIR/m5out_idct_neon_o3" "$GEM5_CONFIG" \
  --cmd="$PROJECT_DIR/src/idct_neon.aarch64" \
  $O3_PARAMS > "$PROJECT_DIR/logs/gem5_idct_neon_o3.log" 2>&1

# 3. Run IDCT SVE2 simulation
echo -e "\n[3/3] Running IDCT SVE2 256-bit O3CPU..."
time "$GEM5_OPT" --outdir="$PROJECT_DIR/m5out_idct_sve2_o3" "$GEM5_CONFIG" \
  --cmd="$PROJECT_DIR/src/idct_sve2.aarch64" \
  $O3_PARAMS \
  --param 'system.cpu[:].isa[:].sve_vl_se = 2' \
  > "$PROJECT_DIR/logs/gem5_idct_sve2_o3.log" 2>&1

echo -e "\n[4/4] Parsing ArmO3CPU IDCT stats.txt results..."
PROJECT_DIR="$PROJECT_DIR" python3 - <<'EOF'
import json
import os

PROJECT_DIR = os.environ["PROJECT_DIR"]

def parse_stat(path, key):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            if key in line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return float(parts[1])
                    except ValueError:
                        pass
    return None

results = {}
for mode in ['scalar', 'neon', 'sve2']:
    path = f"{PROJECT_DIR}/m5out_idct_{mode}_o3/stats.txt"
    if not os.path.exists(path):
        # Local fallback if directory structured differently
        path = f"m5out_idct_{mode}_o3/stats.txt"
        
    sim_seconds = parse_stat(path, 'simSeconds')
    num_cycles = parse_stat(path, 'system.cpu.numCycles')
    committed_insts = parse_stat(path, 'system.cpu.commitStats0.numInsts')
    
    if num_cycles and committed_insts:
        ipc = round(committed_insts / num_cycles, 3)
    else:
        ipc = None
        
    results[mode] = {
        'simSeconds': sim_seconds,
        'numCycles': num_cycles,
        'committedInsts': committed_insts,
        'ipc': ipc
    }

out_json = f"{PROJECT_DIR}/results/gem5_o3cpu_idct_results.json"
with open(out_json, 'w') as f:
    json.dump(results, f, indent=2)

print("\n=== Parsed IDCT Results Summary ===")
print(json.dumps(results, indent=2))
print(f"Results written to: {out_json}")
EOF

echo -e "\nIDCT Simulation process completed successfully!"
