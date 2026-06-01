from __future__ import annotations

import base64
import os
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", SCRIPT_DIR.parent))
BINARY_PATH = Path(
    os.environ.get("BINARY_PATH", PROJECT_DIR / "src" / "neon_gem5.aarch64")
)
OUTPUT_RCS = Path(
    os.environ.get("OUTPUT_RCS", SCRIPT_DIR / "run_workload.rcS")
)


def main() -> int:
    if not BINARY_PATH.exists():
        print(f"Error: {BINARY_PATH} not found!")
        return 1

    binary_data = BINARY_PATH.read_bytes()
    b64_str = base64.b64encode(binary_data).decode("utf-8")

    rcs_content = f"""#!/bin/bash
# ============================================================
# run_workload.rcS ??gem5 FS Workload Script
# ============================================================

echo "=========================================="
echo "Starting Guest Benchmark Execution"
echo "=========================================="

echo "Decoding NEON benchmark..."
cat << 'EOF' | base64 -d > /tmp/neon_gem5.aarch64
{b64_str}
EOF

chmod +x /tmp/neon_gem5.aarch64

echo "Running NEON benchmark on Big Core (CPU 0)..."
taskset -c 0 /tmp/neon_gem5.aarch64

echo "=========================================="
echo "Benchmark completed. Exiting simulation."
echo "=========================================="
"""

    OUTPUT_RCS.write_text(rcs_content, encoding="utf-8")
    print(f"Successfully generated {OUTPUT_RCS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
