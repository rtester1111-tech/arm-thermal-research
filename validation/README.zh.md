# 驗證

這個資料夾收納支撐 bug 證據與熱模型比較的數值與解析驗證。

## 內容

- [解析解](analytical/analytical_solution.py)
- [獨立 Backward Euler 求解器](implicit_solver/implicit_solver.py)
- [時間步長掃描](timestep_sweep/timestep_sweep.py)
- [交叉比對圖](crosscheck/three_way_comparison.py)
- [SPICE cross-check 筆記](crosscheck/spice_crosscheck.md)
- [誤差計算](error_metrics/compute_errors.py)

## 什麼時候來這裡

- 你要看封閉形式的熱基線
- 你要看獨立求解器如何重現 gem5 的 bug 軌跡
- 你要看誤差與收斂證據
