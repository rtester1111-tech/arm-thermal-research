# 如何貢獻到 arm-thermal-research

感謝你想參與這個研究專案。

## 範圍

這個 repo 記錄的是一個封閉型研究工作，主題是 ARM 異質熱管理與 gem5 DVFS 模擬。歡迎能提升可重現性、修正不精確之處、或擴展模擬方法的貢獻。

## 如何參與

### 回報問題

- 如果文件、模擬腳本或研究數據有錯誤，請用 GitHub Issues 回報。
- 如果你懷疑數學模型或模擬結果有問題，請附上公式、腳本，以及實際與預期行為的差異。

### 提交變更

1. Fork repository，並從 `main` 建立分支。
2. 以清楚、具描述性的 commit message 提交變更。
3. 若修改 Python 腳本，請先確認能通過基本檢查（例如 `python3 -m py_compile <script>`）。
4. 開 Pull Request 時請簡述變更內容與動機。

### 歡迎特別關注的方向

- **Phase 6 實作**：big.LITTLE / DynamIQ EAS 異質任務遷移（見 `PHASE5_6_IMPLEMENTATION_PLAN.md`）。
- **gem5 Absolute-Zero Bug patch**：將 `src/sim/power/thermal_model.cc` 的 C++ 修正送 upstream。
- **McPAT 整合**：自動化 gem5 stats → McPAT XML → power extraction 流程。
- **新增 workloads**：例如 H.265 entropy coding、FFT 等新的 SIMD benchmark。

## 風格

- C 原始碼沿用 K&R style，縮排為 4 spaces。
- Python 腳本以 Python 3.8+ 為目標，使用 `numpy` / `matplotlib`。
- Shell script 使用 `#!/usr/bin/env bash` 與 `set -euo pipefail`。

## 引用

若你在學術研究中使用此工作，請引用 `CITATION.cff` 的 metadata。

## 授權

你的貢獻將依 MIT License 授權。

