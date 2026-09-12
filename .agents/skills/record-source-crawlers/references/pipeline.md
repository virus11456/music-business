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

診斷前端最近工作時，失敗 detail 可能只是例外名稱，執行中可能為 null。`frontend/lib/collection-job.ts` 同時辨識收集／排程工作名稱及 JSON detail，不能只找最近成功 JSON。完整待開發項目見根目錄 `docs/IMPLEMENTATION_STATUS.md`。

庫存讀回新模組 `inventory_sync.py` 與端點、分頁及關聯規則見根目錄 `docs/INVENTORY_SYNC.md`；此為開發中功能，勿將既有行情 API 成功視為庫存端點已驗收。

### 2026-09-12 觀察目標價紀錄

新增 watch_alerts.py：analyze.run 在既有行情更新／評分流程中檢查最新 watch 決策，不受一般機會分數門檻影響。同幣別直接比較，跨幣別需有效匯率；只接受設定目標之後取得、未過期、非未來、價格為正且有人在售的行情。每次觀察決策僅留一次達標紀錄於 meta，重設觀察目標可再觸發，停止觀察後不觸發；通知設定頁列出最近 100 次目標的首次命中。這是 Discogs 最低掛牌價低於或等於目標的歷史紀錄，不是貨源降價、成交或買家需求保證。沒有新增 Telegram 發送。5 項目標價測試及型別檢查通過；VPS 尚待部署，部署前不會產生正式到價紀錄。

2026-09-12 部署補記：watch_alerts／analyze／notification_review 已於 VPS 部署且檔案雜湊一致；正式工作 #57 評分 90 張，watch_hits=0，內建排程存活且 16 點時段已完成。153 項離線測試通過，前端到價紀錄區讀取驗證通過。實際到價案例尚未出現，不以隔離測試冒充正式命中；未發送 Telegram。

### 2026-09-12 正式主題擴充

使用者已確認擴充至六個搜尋主題；平台範圍與首批結果見 docs/SEARCH_TOPICS.md（專案根目錄）。新主題為黑膠唱片、レコード、CD、卡帶、カセット；各自在正式 source_topics 保存，不寫死到排程。#58–62 均完成，325 件待反查，維持每輪 20 件與 10/16/22 時段，後續優先消化佇列。matched 僅表示版本候選，不能稱作已確認套利商品。

前端 CollectionProgress 顯示 source_queue 首次反查進度；unchecked 只指沒有 source_checks，不含所有到期／身份改變項目。completed=total-unchecked 包含 failed 和 unmatched，不能當成成功匹配；匹配數更不能當成正毛利商品數。

### 2026-09-12 首批待比對清空與線上驗收

21:49（台北時間）完成既有 325 件待首次反查資料，正式工作 #63–79 共 17 批全部成功：新增 15 件候選匹配、310 件暫未匹配、0 件失敗。累計保存 1,189 件貨源，其中候選匹配 70 件、暫未匹配 1,119 件、未首次反查 0 件，active=null。70 件是候選貨源匹配數，不是已確認版本或可套利專輯數。未匹配資料保留，依既有 7 天快取規則再查。本次為授權的首次建置補跑，沒有新增主題或常駐執行器；VPS 程式每日 10:00／16:00／22:00 Asia/Taipei 排程仍啟用，不依賴對話推動。先前約 6 天的估算已由本次 17 批補跑完成取代。

17 批工作均回報 Sheets synced=true，最後 Discogs 頁 141 列、Sources 人工報價頁 0 列；此為工作回傳，未逐格回讀 Sheet。前端已部署成功，Chrome 實際登入並開啟「進貨與 Sheets」，確認首次反查 100%、待處理 0，以及比價表每頁 50 筆；在 883 筆正毛利比價列（18 頁）上實際切換第 1→2→1 頁成功，修正大量資料一次渲染造成頁面無回應的問題。比價列數不同於唯一貨源或已核對專輯數。瀏覽器驗收沒有建立報價、採購或刊登資料。

### 2026-09-12 22:00 自動接續驗收

22:02 唯讀查驗正式 API：排程工作 #80 於 22:00:06 自行開始、22:00:30 成功完成，沒有手動觸發。首次建置佇列清空後已恢復主題下一頁收集：Yahoo TW 38、Yahoo JP 50、露天 8、Tower 4，共 100 筆搜尋結果，平台失敗 0。去重後新增 2 件，反查 2 件（匹配 1、未匹配 1），沿用 1,189 件快取，刷新露天報價 20 件成功，更新行情 2 件。累計 1,191 件貨源、71 件候選匹配、1,120 件暫未匹配、unchecked=0；候選不等於已確認套利商品。

工作回報 Sheets synced=true、Discogs 頁 143 列、Sources 人工報價頁 0 列；未逐格回讀。active=null、schedule.enabled=true、last_run=complete，下一輪 9/13 10:00 Asia/Taipei。排程程式核對為最久未收集主題輪替；此次繼續 The Beatles Rubber Soul，下個主題依保存時間選擇。此為正式唯讀驗收與文件更新，未修改程式、增加主題或新增排程。

### 2026-09-12 四平台已存貨源刷新（後端待部署）

source_refresh 新增 Yahoo TW／JP、Tower 的商品頁更新，每平台每輪最多 2 件超過 6 小時的旧報價，露天原批次最多 20 件保留；失敗至少 1 小時後再試，依未試及舊嘗試輪替。查詢只用保存平台與穩定商品 ID 建立網址，不新增來源／搜尋主題；更新價格、價格種類、供貨狀態及抓取時間，不覆寫人工報價或版本資料。編號、名稱不符及已知格式衝突不更新舊配對時間，HTTP／解析失敗保留舊值與舊時間，不當作售完。結果逐平台彙總，前端兼容舊露天工作紀錄。

source_details：Tower 讀 Product JSON-LD 並核對 itemId／商品路徑，backOrder 為待調貨。日本 Yahoo 讀同商品 Product，仍採 current_bid，不因 InStock 變即買價；有時區的 priceValidUntil 過期標已結束。台灣 Yahoo 讀 isoredux-data.item，只接受實測 type=1/status=2，其他狀態保留失敗；正庫存數仍是未確認，零數量標無現貨。數字狀態全集、所有下架頁及規格變化未完整實測，不能宣稱全站可靠識別。每平台每日預設最多刷新 6 件商品頁，並非所有已存貨源每日全量更新。

17 項刷新／佇列測試、完整 158 項離線測試通過（15 項 socket 測試未跑），前端工作明細 4 項測試通過。使用正式已存來源各一件在 Mac 連線讀取成功：Tower 8139759 JPY 5790 待調貨、Yahoo TW 101171414293 TWD 7000 供貨未知、Yahoo JP g1239890604 JPY 2500 拍賣中；不是 VPS 寫入驗收。

部署受阻：Hostinger 兩次新建 Web Console 均顯示無法連線，重新整理回 403；正常正式 API 回傳既有 #80 成功與排程存活。沒有重新啟動 VPS、停用 SSH 主機驗證或更改正式資料。後端尚未部署，正式排程仍僅露天逐商品刷新；待終端恢復後備份、部署、以正式 API 觸發一批並回讀結果。
