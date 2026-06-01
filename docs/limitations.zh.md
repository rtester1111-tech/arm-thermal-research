# 模型限制與未來工作

這份文件誠實列出目前模型的邊界，以及若要讓結論更強，還需要補哪些材料。

## 1. 參數來源

R 與 C 值是根據公開 thermal characterization data 擬合而來，量級合理，但沒有對準特定實體晶片。

## 2. 一維熱模型

Cauer 2-node RC 模型能描述 junction-to-ambient 的平均溫度，但看不到局部 hot spot、die 內部 lateral spreading，或 package 級的溫度梯度。

## 3. 功耗模型簡化

目前的功耗模型使用 `P_dynamic = V^2 * 3.0 * IPC` 與簡化的 leak 項，能反映趨勢，但不能取代 McPAT 或更完整的 microarchitectural power model。

## 4. 工作負載代表性

Brightness 與 IDCT 是 synthetic microbenchmark，適合做可重現驗證，但不能直接外推到所有真實 app。

## 5. gem5 仿真 fidelity

Timing O3CPU 與 thermal ODE solver 已經足夠做研究，但仍有 cache、memory controller、DVFS 延遲等簡化。

## 6. 25% 能效改善的條件

這個數字只對特定 workload、governor、溫度門檻與模擬設定成立，不應直接外推到其他晶片或應用。

## 7. patch 狀態

Absolute-Zero Heat Sink Bug patch 已本地驗證，並持續追蹤 upstream review。

