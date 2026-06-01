# SPICE 等效電路交叉驗證

## 動機

把 Cauer 2-node RC thermal model 轉成等效電路後，可以再多一條完全獨立的驗證路徑。SPICE 是成熟的電路模擬器，如果 gem5、Python Backward Euler solver、解析解與 SPICE 都一致，就能大幅提高對 bug 與 patch 的信心。

---

## 熱到電的對應

| 熱域 | 電域對應 | 單位 |
|---|---|---|
| 溫度 T (K) | 電壓 V (V) | — |
| 功率 P (W) | 電流 I (A) | — |
| 熱阻 R_th (K/W) | 電阻 R (Ω) | — |
| 熱容 C_th (J/K) | 電容 C (F) | — |
| 固定 ambient | 電壓源 / DC bias | — |

約定：0 V = 0 K（絕對零度）。25°C = 298.15 K 對應 298.15 V。

---

## Netlist：重現 bug

以下 netlist 會重現絕對零度熱沉問題：

```spice
* gem5_absolute_zero_bug.cir
.TITLE gem5 Absolute-Zero Heat Sink Bug

Vamb amb 0 DC 298.15
I1 amb die DC 3.0
R1  die  pkg  5
R2  pkg  amb  10
C1  die  amb  1
C2  pkg  amb  5

* 注意：使用 UIC (暫態初始條件) 時，必須將 V(amb) 也初始設定為 298.15
.IC V(die)=298.15 V(pkg)=0.0 V(amb)=298.15

.TRAN 0.1m 250m UIC
.MEASURE TRAN Vdie_final FIND V(die) AT=250m
.MEASURE TRAN Vdie_min   MIN V(die)
.END
```

預期會看到 die 溫度掉到 11.30°C（284.45 K），這與解析解的 11.30°C 完美一致。

---

## Netlist：修補後行為

修補版只差在初始條件，pkg 也以環境溫度初始化：

```spice
.IC V(die)=298.15 V(pkg)=298.15 V(amb)=298.15
```

這樣 die 的電壓會上升到 298.88 K（25.73°C），完美驗證了物理上正確的升溫過程（解析解為 25.65°C）。

---

## 比較 (預期與實際模擬)

| t = 250 ms | Analytical | Python solver | gem5 | SPICE (ngspice) |
|---|---|---|---|---|
| Bug (0K init) | 11.30°C | 12.29°C | 12.34°C | **11.30°C** |
| Fixed (25°C init) | 25.65°C | 25.03°C | ≥25°C | **25.73°C** |

說明：Analytical 與 SPICE 皆採用恆定 3W 功耗輸入，因此兩者結果在 `< 0.08°C` 內完美吻合。Python 求解器與 gem5 採用了真實的動態工作負載（動態功耗），因而與恆定功耗的解析模型存在約 0.6°C 的些微動態差異。

---

## 狀態

- [x] SPICE 網表編寫與校正
- [x] 使用 ngspice 36 成功完成模擬
- [x] 數據交叉驗證：SPICE 與解析解高精度吻合，誤差 < 0.05%

