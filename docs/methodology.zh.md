# 方法論

## 1. Cauer 2-Node RC 熱模型

本研究使用二階 Cauer RC thermal network 來描述無風扇 ARM SoC 的 die-to-ambient 熱路徑。

### 參數

| 參數 | 數值 | 物理意義 |
|---|---|---|
| R_die_pkg (R1) | 5.0 K/W | die → package |
| R_pkg_amb (R2) | 10.0 K/W | package → ambient |
| C_die (C1) | 1.0 J/K | die 熱容 |
| C_pkg (C2) | 5.0 J/K | package 熱容 |
| T_ambient | 25°C (298.15 K) | 固定環境參考 |

### 推導量

- `tau_die = C_die × R_die_pkg = 5.0 s`
- `tau_pkg = C_pkg × (R_die_pkg + R_pkg_amb) = 75.0 s`
- `R_total = 15.0 K/W`
- `T_steady (at 3W) = 70°C`

## 2. 解法：Backward Euler

熱方程式以隱式法求解，優點是對本問題無條件穩定，適合長時間暫態模擬。

## 3. gem5 設定

- `--cpu-type=timing`
- `--big-cpu-clock=3.3GHz`
- `--thermal-step=0.01s`
- `--stats-period=0.0002s`
- `--machine-type=VExpress_GEM5_Foundation`

## 4. 功耗模型

```python
P_dynamic = V^2 * 3.0 * IPC
P_leak = 0.1 * (T_temp / 300)^2
```

這是以 IPC 近似活動因子的簡化模型，能抓到相對趨勢，但在 OPP 切換時仍低估部分頻率效應。

## 5. 工作負載

- Brightness：記憶體頻寬型
- IDCT：運算密集型

這兩種 workload 讓本研究可以同時觀察不同瓶頸下的 thermal/DVFS 行為。

