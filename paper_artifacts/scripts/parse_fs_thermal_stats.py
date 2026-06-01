#!/usr/bin/env python3
"""
parse_fs_thermal_stats.py - gem5 FS Thermal Simulation Stats Parser (v4)
See patches/thermal_node_temperature_stat.patch for required gem5 C++ changes.
v4: supports actual patched gem5 stat paths (thermal_components0/2/4).
    Actual paths confirmed from m5out_3node_validate/config.ini (2026-05-29):
      components00=ThermalNode(die), 02=ThermalNode(pkg), 04=ThermalNode(hs),
      06=ThermalNode(amb). stats.txt uses unpadded indices 0, 2, 4, 6.
    Falls back to old designed paths if actual paths not present.
"""
import re, os, sys, json
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

TICK_FREQ = 1e12

def _to_celsius(raw):
    if raw is None: return None
    return raw - 273.15 if raw > 200.0 else raw

def parse_stats(stats_file):
    print(f"Parsing stats file: {stats_file}")
    if not os.path.exists(stats_file):
        print(f"Error: {stats_file} does not exist!"); return None
    begin_pat      = re.compile(r"---------- Begin Simulation Statistics ----------")
    final_tick_pat = re.compile(r"finalTick\s+([\d]+)")
    dyn_power_pat  = re.compile(r"system\.bigCluster\.cpus\.power_model\.dynamicPower\s+([\d\.e\-+]+)")
    st_power_pat   = re.compile(r"system\.bigCluster\.cpus\.power_model\.staticPower\s+([\d\.e\-+]+)")
    # T_die: old path (2-node runs) OR new patched path (components0 = die node)
    temp_die_pat   = re.compile(
        r"(?:system\.bigCluster\.thermal_domain\.currentTemp"
        r"|system\.thermal_components0\.temperature)\s+([\d\.e\-+]+)")
    # T_pkg / T_hs: new patched paths (confirmed from m5out_3node_validate config.ini)
    #   Fallback old designed paths kept for compatibility with any future rename.
    temp_pkg_pat   = re.compile(
        r"(?:system\.thermal_components2\.temperature"
        r"|system\.thermal_model\.node_pkg\.temperature)\s+([\d\.e\-+]+)")
    temp_hs_pat    = re.compile(
        r"(?:system\.thermal_components4\.temperature"
        r"|system\.thermal_model\.node_hs\.temperature)\s+([\d\.e\-+]+)")
    clock_pat      = re.compile(r"system\.bigCluster\.clk_domain\.clock\s+([\d\.e\-+]+)")
    ipc_pat        = re.compile(r"system\.bigCluster\.cpus\.ipc\s+([\d\.e\-+]+)")
    time_series = []; current_stat = {}; count = 0
    with open(stats_file, 'r') as f:
        for line in f:
            if begin_pat.search(line):
                if current_stat and 'final_tick' in current_stat: time_series.append(current_stat)
                current_stat = {}; count += 1; continue
            for pat, key, conv in [
                (final_tick_pat, 'final_tick',  lambda v: int(v)),
                (temp_die_pat,   'temp_die',    lambda v: _to_celsius(float(v))),
                (temp_pkg_pat,   'temp_pkg',    lambda v: _to_celsius(float(v))),
                (temp_hs_pat,    'temp_hs',     lambda v: _to_celsius(float(v))),
                (dyn_power_pat,  'dyn_power_W', lambda v: float(v)),
                (st_power_pat,   'st_power_W',  lambda v: float(v)),
                (ipc_pat,        'ipc',         lambda v: float(v)),
            ]:
                m = pat.search(line)
                if m:
                    try: current_stat[key] = conv(m.group(1))
                    except (ValueError, TypeError): current_stat[key] = None
                    break
            m = clock_pat.search(line)
            if m:
                try:
                    p = float(m.group(1)); current_stat['freq_GHz'] = (TICK_FREQ/p)/1e9 if p>0 else 0.0
                except ValueError: current_stat['freq_GHz'] = None
    if current_stat and 'final_tick' in current_stat: time_series.append(current_stat)
    for d in time_series:
        if 'temp_die' in d and 'temp' not in d: d['temp'] = d['temp_die']
    has_pkg = any(d.get('temp_pkg') is not None for d in time_series)
    has_hs  = any(d.get('temp_hs')  is not None for d in time_series)
    mode = "3-node" if (has_pkg or has_hs) else "2-node"
    print(f"Parsed {len(time_series)} records from {count} dumps. Topology: {mode}.")
    return time_series

def plot_results(data, output_dir):
    if not data: print("No data to plot."); return
    tick0 = data[0]['final_tick']
    times_ms  = [(d['final_tick']-tick0)/(TICK_FREQ/1000) for d in data]
    temps_die = [d.get('temp_die') or d.get('temp',25.0) for d in data]
    temps_pkg = [d.get('temp_pkg') for d in data]
    temps_hs  = [d.get('temp_hs')  for d in data]
    dyn_W     = [d.get('dyn_power_W',0.0) for d in data]
    st_W      = [d.get('st_power_W',0.0)  for d in data]
    total_W   = [a+b for a,b in zip(dyn_W,st_W)]
    freqs     = [d.get('freq_GHz',3.3) for d in data]
    ipcs      = [d.get('ipc',0.0) for d in data]
    has_pkg   = any(v is not None for v in temps_pkg)
    has_hs    = any(v is not None for v in temps_hs)
    os.makedirs(output_dir, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    fig,ax = plt.subplots(figsize=(11,5))
    ax.plot(times_ms, temps_die, color='crimson', linewidth=2, label='T_die (big core junction)')
    if has_pkg:
        ax.plot(times_ms, [v if v is not None else float('nan') for v in temps_pkg],
                color='darkorange', linewidth=1.5, label='T_pkg (package node)')
    if has_hs:
        ax.plot(times_ms, [v if v is not None else float('nan') for v in temps_hs],
                color='steelblue', linewidth=1.5, label='T_hs (heatsink node)')
    ax.axhline(25.0, color='gray', linestyle='--', alpha=0.6, label='Ambient (25 C)')
    ax.set_xlabel('Simulation Time (ms)', fontsize=12); ax.set_ylabel('Temperature (C)', fontsize=12)
    topology = "3-Node Cauer RC" if (has_pkg or has_hs) else "Cauer 2-Node RC"
    ax.set_title(f'gem5 FS: Big Core Transient Temperature ({topology})', fontsize=13, fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.5); ax.legend(fontsize=10); fig.tight_layout()
    fig.savefig(os.path.join(output_dir,'fs_temp_vs_time.png'), dpi=300); plt.close(fig)
    print(f"  Saved fs_temp_vs_time.png  (die range {min(temps_die):.3f}~{max(temps_die):.3f} C)")
    fig,ax = plt.subplots(figsize=(11,5))
    ax.plot(times_ms, dyn_W,  color='dodgerblue', linestyle='--', alpha=0.8, label='Dynamic Power (W)')
    ax.plot(times_ms, st_W,   color='orange',     linestyle=':',  alpha=0.8, label='Static Leakage (W)')
    ax.plot(times_ms, total_W,color='darkblue',   linewidth=2,               label='Total Power (W)')
    ax.set_xlabel('Simulation Time (ms)', fontsize=12); ax.set_ylabel('Power (W)', fontsize=12)
    ax.set_title('gem5 FS: Big Core Power Consumption', fontsize=13, fontweight='bold')
    ax.grid(True,linestyle='--',alpha=0.5); ax.legend(fontsize=10); fig.tight_layout()
    fig.savefig(os.path.join(output_dir,'fs_power_vs_time.png'), dpi=300); plt.close(fig)
    print(f"  Saved fs_power_vs_time.png  (peak dyn {max(dyn_W):.3f} W)")
    fig,ax = plt.subplots(figsize=(11,5))
    ax.step(times_ms, freqs, where='post', color='darkgreen', linewidth=2, label='Big Core Freq (GHz)')
    ax.set_ylim([0,4.0]); ax.set_xlabel('Simulation Time (ms)', fontsize=12)
    ax.set_ylabel('Frequency (GHz)', fontsize=12)
    ax.set_title('gem5 FS: DVFS Frequency Scaling History', fontsize=13, fontweight='bold')
    ax.grid(True,linestyle='--',alpha=0.5); ax.legend(fontsize=10); fig.tight_layout()
    fig.savefig(os.path.join(output_dir,'fs_frequency_vs_time.png'), dpi=300); plt.close(fig)
    if any(d.get('ipc') is not None for d in data):
        fig,ax = plt.subplots(figsize=(11,5))
        ax.plot(times_ms, ipcs, color='purple', linewidth=2, label='Big Core IPC')
        ax.set_xlabel('Simulation Time (ms)', fontsize=12); ax.set_ylabel('IPC', fontsize=12)
        ax.set_title('gem5 FS: Big Core IPC Over Time', fontsize=13, fontweight='bold')
        ax.grid(True,linestyle='--',alpha=0.5); ax.legend(fontsize=10); fig.tight_layout()
        fig.savefig(os.path.join(output_dir,'fs_ipc_vs_time.png'), dpi=300); plt.close(fig)
    out_json = os.path.join(output_dir,'fs_simulation_results.json')
    export = [{'index':i,'time_ms':times_ms[i],'final_tick':d['final_tick'],
               'temp_die_C':d.get('temp_die') or d.get('temp'),'temp_pkg_C':d.get('temp_pkg'),
               'temp_hs_C':d.get('temp_hs'),'dyn_power_W':d.get('dyn_power_W'),
               'st_power_W':d.get('st_power_W'),'freq_GHz':d.get('freq_GHz'),'ipc':d.get('ipc')}
              for i,d in enumerate(data)]
    with open(out_json,'w') as f: json.dump(export,f,indent=2)
    print(f"  Saved {out_json}  ({len(export)} records)")

if __name__ == '__main__':
    stats_path = "m5out_fs_thermal/stats.txt"
    out_dir    = "results/phase5"
    if len(sys.argv) > 1: stats_path = sys.argv[1]
    if len(sys.argv) > 2: out_dir = sys.argv[2]
    data = parse_stats(stats_path)
    if data:
        plot_results(data, out_dir)
        print("\nDone! Check results in:", out_dir)
