#!/usr/bin/env python3
"""
verify_leakage_model.py — 漏電模型驗證腳本

驗證項目：
1. RESEARCH_REPORT.md 宣稱的「漏電使穩態功耗上升 42%」是否正確
2. 各溫度下的實際漏電增幅計算
3. 有/無漏電模型的溫度差異精確量化

輸出：
- 終端驗證報告
- results/leakage_verification.json — 完整計算記錄
"""

import json
import math
from pathlib import Path

# ===========================================================================
# 漏電模型參數（與 thermal_governor.py 完全一致）
# ===========================================================================
LEAK_RATIO_REF = 0.30    # 參考溫度下漏電占總功耗比例
T_LEAK_REF     = 40.0    # 參考溫度 (°C)
LEAK_COEFF     = 0.035   # 溫度係數 (1/°C)


def power_with_leakage(base_power, temp):
    """與 thermal_governor.py 相同的漏電功耗公式"""
    p_dynamic = base_power * (1.0 - LEAK_RATIO_REF)
    temp_capped = min(temp, 100.0)
    p_leak = base_power * LEAK_RATIO_REF * math.exp(LEAK_COEFF * (temp_capped - T_LEAK_REF))
    return p_dynamic + p_leak


def power_no_leakage(base_power):
    """無漏電模型（V1）"""
    return base_power


# ===========================================================================
# 驗證 1：各溫度下的漏電增幅
# ===========================================================================
def verify_leakage_amplification():
    print("=" * 80)
    print(" 驗證 1：各溫度下的漏電增幅詳細計算")
    print("=" * 80)

    base_power = 4.5  # 3.30 GHz OPP 功耗
    temps = [25, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 100]

    print(f"\n  基礎功耗（OPP）= {base_power} W")
    print(f"  P_dynamic = {base_power} × (1 - {LEAK_RATIO_REF}) = {base_power * (1 - LEAK_RATIO_REF):.3f} W（恆定）")
    print(f"  P_leak(T) = {base_power} × {LEAK_RATIO_REF} × exp({LEAK_COEFF} × (T - {T_LEAK_REF}))")
    print()

    print(f"  {'溫度':>6} {'P_dynamic':>12} {'P_leak(T)':>12} {'P_total':>12} {'增幅':>8} {'漏電占比':>10}")
    print("  " + "-" * 68)

    results = []
    for t in temps:
        p_total = power_with_leakage(base_power, t)
        p_dynamic = base_power * (1 - LEAK_RATIO_REF)
        p_leak = p_total - p_dynamic
        amplification = (p_total - base_power) / base_power * 100
        leak_ratio = p_leak / p_total * 100

        results.append({
            'temp': t,
            'p_dynamic': round(p_dynamic, 4),
            'p_leak': round(p_leak, 4),
            'p_total': round(p_total, 4),
            'amplification_pct': round(amplification, 2),
            'leak_ratio_pct': round(leak_ratio, 2),
        })

        print(f"  {t:>5}°C {p_dynamic:>11.3f}W {p_leak:>11.3f}W {p_total:>11.3f}W {amplification:>+7.1f}% {leak_ratio:>9.1f}%")

    return results


# ===========================================================================
# 驗證 2：RESEARCH_REPORT 宣稱的 42% 增幅
# ===========================================================================
def verify_42_percent_claim():
    print("\n" + "=" * 80)
    print(" 驗證 2：RESEARCH_REPORT 宣稱「穩態功耗上升 42%」")
    print("=" * 80)

    base_power = 4.5  # SVE2 aggressive @ 3.30 GHz

    print("\n  RESEARCH_REPORT.md L103 原文：")
    print('  「有漏電模型 (V2) 相比動態功耗單一模型 (V1) 使...穩態功耗上升了約 42%」')
    print()

    # 在不同解讀下計算
    print("  === 解讀 A：「42%」指的是在某個中間溫度的增幅 ===")
    for t in [60, 65, 70, 75]:
        p_total = power_with_leakage(base_power, t)
        amp = (p_total - base_power) / base_power * 100
        print(f"    T={t}°C: P_total={p_total:.3f}W, 增幅={amp:.1f}%")
        if abs(amp - 42) < 3:
            print(f"    ⬆️  T={t}°C 的增幅 ≈ 42%，可能是報告的參考溫度點")

    print()
    print("  === 解讀 B：「42%」指的是漏電「額外增加的功耗」占動態功耗的比例 ===")
    # 在穩態峰值溫度（~90°C）計算
    p_at_90 = power_with_leakage(base_power, 90)
    p_dynamic = base_power * (1 - LEAK_RATIO_REF)
    p_leak_90 = p_at_90 - p_dynamic
    ratio_to_dynamic = (p_leak_90 - base_power * LEAK_RATIO_REF) / p_dynamic * 100
    print(f"    T=90°C: P_leak={p_leak_90:.3f}W, P_dynamic={p_dynamic:.3f}W")
    print(f"    漏電增量占動態功耗比例 = {ratio_to_dynamic:.1f}%")

    print()
    print("  === 解讀 C：「42%」指的是峰值溫度差異的百分比 ===")
    # 如果是指溫度差異：V2 峰值 90.79°C vs V1 峰值（無漏電）
    # 需要實際跑模擬才知道
    print("    需要實際比對有/無漏電模型的峰值溫度差異")
    print("    （見步驟 3 的模擬比對結果）")

    print()
    print("  === 結論 ===")
    print("  在 90°C 峰值溫度下，漏電使總功耗相比基準增加了：")
    p_at_90_total = power_with_leakage(base_power, 90)
    total_amp = (p_at_90_total - base_power) / base_power * 100
    print(f"    (P_total - P_base) / P_base = ({p_at_90_total:.3f} - {base_power}) / {base_power} = {total_amp:.1f}%")
    print(f"    這遠大於報告宣稱的 42%。")
    print()
    print("  可能的合理解讀：")
    print(f"    在 T≈65°C 時增幅約 42%，報告可能指的是平均溫度下的增幅，")
    print(f"    而非峰值溫度下的增幅。建議在報告中明確標註參考溫度。")


# ===========================================================================
# 驗證 3：模擬比對 — 有/無漏電的溫度差異
# ===========================================================================
def simulate_leakage_comparison():
    print("\n" + "=" * 80)
    print(" 驗證 3：有/無漏電模型的模擬結果比對")
    print("=" * 80)

    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    try:
        import thermal_governor as tg
    except ImportError:
        print("  ❌ 無法匯入 thermal_governor.py")
        return None

    tg.load_ipc_profile('brightness')

    modes = ['sve2_aggressive', 'sve2_balanced', 'sve2_predictive']

    print(f"\n  {'模式':<22} {'有漏電峰溫':>12} {'無漏電峰溫':>12} {'溫差':>8} {'有漏電能耗':>12} {'無漏電能耗':>12} {'能耗增幅':>10}")
    print("  " + "-" * 90)

    comparison = []
    for mode in modes:
        r_leak = tg.simulate(mode, enable_leakage=True)
        r_noleak = tg.simulate(mode, enable_leakage=False)

        temp_diff = r_leak['max_temp'] - r_noleak['max_temp']
        energy_amp = (r_leak['energy'] - r_noleak['energy']) / r_noleak['energy'] * 100

        comparison.append({
            'mode': mode,
            'leak_max_temp': round(r_leak['max_temp'], 2),
            'noleak_max_temp': round(r_noleak['max_temp'], 2),
            'temp_diff': round(temp_diff, 2),
            'leak_energy': round(r_leak['energy'], 1),
            'noleak_energy': round(r_noleak['energy'], 1),
            'energy_amplification_pct': round(energy_amp, 1),
        })

        print(f"  {mode:<22} {r_leak['max_temp']:>11.2f}°C {r_noleak['max_temp']:>11.2f}°C {temp_diff:>+7.2f}°C {r_leak['energy']:>11.1f}J {r_noleak['energy']:>11.1f}J {energy_amp:>+9.1f}%")

    print()
    print("  解讀：")
    agg = [c for c in comparison if c['mode'] == 'sve2_aggressive'][0]
    print(f"  sve2_aggressive 的漏電使峰值溫度額外推高了 {agg['temp_diff']:.2f}°C")
    print(f"  sve2_aggressive 的漏電使總能耗增加了 {agg['energy_amplification_pct']:.1f}%")
    print(f"  → RESEARCH_REPORT 宣稱「溫度額外推高 5.5°C」→ 實際 {agg['temp_diff']:.2f}°C")
    print(f"  → RESEARCH_REPORT 宣稱「穩態功耗上升 42%」→ 實際能耗增幅 {agg['energy_amplification_pct']:.1f}%")

    return comparison


# ===========================================================================
# 主程式
# ===========================================================================
if __name__ == '__main__':
    print("🔬 ARM Thermal Research — 漏電模型驗證報告")
    print("=" * 80)

    amp_results = verify_leakage_amplification()
    verify_42_percent_claim()
    comparison = simulate_leakage_comparison()

    # 儲存完整驗證結果
    out_dir = Path(__file__).parent / '../results'
    out_dir.mkdir(parents=True, exist_ok=True)

    verification_data = {
        'leakage_amplification_by_temperature': amp_results,
        'simulation_comparison': comparison,
        'model_parameters': {
            'LEAK_RATIO_REF': LEAK_RATIO_REF,
            'T_LEAK_REF': T_LEAK_REF,
            'LEAK_COEFF': LEAK_COEFF,
        },
        'conclusion': (
            '報告宣稱的 42% 增幅在約 65°C 時成立，'
            '但在峰值溫度 90°C 下實際增幅遠大於此。'
            '建議修正報告，明確標註參考溫度或使用時間平均增幅。'
        ),
    }

    json_path = out_dir / 'leakage_verification.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(verification_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 驗證結果已儲存至 {json_path}")
