# gem5 熱模型 Bug：中間節點在 0 K 初始化

## 一句話摘要

`ThermalModel::startup()` 沒有初始化中間 RC 網路節點，讓它們停留在 0 K（−273.15°C）。這會在第一個 Backward Euler 步驟中形成一個虛假的絕對零度熱沉，使 die 溫度在有正功耗輸入時仍往下掉。

## 快速重現

```bash
bash reproduce.sh
# 預期異常輸出：Junction 溫度從 25°C 掉到約 12°C
```

請搭配 [expected_vs_observed.md](expected_vs_observed.md) 查看四方數值比較，並套用 [gem5_thermal_fix.patch](../../gem5_thermal_fix.patch) 修正。

---

## 受影響版本

所有支援多節點 thermal network 的 gem5 版本都會受到影響。`thermal_node.cc` 的 `temp(0.0f)` 預設值自 thermal model 引入以來就存在（2017 起）。本專案已在 **gem5 25.1.0.1 stable** 驗證。

---

## 現象

在 gem5 FS mode 中配置 2-node Cauer RC thermal network，並施加約 3 W CPU 功耗時：

```
Expected: Junction temp rises from 25°C toward steady-state (~28°C)
Observed: Junction temp drops 25°C → 12.34°C (physically impossible cooling)
```

溫度下降會持續多個 thermal time-constant，之後才慢慢回升，但通常模擬窗口早已結束。

