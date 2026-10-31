## 2026-11-01 Discogs 上架 API 正式驗證（建立草稿 → 讀回 → 刪除）

VPS 以正式 token 直接呼叫 Discogs API：`POST /marketplace/listings` 建立 Draft 刊登（release 13668328、Near Mint、US$999、allow_offers false）回 201，listing 4443871782；`GET` 讀回 Draft、版本、品相、價格皆一致；`DELETE` 回 204；再讀回 404「Item not found」。PinnacleRecords 具 API 上架與刪除權限，測試刊登未留存。此測試未經網站「送出到 Discogs」流程，`DISCOGS_LISTING_WRITE` 仍未開啟；網站上架流程待使用者以實際要賣的商品驗收。

## 2026-10-31 Discogs 帳號停權解除（正式 API 唯讀驗證）

VPS srv1542946 以正式 token 檢查：`/oauth/identity` 200（PinnacleRecords）；`/users/PinnacleRecords/inventory` 200、362 筆刊登（10/30 仍為 403 suspended）；對 `/marketplace/listings` 送出刻意缺欄位的空內容得 422「Invalid release_id」，表示上架端點已進入欄位檢查，帳號具上架權限，未建立任何商品。公開庫存另可見 347 件 For Sale。未修改 .env、未開啟 `DISCOGS_LISTING_WRITE`、未重啟服務。

尚未完成：系統內的庫存讀回（`POST /api/inventory/sync`）尚未對這個帳號跑過，362 筆刊登與本系統紀錄的關聯未驗證；系統上架仍關閉，正式送出一件商品並讀回核對前不宣稱上架流程已驗收。

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

## 驗證方式與換帳號

依 Discogs 官方驗證規範，只操作自己帳號時使用個人存取 token（Settings → Developers → Generate new token），標頭為 `Authorization: Discogs token=<token>`，本程式即採此方式；不需要在「Create an Application」申請 OAuth consumer key／secret，那是代替其他使用者操作時才需要。每個請求須帶 User-Agent，認證後限速每分鐘 60 次，既有 client 已處理。

換帳號：由使用者在新帳號產生 token，自行寫入 VPS `.env` 的 `DISCOGS_TOKEN`（權限 600）並重啟服務，不經對話傳遞。新帳號須先完成 Discogs 賣家設定（幣別、付款、運費政策），前端賣家幣別也要對應。庫存讀回保存舊帳號名稱，換帳號後先用「改用其他帳號重新讀回」清除舊快照，刊登登錄紀錄保留（見 INVENTORY_SYNC.md）。

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
