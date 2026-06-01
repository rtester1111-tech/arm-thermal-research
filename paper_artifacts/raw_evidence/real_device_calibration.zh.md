# 模擬範圍與未來硬體校準

本倉庫是 simulation artifact。已投稿的 Paper 1 與 Paper 2 結果沒有使用實體 ARM 裝置量測資料做熱模型校準。

目前的證據基礎包含：

- gem5 thermal model 行為與設定 traces；
- Cauer RC path 的 analytical、Python、SPICE 交叉驗證；
- package-aware scheduling 實驗用的 trace-driven co-simulation；
- 公開 artifact tree 裡的 figures、logs、scripts。

本倉庫沒有提供、也沒有主張使用 board-level temperature traces、silicon power measurements、hardware power-monitor logs、外部功耗儀資料，或硬體 sensor calibration files。

## 如何解讀目前結果

Paper 1 使用模擬與獨立求解器檢查 gem5 原生 Cauer RC thermal path 的物理 admissibility。核心結果是 thermal-initialization artifact 與修正方式；它不需要對準某一顆實體晶片。

Paper 2 在 gem5-based workflow 中評估 trace-driven package-aware scheduling mechanism。文中的 RC parameters 是模擬參數，不是從特定實體晶片量測後 fitting 出來的結果。因此它應被解讀為 simulator-level artifact，而不是 hardware characterization study。

## 若未來要做硬體校準，需要補什麼

若之後要延伸成硬體校準版本，至少需要新增以下證據後才能做 device-specific claims：

1. 明確的 target platform、board revision、作業系統、散熱條件、環境溫度、firmware/kernel configuration。
2. 在受控 workload 下收集並對齊時間軸的 temperature、power、frequency、workload traces。
3. 從 traces fitting RC parameters 的完整程序。
4. 使用 hold-out validation run 證明 fitted parameters 能預測另一組 workload 或 thermal transient。
5. 對 sensor placement、sampling rate、power attribution、thermal boundary conditions 的 uncertainty 討論。

在這些實機量測完成前，本倉庫只把 hardware calibration 視為 future work。
