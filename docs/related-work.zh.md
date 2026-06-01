# 相關研究

## Thermal Modeling Tools

### HotSpot

HotSpot 是以 floorplan 為基礎的 thermal model，能看到更細的 spatial temperature distribution。相較之下，本研究使用的是較 lumped 的二階 Cauer RC network，重點在 junction 平均溫度與可驗證的暫態行為。

### McPAT

McPAT 會根據 gem5 activity counters 做更細的功耗估算。本研究目前的 `V^2 × 3.0 × IPC` 是簡化版，未來若整合 McPAT，能提升 OPP 轉換與分項功耗的準確度。

### DVFS governor 文獻

- `schedutil`：反應式 governor
- EAS：以 Energy Model 做異質排程
- 本研究的 `dT/dt` predictive governor：以溫度變化率做前瞻控制，屬研究型實作

## Simulation Infrastructure

### gem5

本研究使用 gem5 25.1.0.1 stable 的 ARM FS mode。這次發現的 bug 不是數值法本身有問題，而是 thermal node 初始化流程漏掉了中間節點。

### SPICE equivalent circuit

二階 Cauer RC thermal network 可以直接對應到 SPICE netlist；這也是為什麼獨立 solver 與 gem5 能在數值上互相對照。

## ARM thermal management

本研究也把 Linux thermal zones 與 big.LITTLE / EAS 的架構放進脈絡裡，方便 Phase 6 之後的異質排程分析。

