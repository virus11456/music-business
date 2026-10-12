# Discogs 刊登送出

2026-10-12 本機實作，未部署、未以真實 Discogs 帳號送出。狀態表第 3 項「Discogs 正式刊登」從「未連接」改為「已實作，待設定、部署與正式驗收」。

## 功能

`POST /api/listings/publish`，body 為 `{ "draft_ids": [1, 2], "currency": "USD", "status": "Draft" }`，沿用管理者認證、Origin、CSRF 與工作鎖，以背景工作「送出 Discogs 刊登」執行。`status` 只接受 `Draft`（在 Discogs 建立草稿刊登，預設）或 `For Sale`（直接出售）。每批 1 至 50 筆不同草稿。

送出前整批驗證，任何一筆不通過就整批不送：草稿存在、通過與 Quicklister 匯出相同的 `draft_export_issues` 檢查（48 小時確認、版本、品相、供貨、來源報價一致、未登錄上架、未被排除）、幣別與賣家設定一致，且沒有結果不明的舊送出。

每件草稿依序處理：先把 `submitting` 紀錄寫進主資料源，再呼叫 `POST /marketplace/listings`（release_id、condition、sleeve_condition、price、status、comments、external_id=`simples-{draft_id}-release-{release_id}`、allow_offers=false）。只送一次，結果分三類：

- **listed**：回應 201 且有正整數 `listing_id`。寫入 `published_listings`，草稿顯示已上架，之後不能再匯出或重送。
- **failed**：Discogs 回 4xx（含 429）。Discogs 沒有建立刊登；保留拒絕原因（最多 200 字），草稿可修正後再送。
- **uncertain**：5xx、連線中斷、逾時、回應不是 JSON object 或缺少 `listing_id`。刊登可能已存在，系統**不重送**，並停止同批其餘草稿（計為 not_attempted）。草稿的匯出、AI 文案與再次送出都會被阻擋，直到核對完成。

紀錄存於 meta 鍵 `listing_submission:{draft_id}`（Sheet 允許前綴已加入），保留最近 10 次歷史、要求狀態、送出與完成時間。`workflow.listing_submissions` 回傳啟用狀態、各狀態計數與最近 100 筆；每筆草稿另帶 `submission` 摘要。公開目錄白名單不含這些欄位。

## 核對結果不明

1. 先按「讀回刊登狀態」（`inventory_sync`）。完整快照中若有相同 `external_id` 與版本的刊登，自動把 `submitting`／`uncertain` 標為 `listed` 並連結刊登編號；工作結果顯示 `reconciled` 數量。
2. 或在前端「送出到 Discogs」面板人工核對：`POST /api/listings/submissions/resolve`，`outcome=listed` 需填 Discogs 刊登編號；`outcome=not_listed` 標為 failed，草稿可重送。只能處理 `submitting`／`uncertain`。
3. `submitting` 超過 10 分鐘仍未完成，代表最後一次寫入沒有完成（例如程序中斷或 Sheet 寫入結果不明）；前端同樣提供核對按鈕。

## 啟用與邊界

- 後端環境變數 `DISCOGS_LISTING_WRITE=1` 才啟用；未設定時 API 拒絕、前端面板顯示未啟用。只部署程式不會開始寫入。
- 使用既有 `DISCOGS_TOKEN`；Discogs 要求該帳號具賣家權限。目前帳號停權（HTTP 403），解除前不能驗收。
- 價格以草稿幣別送出，Discogs 以賣家設定幣別解讀；前端先核對賣家幣別再勾選。
- 不上傳照片、不自動設定運費政策、不處理訂單；建立後仍須到 Discogs 核對版本、照片與出貨條款。
- 示範庫不能送出。工作明細含逐件結果，不含 token。

## 驗證

- 16 項隔離測試（tests/test_discogs_publish.py）：停用旗標不送出、整批先驗證、成功登錄並阻擋重複匯出、拒絕可重送、結果不明停止後續且不重送、人工核對兩種結果、庫存讀回自動對帳、客戶端 4xx／429／5xx／斷線／非 JSON 分類、端點與公開目錄排除、Sheet meta 契約。
- 後端離線 275 項、前端 109 項 node 測試、`tsc --noEmit` 與 `build:vercel` 通過。
- 未部署 VPS、未取得賣家權限、未對 Discogs 送出任何請求；`oxlint` 對 workflow.tsx 既有表單預設值的 no-base-to-string 警告為本批之前已存在。
