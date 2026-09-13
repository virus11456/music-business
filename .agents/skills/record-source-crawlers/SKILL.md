---
name: record-source-crawlers
description: 維護或執行 SIMPLES 唱片進貨資料抓取，涵蓋台灣 Yahoo、日本 Yahoo、露天、Tower、Discogs 反查、分批快取與 Sheets 同步。用於抓資料、修爬蟲、檢查自動收集或新增來源；不負責購買、刊登或客服。
---

# 唱片資料抓取

這是 music-business 專案的操作與維護技能。實際爬蟲、排程與持久資料仍在 Python 程式內；不要把每日排程改成 AI 任務，也不要另複製一套爬蟲到 skill。

## 找到實作與選擇流程

從本 skill 向上三層可到專案根目錄；先讀該處 `AGENTS.md` 與目前程式，文件中的數值是實作約定，不代表第三方平台永遠維持相同介面。

- 平台抓取／解析／連線問題：讀 [平台介面](references/platforms.md)，只檢查相關平台。
- 批次反查、快取、排程、Sheets 或比價結果：讀 [資料流程](references/pipeline.md)。
- 新增來源：依平台介面的擴充步驟處理。CATALOG 中 `supported=false` 只是通路名錄，不代表已接通。

## 唯讀診斷

使用 [scripts/inspect_crawlers.py](scripts/inspect_crawlers.py) 檢查既有資料庫：

```bash
python3 .agents/skills/record-source-crawlers/scripts/inspect_crawlers.py --db /path/to/existing.sqlite3
```

路徑必須由目前部署設定確認，不能猜測或建立新庫。工具以 SQLite read-only/query-only 開啟一致快照，輸出各平台最近收集、48 小時過期／未知報價、未反查、到期或身份改變數與排程歷史；不連網、不開始工作、不讀取憑證。`due` 將損壞重試時間列為待診斷，不代表現行排程一定能正常處理它。資料庫歷史不能證明排程程序仍存活，enabled 固定為 null，須另查正式 `/api/state`。

## 執行邊界

最新主資料源是使用者指定 Google Sheet，VPS 只執行單一正式程序與排程；SQLite 僅作記憶體查詢引擎，不能改回舊磁碟庫。詳見專案 docs/SHEET_PRIMARY.md。維護前讀取 `/api/state` 的 active、jobs、schedule、source_queue；不要在 Mac 啟動第二套正式後端。程式測試用臨時資料庫，不能往正式庫塞示範商品。

需要實際收集時，優先使用既有前端或後端工作 API，沿用使用者指定主題、平台及 Google Sheet。建立新主題會保存並納入後續輪替，不能因示例而擅自扩大搜尋範圍。API 傳回 accepted 只表示已接單，須讀工作結果判斷成功、部分失敗或仍執行中；結果不明時先查狀態，勿重送同一批。

憑證只從部署設定取得，不寫進 skill、命令輸出或 Git。Chrome 只能協助觀察使用者授權的頁面與管理主機；抓取被拒、頁面變更或驗證阻擋時，保留失敗狀態與原始資料，不用猜值或把失敗當空結果。不能為爬蟲停用 TLS、固定未知 IP 或改用未授權登入資料。

## 配對與結果語意

只將相同且明確的黑膠／CD／卡帶配成候選。品相差異不是身份衝突；Label 是輔助證據，不能蓋過格式或唱片編號衝突。標題推測編號仍須標示待核對，不等於已確認壓片。沿用 `source_match.py`，不要各平台自行建立較寬鬆的判斷。

Want 是收藏需求數，不是實際買方訂單。Discogs 最低掛牌價不是成交價；拍賣出價、規格區間價、未知庫存都不能當成已確認可採購成本。毛利與扣設定費用後淨利分開，不能將未填費用視為已確認全成本。

## 驗證與交付

修解析器先以小型、無個資的 HTML／JSON fixture 驗證實際欄位與錯誤路徑；再依授權範圍做單頁或一批實測。保留頁碼、身份快取、未配對資料與重試時間，不清空佇列以求「重跑成功」。

按改動執行 references 指定測試，報告離線解析通過與正式連線結果的差異。說明平台、批次數、成功／失敗／未配對、資料新鮮度、後續排程；候選組合數不要稱為套利商品數。Sheets 同步成功與逐格回讀驗證分開報告。

爬蟲功能、參數或限制變動時，同步更新本 skill 對應 reference、README、CHANGELOG 與相關測試，提交至專案指定 GitHub。skill 的存在不代表當前平台都已實測可連線。
