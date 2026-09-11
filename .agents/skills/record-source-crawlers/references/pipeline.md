# 反查、排程與同步

## 正式操作入口

先 GET `/api/state`。沿用後端認證、Origin 與狀態中的 CSRF；不把 token 放在 URL。POST 會啟動背景工作，需追蹤 jobs 與 active：

- `/api/sourcing/reverse` 搭配 `{ "query": "使用者的主題", "platforms": ["yahoo_tw", "yahoo_jp", "ruten", "tower"] }`：取各平台保存的下一頁、保存主題與平台範圍，反查一批、分析及同步。
- 同一端點搭配 `{}`：不增加搜尋主題或抓新搜尋頁，處理既有到期佇列，也可能刷新露天報價、行情與 Sheets。
- `/api/platforms/search` 搭配 query/platforms：僅搜尋保存來源，不等同反查與完整同步。
- `/api/platforms/match` 搭配 candidate_id（可選 query）：搜尋 Discogs 版本建議，不等於人工确认。
- `/api/sheets/sync`：同步既有資料；先看工作是否執行中，勿重複提交。

呼叫前以 `server.py` 確認契約；日常操作優先走前端既有按鈕，不另寫繞过工作鎖的正式操作腳本。

## 佇列與排程

`source_queue.py` 保存 source_topics、source_pages、source_checks。預設每批 20 件反查，函式允許 1–40 件。頁面成功才推進；失敗保留原頁；空結果／最後頁會回到第一頁以供日後更新。

身份 fingerprint 只包括 title、artist、format、catalog_no；價格和庫存改變不強迫重新搜版本，但仍應刷新報價與利潤。身份一致時：未配對 7 天、已配對 30 天、查詢失敗 1 小時後重試。身份改變則提早反查。不要刪 cache 或改 captured_at 來掩蓋過期。

`matching.py` 搜尋 release，每件最多 10 建議。`source_match.py` 再嚴格核對格式、編號、標題；`direct_matches.py` 對已存貨源和版本作本地交叉比對並使用 v3 快取。明確規格編號優先，其次僅採標題中單一明確編號；多編號不猜。Label 僅輔助。保留 `excluded_matches` 與人工核對的不同語意。

每批共用 Discogs client，同一版本不重抓；行情不足 6 小時時沿用，另輪替最多 20 個既有版本更新行情。`scheduler.py` 按 Asia/Taipei 每日 10:00／16:00／22:00 執行；待處理多於 20 時先消化佇列，否則輪替已保存主題。這是主題分頁收集，不是全站庫存鏡像。以 API 的 enabled、last_run、next_run 驗證執行情況，不僅看設定文字。

## Discogs 與 Sheets

`discogs_client.py` 是 GET-only：`/database/search`、`/releases/`、`/marketplace/stats/`。使用設定內 token 和 User-Agent；SQLite api_budget 共用 1.1 秒間隔；剩餘額度低時冷卻，429／5xx 或暫時連線問題最多 4 次嘗試，尊重 Retry-After。不要另建無節流 client 平行灌請求。

`ingest.py` 保存版本與行情；`analyze.py` 分析；`comparisons.py` 算含幣別換算的價差／毛利／扣設定費用後淨利；`sheet_sync.py` 的 build_tables/sync 是唯一表格輸出契約。沿用已指定 Sheet 與應用程式管理的分頁，不能覆寫使用者其他分頁。快取命中並不代表來源報價新鮮，前端 48 小時篩選與缺值語意需保留。

配對、報價核對、草稿、正式刊登是不同狀態。`workflow.py` 匯出會重查已排除配對、48 小時確認期限、報價更新與來源 URL 一致性。現有 Quicklister 是檔案匯出，不能聲稱已透過 Discogs API 刊登。

## 驗證

```bash
.venv/bin/python -m unittest tests.test_source_queue tests.test_source_match tests.test_matching tests.test_direct_matches tests.test_comparisons
.venv/bin/python tests/run_offline.py
```

HTTP 完整流程測試在允許 localhost bind 的隔離測試環境執行；測試 subprocess 不應繼承正式 REMOTE_ACCESS_TOKEN／FRONTEND_ORIGIN／PUBLIC_API_ORIGIN，避免 fixture 被正式 Origin 拒絕。不得因此修改正式服務的認證設定。外部服務 mock、API 工作成功、真實平台連線與 Sheet 回讀各自說明，不混成「全流程已上線」。
