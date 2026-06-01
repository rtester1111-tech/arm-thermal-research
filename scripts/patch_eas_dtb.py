#!/usr/bin/env python3
"""
patch_eas_dtb.py — Inject EAS (Energy-Aware Scheduler) properties into
gem5-generated DTB for big.LITTLE task-migration research.

Background
----------
gem5's auto-generated DTB for the VExpress_GEM5_Foundation machine does not
include the properties that Linux's EAS engine requires:
  • capacity-dmips-mhz   — relative compute capacity per CPU
  • dynamic-power-coefficient — mW/MHz at (voltage)² = 1 V²
  • operating-points-v2  — per-OPP frequency/voltage/power table

This script:
  1. Decompiles the input DTB to DTS text (requires `dtc` ≥ 1.5)
  2. Inserts/replaces EAS properties in the two CPU nodes
  3. Appends OPP tables and a CPU capacity-state table
  4. Recompiles to a patched DTB

Usage
-----
  python3 patch_eas_dtb.py [--input <base.dtb>] [--output <eas.dtb>]

Defaults:
  input  = m5out_fs_thermal_v2/system.dtb
  output = m5out_phase6/eas_patched.dtb
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile


# ─────────────────────────────────────────────────────────────────────────────
# EAS configuration: Cortex-X4 big core vs Cortex-A720 little core
#
# Power formula: P_dyn [µW] = coeff × (V² relative to 1V) × freq_MHz
#   big   coeff = 450  (Cortex-X4 class, normalised)
#   little coeff = 120 (Cortex-A720 class, ~3.75× more efficient)
#
# Capacity: proportional to DMIPS/MHz (IPC × IPC_ref)
#   big   → 1024 (EAS reference value, normalised ceiling)
#   little → 540  (≈ 53% of big core, typical A-vs-X ratio)
# ─────────────────────────────────────────────────────────────────────────────

BIG_CAPACITY_DMIPS_MHZ   = 1024
BIG_DYN_POWER_COEFF      = 450    # mW/MHz at 1 V²

LITTLE_CAPACITY_DMIPS_MHZ = 540
LITTLE_DYN_POWER_COEFF    = 120

# OPP tables: (freq_hz, voltage_µV, power_µW)
# P_dyn = coeff × (V_µV / 1_000_000)² × (freq_Hz / 1_000_000)
def _opp(coeff, freq_hz, v_uv):
    v = v_uv / 1e6
    f_mhz = freq_hz / 1e6
    return int(coeff * v * v * f_mhz * 1000)   # µW

BIG_OPPS = [
    (3_300_000_000, 1_200_000),   # 3.3 GHz @ 1.2 V (boost)
    (3_000_000_000, 1_100_000),   # 3.0 GHz @ 1.1 V
    (2_800_000_000, 1_000_000),   # 2.8 GHz @ 1.0 V
    (2_400_000_000,   900_000),   # 2.4 GHz @ 0.9 V
    (2_000_000_000,   800_000),   # 2.0 GHz @ 0.8 V (efficiency)
]

LITTLE_OPPS = [
    (2_000_000_000,   900_000),   # 2.0 GHz @ 0.9 V
    (1_500_000_000,   850_000),   # 1.5 GHz @ 0.85 V
    (1_000_000_000,   800_000),   # 1.0 GHz @ 0.8 V
]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"[ERROR] {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    return r.stdout


def decompile_dtb(dtb_path):
    """Return DTS text for the given DTB file."""
    return run(["dtc", "-I", "dtb", "-O", "dts", "-q", dtb_path])


def compile_dts(dts_text, out_path):
    """Compile DTS text → DTB at out_path."""
    with tempfile.NamedTemporaryFile(suffix=".dts", mode='w', delete=False) as f:
        f.write(dts_text)
        tmp = f.name
    try:
        run(["dtc", "-I", "dts", "-O", "dtb", "-q", "-o", out_path, tmp])
    finally:
        os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# OPP table DTS snippets
# ─────────────────────────────────────────────────────────────────────────────

def _opp_entry(freq_hz, v_uv, power_uw):
    return (
        f"\t\t\topp@{freq_hz} {{\n"
        f"\t\t\t\topp-hz = /bits/ 64 <{freq_hz}>;\n"
        f"\t\t\t\topp-microvolt = <{v_uv}>;\n"
        f"\t\t\t\topp-microwatt = <{power_uw}>;\n"
        f"\t\t\t}};\n"
    )


def big_opp_table():
    entries = "".join(
        _opp_entry(f, v, _opp(BIG_DYN_POWER_COEFF, f, v))
        for f, v in BIG_OPPS
    )
    return (
        "\tbig_opp_table: opp-table-big {\n"
        "\t\tcompatible = \"operating-points-v2\";\n"
        "\t\topp-shared;\n"
        f"{entries}"
        "\t};\n"
    )


def little_opp_table():
    entries = "".join(
        _opp_entry(f, v, _opp(LITTLE_DYN_POWER_COEFF, f, v))
        for f, v in LITTLE_OPPS
    )
    return (
        "\tlittle_opp_table: opp-table-little {\n"
        "\t\tcompatible = \"operating-points-v2\";\n"
        "\t\topp-shared;\n"
        f"{entries}"
        "\t};\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Patch helpers
# ─────────────────────────────────────────────────────────────────────────────

def inject_cpu_eas_props(dts, cpu_reg, capacity, dyn_coeff, opp_label):
    """
    Inject EAS properties into the cpu@<cpu_reg> node.
    cpu_reg is a hex string like "0" (big) or "101" (little).
    """
    # Match the cpu node opening brace
    pattern = re.compile(
        r"(cpu@" + re.escape(cpu_reg) + r"\s*\{[^}]*?)(phandle\s*=\s*<[^>]+>;)",
        re.DOTALL,
    )
    replacement = (
        r"\1"
        f"capacity-dmips-mhz = <{capacity}>;\n"
        f"\t\tdynamic-power-coefficient = <{dyn_coeff}>;\n"
        f"\t\toperating-points-v2 = <&{opp_label}>;\n"
        "\t\t"
        r"\2"
    )
    new_dts, n = pattern.subn(replacement, dts)
    if n == 0:
        print(f"[WARN] cpu@{cpu_reg} node not found — skipping EAS injection", file=sys.stderr)
    else:
        print(f"  [+] cpu@{cpu_reg}: capacity={capacity}, dyn_coeff={dyn_coeff}, opp={opp_label}")
    return new_dts


def insert_opp_tables(dts, big_opp, little_opp):
    """Insert OPP tables just before the closing brace of the root '/' node."""
    # Find the last closing brace (end of root node)
    # The DTS root ends with '};' after all child nodes
    insert_marker = "\n};"
    idx = dts.rfind(insert_marker)
    if idx < 0:
        print("[WARN] Could not find root node closing brace; appending OPP tables", file=sys.stderr)
        return dts + "\n" + big_opp + little_opp
    return dts[:idx] + "\n" + big_opp + little_opp + dts[idx:]


def patch_dts(dts):
    """Apply all EAS patches to the DTS text and return the patched version."""
    print("[*] Injecting EAS properties into big core (cpu@0)...")
    dts = inject_cpu_eas_props(dts, "0", BIG_CAPACITY_DMIPS_MHZ, BIG_DYN_POWER_COEFF, "big_opp_table")

    print("[*] Injecting EAS properties into little core (cpu@101)...")
    dts = inject_cpu_eas_props(dts, "101", LITTLE_CAPACITY_DMIPS_MHZ, LITTLE_DYN_POWER_COEFF, "little_opp_table")

    print("[*] Inserting OPP tables...")
    dts = insert_opp_tables(dts, big_opp_table(), little_opp_table())

    return dts


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input",  default="m5out_fs_thermal_v2/system.dtb",
                    help="Base DTB generated by gem5 (default: m5out_fs_thermal_v2/system.dtb)")
    ap.add_argument("--output", default="m5out_phase6/eas_patched.dtb",
                    help="Output path for EAS-patched DTB (default: m5out_phase6/eas_patched.dtb)")
    ap.add_argument("--dump-dts", action="store_true",
                    help="Also write the intermediate patched DTS to <output>.dts")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] Input DTB not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print(f"[*] Decompiling base DTB: {args.input}")
    dts = decompile_dtb(args.input)

    print(f"[*] Patching DTS with EAS properties...")
    patched = patch_dts(dts)

    if args.dump_dts:
        dts_out = args.output + ".dts"
        with open(dts_out, "w") as f:
            f.write(patched)
        print(f"[*] Intermediate DTS written: {dts_out}")

    print(f"[*] Compiling patched DTS → DTB: {args.output}")
    compile_dts(patched, args.output)

    print(f"\n[OK] EAS-patched DTB ready: {args.output}")
    print(f"     Big  core: capacity={BIG_CAPACITY_DMIPS_MHZ}, dyn_coeff={BIG_DYN_POWER_COEFF} mW/MHz@1V²")
    print(f"     Little core: capacity={LITTLE_CAPACITY_DMIPS_MHZ}, dyn_coeff={LITTLE_DYN_POWER_COEFF} mW/MHz@1V²")
    print(f"\n     Pass to gem5 with: --dtb {args.output}")
    print(f"     Or via fs_thermal.py:  --dtb {args.output}")


if __name__ == "__main__":
    main()
