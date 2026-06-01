# 期望 vs 實際：四方數值比較

## 設定

- Cauer 2-node RC thermal network
- `R_die_pkg = 5.0 K/W`, `R_pkg_amb = 10.0 K/W`
- `C_die = 1.0 J/K`, `C_pkg = 5.0 J/K`
- `T_ambient = 25.0°C (298.15 K)`
- CPU power：約 `3.0 W`（active workload）
- Backward Euler，`dt = 0.01 s`

---

## 比較表

| 指標 | Analytical (closed-form) | gem5 Original (buggy) | gem5 Patched | Python Solver (independent) |
|---|---|---|---|---|
| **Initial node_pkg temp** | 25°C | **0 K = −273.15°C** | 25°C | 0 K (Case A) / 25°C (Case B) |
| **Min junction temp** | 25.00°C | **12.34°C** | 25.00°C | **12.29°C** (Case A) |
| **Final junction temp (222 ms)** | 25.03°C | 12.34°C | 25.04°C | 12.29°C (Case A) / 25.03°C (Case B) |
| **Final junction temp (52 s)** | 28.78°C† | n/a | **28.71°C** | 28.76°C† |
| **Temp below ambient?** | Never | **Yes** | Never | Case A: Yes / Case B: Never |
| **Physical validity** | ✅ | ❌ | ✅ | Case A: ❌ / Case B: ✅ |
| **Deviation from gem5 bugged** | — | baseline | — | **0.05°C** (Case A) |

† Analytical and Python solver values at 52 s are estimated with sustained 3W power.

---

## 重點

獨立 Python solver 能在 **0.05°C** 內重現 gem5 bugged 結果，證明兩者共用同一個物理機制：0 K 的中間節點扮演了絕對零度熱沉。

修補後，gem5 會回到物理上合理的升溫軌跡。
