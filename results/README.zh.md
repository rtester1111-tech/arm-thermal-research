# 結果資料夾

這個資料夾存放研究中使用的圖表、JSON 摘要與執行輸出。

## 主要分類

- `validation/` - 分析、數值與交叉驗證輸出
- `phase5/` - 未修補的 full-system gem5 bug 確認結果
- `phase5_v2/` - 修補後的 full-system gem5 驗證結果
- 根目錄圖表與 JSON - DVFS 與漏電研究的摘要輸出

## 建議從哪裡開始

- [驗證圖表](validation/)
- [修補後的 full-system 執行結果](phase5_v2/)
- [Bug 確認執行結果](phase5/)

## 補充說明

這裡的頂層檔案都是實驗與分析腳本的正式輸出。摘要結果保留在這裡即可；原始大型資料若不是對外發布證據，建議放在 git 之外。
