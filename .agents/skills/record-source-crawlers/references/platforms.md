# 平台抓取介面

實作入口為根目錄 `platforms.py`：`CATALOG`、`search_url`、`PARSERS`、`candidate`、`search`；以下是目前程式契約，不是官方 API 保證。

## 共同規則

`search(settings, query, selected, page=1, full_page=False)` 驗證搜尋詞 1–120 字、平台最多 4 個、頁碼 1–1000。平台最近一次收集不足 3 秒時等待。`fetch` 的 timeout 為 25 秒、回應上限 5 MB，跨主機重新導向會拒絕。

商品以 `(platform, external_id)` upsert，保存標題、歌手、格式、編號、價格、幣別、price_kind、availability、source_url、captured_at。非正數或無效價格是缺值，不是零元。成功空頁與讀取失敗分開寫入 `platform_runs`；解析結構壞掉應拋錯。

## 台灣 Yahoo：yahoo_tw

- 搜尋 `https://tw.bid.yahoo.com/search/auction/product?p=...`，續頁用 `pg`。
- `parse_yahoo_tw` 讀 `<script id="isoredux-data">` 的 `search.ecsearch.hits`，只接收 TWD。`ec_productid`、`ec_title`、`ec_price` 對應商品；最低／最高價不同標 `range`，庫存預設未確認。
- `yahoo_transport.py` 只對 `tw.bid.yahoo.com` 使用正常 DNS 的 IPv4 連線，保留預設 TLS 憑證驗證。這是既有 IPv6 搜尋路徑異常的局部修正；不能把任何 404 都歸咎 IPv6，或改全機 DNS／固定 IP。
- 缺少 script 或 hits 結構改變應報失敗。先區分 HTTP 回應與 JSON 解析，再更新 fixture。

## 日本 Yahoo：yahoo_jp

- 搜尋 `https://auctions.yahoo.co.jp/search/search?p=...&ei=utf-8`；續頁 `b=(page-1)*50+1`、`n=50`。
- `parse_yahoo_jp` 讀 `li.Product` 裡帶 `data-auction-id` 的連結及 title／price。JPY，`price_kind=current_bid`，標示拍賣中／需確認結標。
- 無卡片時僅遇程式認得的「一致する商品はありません」「見つかりません」才當空結果；其他狀況視為结构改變。
- source-first 的 full_page 模式最多 50 筆；一般第一頁搜尋目前最多 40 筆。不要將出價當成含運即買價。

## Tower：tower

- 搜尋 `https://tower.jp/search/item/...`，續頁 `?page=`。
- `parse_tower` 讀商品卡片 `TOL-item-search-result-PC-result-list-display-item`，格式來自 category，連結限 `https://tower.jp/item/數字`；保留 artist、規格品番、JPY 標價與來源庫存文字。
- `tower_pages` 讀 `.common-pagination` 對應 totalPages 腳本；不要誤讀歌手彈窗的另一組分頁。full_page 模式無法解析總頁數時停止推進頁碼。
- 取扱なし、預購、訂購、庫存少、有庫存要保留差異；有舊標價不代表目前可買。查 `frontend/lib/source-availability.ts` 看展示分類，不另發明存貨推測。

## 露天：ruten

- 搜尋使用網站目前可讀的 JSON 介面 `https://rtapi.ruten.com.tw/api/search/v4/index.php/core/prod`，`q`、`type=direct`、`sort=rnk/dc`、`limit=40`、`offset=(page-1)*40+1`。
- 先取 `Rows[].Id`（只接受數字），等待 3 秒，再用 `/api/prod/v3/index.php/prod?id=...` 一批取得商品資料。這是網站介面，不宣稱官方穩定開發者 API。
- `parse_ruten` 要求 JSON list、TWD、兩個 PriceRange 值；SaleType 非 buy 為競標，買價區間不同為 range。StockStatus=1 是來源標示有庫存，2 是預購，其餘未知。
- `source_refresh.py` 每次最多 20 件（允許 1–40），補刷新超過 6 小時的舊露天報價；同一商品失敗後至少 1 小時再試。回傳重複／額外 ID 視為失敗。標題變更不刷新舊配對時間，missing 不冒充新鮮庫存。只更新平台報價，不覆寫人工總成本。

## 新增與測試

新增平台需同時提供解析器、搜尋 URL、商品穩定 ID／連結／幣別／價格種類、有效空結果判斷與 fixture，檢查平台數量驗證及前端選單；確認後才設 supported=true。Mercari、Rakuten、Disk Union、HMV、Record City 目前只是未接通名錄。

依改動執行：

```bash
.venv/bin/python -m unittest tests.test_platforms tests.test_source_refresh
```

Yahoo transport 改動另找並執行 `tests/test_yahoo_transport.py`。平台當天可用性仍需授權環境實測，fixture 不能證明網路通暢。
