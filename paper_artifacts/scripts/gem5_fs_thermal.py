# Copyright (c) 2026 ARM Thermal Research Project
# All rights reserved.
#
# This configuration file extends the ARM big.LITTLE(tm) FS example
# with power models, a Cauer 2-node RC thermal network, and DVFS support.
#
# Based on gem5's official fs_power.py and fs_bigLITTLE.py examples.
# Reference: gem5/src/sim/power/ThermalModel.py, ThermalDomain.py,
#            DVFSHandler.py, MathExprPowerModel.py

import argparse
import os
import sys

import fs_bigLITTLE as bL

import m5
from m5.objects import (
    MathExprPowerModel,
    PowerModel,
    ThermalCapacitor,
    ThermalDomain,
    ThermalModel,
    ThermalNode,
    ThermalReference,
    ThermalResistor,
)


# ============================================================
# Power Models: Big Core (Cortex-X4 class)
# ============================================================

class BigCorePowerOn(MathExprPowerModel):
    """Dynamic + static power model for big cores in ON state.

    Dynamic power: P_dyn ∝ V² × (activity factor from IPC + cache misses)
    Static power:  P_leak ∝ (T/T_ref)² — simplified quadratic leakage model
    """
    def __init__(self, cpu_path, **kwargs):
        super().__init__(**kwargs)
        # Dynamic power: voltage² × activity factor (IPC-based)
        # Using only IPC avoids cumulative stat / simSeconds division
        # which produces garbage values after checkpoint restoration.
        # Constants tuned to produce ~2-5W under typical workloads.
        self.dyn = (
            "voltage * voltage * 3.0 * {cpu}.ipc"
        ).format(cpu=cpu_path)
        # Static power: temperature-dependent leakage (quadratic approx)
        # At 25°C (298K): ~0.1W, at 85°C (358K): ~0.14W
        self.st = "0.1 * (temp / 300) * (temp / 300)"


class BigCorePowerOff(MathExprPowerModel):
    """Zero power for inactive states (CLK_GATED, SRAM_RETENTION, OFF)."""
    dyn = "0"
    st = "0"


class BigCorePowerModel(PowerModel):
    """Per-state power model for big cores."""
    def __init__(self, cpu_path, **kwargs):
        super().__init__(**kwargs)
        self.pm = [
            BigCorePowerOn(cpu_path),   # ON
            BigCorePowerOff(),          # CLK_GATED
            BigCorePowerOff(),          # SRAM_RETENTION
            BigCorePowerOff(),          # OFF
        ]


# ============================================================
# Power Models: Little Core (Cortex-A720 class)
# ============================================================

class LittleCorePowerOn(MathExprPowerModel):
    """Dynamic + static power model for little cores in ON state.

    Lower coefficients than big cores (~0.5-2W typical).
    """
    def __init__(self, cpu_path, **kwargs):
        super().__init__(**kwargs)
        # Lower activity factor than big cores (~0.5-2W typical)
        self.dyn = (
            "voltage * 1.5 * {cpu}.ipc"
        ).format(cpu=cpu_path)
        self.st = "0.05 * (temp / 300) * (temp / 300)"


class LittleCorePowerOff(MathExprPowerModel):
    dyn = "0"
    st = "0"


class LittleCorePowerModel(PowerModel):
    def __init__(self, cpu_path, **kwargs):
        super().__init__(**kwargs)
        self.pm = [
            LittleCorePowerOn(cpu_path),   # ON
            LittleCorePowerOff(),           # CLK_GATED
            LittleCorePowerOff(),           # SRAM_RETENTION
            LittleCorePowerOff(),           # OFF
        ]


# ============================================================
# Power Models: L2 Cache
# ============================================================

class L2PowerOn(MathExprPowerModel):
    """L2 cache power based on access count."""
    def __init__(self, l2_path, **kwargs):
        super().__init__(**kwargs)
        self.dyn = f"{l2_path}.overallAccesses * 0.000018000"
        self.st = "(voltage * 3) / 10"


class L2PowerOff(MathExprPowerModel):
    dyn = "0"
    st = "0"


class L2PowerModel(PowerModel):
    def __init__(self, l2_path, **kwargs):
        super().__init__(**kwargs)
        self.pm = [
            L2PowerOn(l2_path),    # ON
            L2PowerOff(),          # CLK_GATED
            L2PowerOff(),          # SRAM_RETENTION
            L2PowerOff(),          # OFF
        ]


# ============================================================
# Configuration Functions
# ============================================================

def addThermalOptions(parser):
    """Add thermal simulation-specific command line options."""
    parser.add_argument(
        "--thermal-step", type=float, default=0.01,
        help="Thermal simulation step in seconds (default: 10ms)")
    parser.add_argument(
        "--ambient-temp", type=str, default="25C",
        help="Ambient temperature (default: 25C)")
    parser.add_argument(
        "--r-die-pkg", type=float, default=5.0,
        help="Die-to-package thermal resistance in K/W (default: 5.0)")
    parser.add_argument(
        "--r-pkg-amb", type=float, default=10.0,
        help="Package-to-ambient thermal resistance in K/W (default: 10.0)")
    parser.add_argument(
        "--c-die", type=float, default=1.0,
        help="Die thermal capacitance in J/K (default: 1.0)")
    parser.add_argument(
        "--c-pkg", type=float, default=5.0,
        help="Package thermal capacitance in J/K (default: 5.0)")
    parser.add_argument(
        "--stats-period", type=float, default=0.0001,
        help="Stats dump period in seconds (default: 100us = 0.0001s)")
    parser.add_argument(
        "--no-dvfs", action="store_true", default=False,
        help="Disable DVFS handler")
    parser.add_argument(
        "--enable-3node", action="store_true", default=False,
        help="Enable 3-node Cauer network (die, package, heatsink)")
    parser.add_argument(
        "--r-pkg-hs", type=float, default=2.0,
        help="Package-to-heatsink thermal resistance in K/W")
    parser.add_argument(
        "--r-hs-amb", type=float, default=8.0,
        help="Heatsink-to-ambient thermal resistance in K/W")
    parser.add_argument(
        "--c-hs", type=float, default=15.0,
        help="Heatsink thermal capacitance in J/K")


def setupDVFS(system):
    """Reconfigure cluster clock/voltage domains for multi-OPP DVFS.

    Big cluster OPP table (Cortex-X4 class):
      Level 0: 3.3 GHz @ 1.2V  (boost)
      Level 1: 3.0 GHz @ 1.1V
      Level 2: 2.8 GHz @ 1.0V
      Level 3: 2.4 GHz @ 0.9V
      Level 4: 2.0 GHz @ 0.8V  (efficiency)

    Little cluster OPP table (Cortex-A720 class):
      Level 0: 2.0 GHz @ 0.9V
      Level 1: 1.5 GHz @ 0.85V
      Level 2: 1.0 GHz @ 0.8V
    """
    dvfs_domains = []

    if hasattr(system, 'bigCluster'):
        system.bigCluster.clk_domain.domain_id = 0
        system.bigCluster.voltage_domain.voltage = [
            '1.2V', '1.1V', '1.0V', '0.9V', '0.8V'
        ]
        system.bigCluster.clk_domain.clock = [
            '3300MHz', '3000MHz', '2800MHz', '2400MHz', '2000MHz'
        ]
        dvfs_domains.append(system.bigCluster.clk_domain)

    if hasattr(system, 'littleCluster'):
        system.littleCluster.clk_domain.domain_id = 1
        system.littleCluster.voltage_domain.voltage = [
            '0.9V', '0.85V', '0.8V'
        ]
        system.littleCluster.clk_domain.clock = [
            '2000MHz', '1500MHz', '1000MHz'
        ]
        dvfs_domains.append(system.littleCluster.clk_domain)

    system.dvfs_handler.domains = dvfs_domains
    system.dvfs_handler.enable = True
    system.dvfs_handler.transition_latency = '100us'


def setupPowerModels(system):
    """Attach power models to CPUs and L2 caches.

    Big cluster CPUs get BigCorePowerModel,
    Little cluster CPUs get LittleCorePowerModel.
    The big cluster's L2 cache gets an L2PowerModel.
    """
    # Big cluster CPUs
    if hasattr(system, 'bigCluster'):
        for cpu in system.bigCluster.cpus:
            cpu.power_state.default_state = "ON"
            cpu.power_model = BigCorePowerModel(cpu.path())

        # L2 cache of the big cluster
        if hasattr(system.bigCluster, 'l2'):
            for l2 in system.bigCluster.l2.descendants():
                if isinstance(l2, m5.objects.Cache):
                    l2.power_state.default_state = "ON"
                    l2.power_model = L2PowerModel(l2.path())

    # Little cluster CPUs
    if hasattr(system, 'littleCluster'):
        for cpu in system.littleCluster.cpus:
            cpu.power_state.default_state = "ON"
            cpu.power_model = LittleCorePowerModel(cpu.path())


def setupThermalModel(system, options):
    """Build a Cauer 2-node RC thermal network for the big cluster.

    Topology (Cauer model):

        Heat Source (P)
             |
        [ThermalDomain] --> node_die
             |                 |
           [C_die]          [R_die_pkg]
             |                 |
        node_amb(ref)     node_pkg
                              |                 |
                            [C_pkg]          [R_pkg_amb]
                              |                 |
                         node_amb(ref)     node_amb(ref)

    Cauer model: capacitors shunt to ground (ambient reference),
    resistors connect adjacent nodes in series.

    This produces physically meaningful transient behavior:
    - C_die represents the die's thermal mass
    - C_pkg represents the package/heatsink thermal mass
    - R_die_pkg is the die-to-package interface resistance
    - R_pkg_amb is the package-to-ambient convection resistance
    """
    # Create thermal domain for the big cluster heat source
    big_td = ThermalDomain(initial_temperature=options.ambient_temp)
    system.bigCluster.thermal_domain = big_td

    # Assemble the thermal model
    tm = ThermalModel(step=options.thermal_step)
    system.thermal_model = tm

    # Create thermal nodes and attach to tm so they show up in stats
    tm.node_die = ThermalNode()     # Die junction node
    tm.node_pkg = ThermalNode()     # Package surface node
    tm.node_amb = ThermalNode()     # Ambient environment node

    node_die = tm.node_die
    node_pkg = tm.node_pkg
    node_amb = tm.node_amb

    # Fixed-temperature ambient reference
    ambient_ref = ThermalReference(temperature=options.ambient_temp)

    # Thermal RC components
    R_die_pkg = ThermalResistor(resistance=options.r_die_pkg)
    C_die = ThermalCapacitor(capacitance=options.c_die)
    C_pkg = ThermalCapacitor(capacitance=options.c_pkg)

    if options.enable_3node:
        tm.node_hs = ThermalNode()
        node_hs = tm.node_hs
        R_pkg_hs = ThermalResistor(resistance=options.r_pkg_hs)
        R_hs_amb = ThermalResistor(resistance=options.r_hs_amb)
        C_hs = ThermalCapacitor(capacitance=options.c_hs)
    else:
        R_pkg_amb = ThermalResistor(resistance=options.r_pkg_amb)

    # 1. Heat source: big cluster power -> die node
    tm.addDomain(big_td, node_die)

    # 2. Series resistor: die -> package
    tm.addResistor(R_die_pkg, node_die, node_pkg)

    # 3. Shunt capacitor: die -> ambient (Cauer topology)
    tm.addCapacitor(C_die, node_die, node_amb)

    if options.enable_3node:
        # 4. Series resistor: package -> heatsink
        tm.addResistor(R_pkg_hs, node_pkg, node_hs)
        
        # 5. Shunt capacitor: package -> ambient
        tm.addCapacitor(C_pkg, node_pkg, node_amb)
        
        # 6. Series resistor: heatsink -> ambient
        tm.addResistor(R_hs_amb, node_hs, node_amb)
        
        # 7. Shunt capacitor: heatsink -> ambient
        tm.addCapacitor(C_hs, node_hs, node_amb)
    else:
        # 4. Series resistor: package -> ambient
        tm.addResistor(R_pkg_amb, node_pkg, node_amb)
    
        # 5. Shunt capacitor: package -> ambient
        tm.addCapacitor(C_pkg, node_pkg, node_amb)

    # 6/8. Fix ambient node temperature
    tm.addReference(ambient_ref, node_amb)


# ============================================================
# Main entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="ARM big.LITTLE FS configuration with integrated "
                    "power model, Cauer 2-node RC thermal network, "
                    "and multi-OPP DVFS handler."
    )
    bL.addOptions(parser)
    addThermalOptions(parser)
    options = parser.parse_args()

    if options.cpu_type != "timing":
        m5.util.fatal(
            "Thermal simulation requires 'timing' CPUs for meaningful "
            "IPC/cache statistics. Use --cpu-type timing."
        )

    # Build the base big.LITTLE system
    root = bL.build(options)

    # Setup DVFS with multi-OPP frequency/voltage tables
    if not options.no_dvfs:
        setupDVFS(root.system)

    # Setup power models for CPUs and L2 caches
    setupPowerModels(root.system)

    # Setup Cauer 2-node RC thermal network
    setupThermalModel(root.system, options)

    # Instantiate the simulation
    bL.instantiate(options)

    # Print configuration summary
    print("=" * 70)
    print("gem5 FS Thermal Simulation Configuration")
    print("=" * 70)
    print(f"  Thermal step:    {options.thermal_step}s")
    print(f"  Ambient temp:    {options.ambient_temp}")
    print(f"  R_die_pkg:       {options.r_die_pkg} K/W")
    print(f"  R_pkg_amb:       {options.r_pkg_amb} K/W")
    print(f"  C_die:           {options.c_die} J/K")
    print(f"  C_pkg:           {options.c_pkg} J/K")
    print(f"  DVFS:            {'disabled' if options.no_dvfs else 'enabled'}")
    print(f"  Stats period:    {options.stats_period}s")
    print("=" * 70)
    print("WARNING: Power numbers are illustrative examples.")
    print("They are NOT representative of any particular implementation.")
    print("=" * 70)

    # Dump stats periodically for thermal trace analysis
    m5.stats.periodicStatDump(m5.ticks.fromSeconds(options.stats_period))
    bL.run()


if __name__ == "__m5_main__":
    main()
