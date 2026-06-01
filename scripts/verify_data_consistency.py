#!/usr/bin/env python3
"""
verify_data_consistency.py — 數據一致性驗證腳本

驗證項目：
1. thermal_simulation_v2.json 中的數據屬於哪個工作負載（Brightness or IDCT）
2. SVE2 模式在不同工作負載下結果是否合理
3. 重新生成兩種工作負載的完整結果供比對

輸出：驗證報告（終端輸出）+ 兩份工作負載的 JSON 數據
"""

import json
import math
import sys
from pathlib import Path

# 加入 scripts 目錄以便引入 thermal_governor
sys.path.insert(0, str(Path(__file__).parent))

# ===========================================================================
# 1. 分析現有 JSON 屬於哪個工作負載
# ===========================================================================
def analyze_existing_json():
    json_path = Path(__file__).parent / '../results/thermal_simulation_v2.json'
    if not json_path.exists():
        print("❌ thermal_simulation_v2.json 不存在")
        return

    with open(json_path) as f:
        data = json.load(f)

    print("=" * 80)
    print(" 步驟 1：分析 thermal_simulation_v2.json 的工作負載類型")
    print("=" * 80)

    scalar_fps = data['scalar']['avg_fps']
    print(f"\n  scalar avg_fps = {scalar_fps:.4f}")

    # Brightness IPC: scalar=0.833, sve2=1.000
    # FPS @ 1.2GHz = 60 × 0.32 × (0.833/1.000) = 15.9936
    brightness_expected = 60 * 0.32 * (0.833 / 1.000)

    # IDCT IPC: scalar=0.650, sve2=2.100
    # FPS @ 1.2GHz = 60 × 0.32 × (0.650/2.100) = 5.9429
    idct_expected = 60 * 0.32 * (0.650 / 2.100)

    print(f"  Brightness 預期 scalar FPS = {brightness_expected:.4f}")
    print(f"  IDCT 預期 scalar FPS       = {idct_expected:.4f}")

    brightness_match = abs(scalar_fps - brightness_expected) < 0.01
    idct_match = abs(scalar_fps - idct_expected) < 0.01

    if idct_match:
        print(f"\n  ✅ JSON 數據為 IDCT 工作負載結果")
        workload = 'idct'
    elif brightness_match:
        print(f"\n  ✅ JSON 數據為 Brightness 工作負載結果")
        workload = 'brightness'
    else:
        print(f"\n  ⚠️  無法確定工作負載類型（FPS 值不匹配任何預期值）")
        workload = 'unknown'

    return data, workload


# ===========================================================================
# 2. 檢查 SVE2 跨工作負載一致性問題
# ===========================================================================
def check_sve2_cross_workload():
    print("\n" + "=" * 80)
    print(" 步驟 2：SVE2 跨工作負載一致性分析")
    print("=" * 80)

    # 模擬公式：FPS = BASE_FPS × freq_mult × (ipc / IPC_SVE2) × intensity
    # 對 SVE2 模式：ipc = IPC_SVE2，所以 ipc/IPC_SVE2 = 1.0（恆等）
    # 這意味著 FPS 不受工作負載類型影響

    print("\n  FPS 公式分析：")
    print("  FPS = BASE_FPS × freq_mult × (ipc / IPC_SVE2) × intensity")
    print()

    workloads = {
        'brightness': {'scalar': 0.833, 'neon': 0.718, 'sve2': 1.000},
        'idct':       {'scalar': 0.650, 'neon': 1.250, 'sve2': 2.100},
    }

    for wl_name, ipcs in workloads.items():
        print(f"  【{wl_name.upper()} 工作負載】")
        for mode, ipc in ipcs.items():
            ratio = ipc / ipcs['sve2']
            print(f"    {mode:>8}: IPC={ipc:.3f}, IPC/IPC_SVE2={ratio:.4f}")
        print()

    print("  結論：")
    print("  - SVE2 模式的 ipc/IPC_SVE2 在任何工作負載下都 = 1.0000")
    print("  - 因此 SVE2 的 FPS 輸出完全不受工作負載類型影響")
    print("  - 功耗模型僅依賴頻率（OPP Table），也不隨工作負載改變")
    print("  - ⇒ SVE2 所有指標在不同工作負載下完全相同（這是模型設計限制）")
    print()

    print("  改進建議：")
    print("  方案 A：引入工作負載功耗因子（例如 IDCT 計算密集 → ALU 活動率更高）")
    print("           P_effective = P_opp × workload_power_factor")
    print("           workload_power_factor: brightness=1.00, idct=1.15")
    print("  方案 B：引入工作負載基礎 FPS 差異（不同核心的基礎處理能力不同）")
    print("           BASE_FPS_brightness = 60, BASE_FPS_idct = 45（IDCT 更重）")


# ===========================================================================
# 3. 雙工作負載完整比對
# ===========================================================================
def run_dual_workload_comparison():
    print("\n" + "=" * 80)
    print(" 步驟 3：雙工作負載模擬執行與比對")
    print("=" * 80)

    try:
        import thermal_governor as tg
    except ImportError:
        print("  ❌ 無法匯入 thermal_governor.py，請確認當前目錄")
        return

    modes = ['scalar', 'neon_aggressive', 'neon_balanced',
             'sve2_aggressive', 'sve2_balanced', 'sve2_gradual', 'sve2_predictive']

    results_by_workload = {}
    out_dir = Path(__file__).parent / '../results'

    for workload in ['brightness', 'idct']:
        tg.load_ipc_profile(workload)
        results = {}
        for mode in modes:
            results[mode] = tg.simulate(mode)
        results_by_workload[workload] = results

        # 儲存各工作負載 JSON
        json_path = out_dir / f'thermal_simulation_v2_{workload}.json'
        json_data = {
            m: {k: v for k, v in r.items() if k != 'time'}
            for m, r in results.items()
        }
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        print(f"\n  ✅ 儲存 {workload} 結果：{json_path}")

    # 比對表
    print("\n" + "-" * 100)
    print(f"  {'模式':<22} {'Brightness FPS':>15} {'IDCT FPS':>12} {'FPS 差異':>10} {'能耗不同?':>10} {'溫度不同?':>10}")
    print("-" * 100)

    for mode in modes:
        rb = results_by_workload['brightness'][mode]
        ri = results_by_workload['idct'][mode]
        fps_diff = rb['avg_fps'] - ri['avg_fps']
        energy_diff = "✅" if abs(rb['energy'] - ri['energy']) > 0.1 else "❌ (相同)"
        temp_diff = "✅" if abs(rb['max_temp'] - ri['max_temp']) > 0.1 else "❌ (相同)"
        print(f"  {mode:<22} {rb['avg_fps']:>15.2f} {ri['avg_fps']:>12.2f} {fps_diff:>+10.2f} {energy_diff:>10} {temp_diff:>10}")

    print("-" * 100)
    print("\n  解讀：")
    print("  - FPS 差異 > 0 表示 Brightness 的 FPS 更高（因為 IDCT 計算密集，fps_factor=0.70）")
    print("  - 能耗/溫度不同 = ✅ 代表功耗模型已成功導入 workload_power_factor，區分了計算密集與記憶體頻寬型負載")
    print("  - SVE2 的 FPS 差異不再為 0 = 說明 P2 順利導入 fps_factor，修正了 SVE2 跨負載結果相同的模型限制")


# ===========================================================================
# 4. RESEARCH_REPORT 宣稱數值交叉驗證
# ===========================================================================
def verify_report_claims():
    print("\n" + "=" * 80)
    print(" 步驟 4：RESEARCH_REPORT.md 宣稱數值驗證")
    print("=" * 80)

    # 報告宣稱的 Brightness 表格數值（RESEARCH_REPORT.md L92-L100）
    report_brightness = {
        'scalar':           {'avg_fps': 15.99, 'max_temp': 30.45, 'throttle': 0, 'energy': 109.0, 'edp': 6.81},
        'neon_aggressive':  {'avg_fps': 29.19, 'max_temp': 90.79, 'throttle': 10, 'energy': 1179.9, 'edp': 40.43},
        'neon_balanced':    {'avg_fps': 28.75, 'max_temp': 88.10, 'throttle': 4, 'energy': 1114.4, 'edp': 38.76},
        'sve2_aggressive':  {'avg_fps': 40.65, 'max_temp': 90.79, 'throttle': 10, 'energy': 1179.9, 'edp': 29.03},
        'sve2_balanced':    {'avg_fps': 40.04, 'max_temp': 88.10, 'throttle': 4, 'energy': 1114.4, 'edp': 27.83},
        'sve2_gradual':     {'avg_fps': 38.81, 'max_temp': 86.73, 'throttle': 5, 'energy': 1026.3, 'edp': 26.44},
        'sve2_predictive':  {'avg_fps': 40.67, 'max_temp': 88.03, 'throttle': 1, 'energy': 885.7, 'edp': 21.78},
    }

    try:
        import thermal_governor as tg
    except ImportError:
        print("  ❌ 無法匯入 thermal_governor.py")
        return

    # 使用 brightness IPC 重跑
    tg.load_ipc_profile('brightness')
    print("\n  使用 Brightness IPC 重新模擬並驗證報告數值...")

    all_pass = True
    for mode, expected in report_brightness.items():
        r = tg.simulate(mode)
        checks = []
        for key in ['avg_fps', 'max_temp', 'energy', 'edp']:
            actual = r[key]
            exp = expected[key]
            tol = 0.1 if key in ['avg_fps', 'edp'] else 0.5 if key == 'max_temp' else 1.0
            ok = abs(actual - exp) < tol
            checks.append((key, actual, exp, ok))
            if not ok:
                all_pass = False

        throttle_ok = r['throttle'] == expected['throttle']
        if not throttle_ok:
            all_pass = False

        status = "✅" if all(c[3] for c in checks) and throttle_ok else "❌"
        print(f"  {status} {mode}: ", end="")
        failed = [(k, a, e) for k, a, e, ok in checks if not ok]
        if not throttle_ok:
            failed.append(('throttle', r['throttle'], expected['throttle']))
        if failed:
            print(", ".join([f"{k}: 實際={a:.2f} vs 預期={e}" for k, a, e in failed]))
        else:
            print("所有數值匹配")

    print(f"\n  總結：{'✅ 所有報告數值驗證通過' if all_pass else '❌ 部分數值不匹配，需要調查'}")


# ===========================================================================
# 主程式
# ===========================================================================
if __name__ == '__main__':
    data, workload = analyze_existing_json()
    check_sve2_cross_workload()
    run_dual_workload_comparison()
    verify_report_claims()

    print("\n" + "=" * 80)
    print(" 驗證完成。結果摘要請見上方各步驟輸出。")
    print(" 詳細分析請參閱 QA_RESEARCH_LOG.md")
    print("=" * 80)
