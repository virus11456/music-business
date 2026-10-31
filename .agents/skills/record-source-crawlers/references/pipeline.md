# 反查、排程與同步

## 最新查驗與發布界線（2026-09-14）

由指定Sheet的jobs直接讀回自然#97、#98成功。#97因pending_before=25先消化20件，沒有抓新頁；#98從Yahoo JP／Tower第2頁收集73筆結果，反查20件、行情更新20版、刷新28/28，pending=57。兩轮保存3展示頁寫入、2頁略過、5頁讀回成功；這是本次直接讀到的正式工作紀錄，不是本次重新逐格核對全資料。後續02:55已使用登入的VPS主控台讀公開HTTPS API200：active=null、google_sheets，下一輪10:00；24底層表與2724比較唯讀稽核通過。

前端新明細將排程起始已存版本數與本輪market_updated分開，matched只稱版本候選；未知更新數不補0。已保存分頁／快取及10/16/22執行邏輯不變。這批前端95項測試、型別與本機建置通過，尚未部署。

每日含正式／預覽／前後端最多20次；發布前走根目錄scripts/release_guard.py及deploy/README.md。額度未知時不push，本機git.deploymentEnabled=false尚未同步；02:55已另外在Vercel移除SIMPLES Git連接並確認，停用自動Git觸發。不得藉重新收集或同步來代替唯讀查驗。

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

### 2026-10-31 03:00 稀缺掃描與依名單找貨

`scheduler.py` 另有 03:00 夜間時段（`night()`，flow=`demand_night`），不跑反查佇列：
1. `ingest.scan`：依已啟用的掃描主題（可只填格式＋國別、不填歌手）分頁搜尋 Discogs。搜尋結果自帶的 community want/have 若存在，先排除 Want < `SCAN_MIN_WANT`（50）或 Want/Have < 主題比值者，不打單張請求；通過者以 `/releases/` 回應決定是否加入，並同時寫入 USD 行情快照。每晚 Discogs 請求上限 `SCAN_REQUEST_BUDGET`（600）、新增版本上限 `SCAN_MAX_NEW`（150），各主題平分；中途用完時不推進頁碼，下次同頁接續（已存版本略過）。手動「掃描與抓價」同樣套用 Want 下限。
   - 2026-10-31 補充：Discogs 搜尋每組條件最多 200 頁（1 萬筆），第 201 頁回 404。掃描一律帶 `sort=want&sort_order=desc`（正式實測有效：日本黑膠第 1 頁 Want 11,980 起，第 200 頁約 227）。未指定歌手或年份的主題依序掃「全部年份的前 1 萬筆」再逐年（1950 至今年）；一頁最低 Want 已低於門檻或到最後一頁即換下一年，全部掃完回到開頭。進度存在 meta `scan_cursor:{主題 id}`（segment、page），`scan_targets.next_page` 同步顯示頁碼。指定歌手或年份的主題只有一段。
2. `demand_queue.run`：取最新快照 Want ≥ 50 且 Want/Have ≥ `DEMAND_MIN_RATIO`（2）的版本，依「歌手＋專輯名」合併為專輯；Discogs 無人在售者優先，再依最高比值、Want 排序；每晚最多 `DEMAND_ALBUMS`（100）張，同專輯 7 天內不重搜（meta `demand_search:*`）。每張專輯以 `sourcing.find_many` 對 Yahoo TW／JP、露天、Tower 搜一次（Rotten Blues 僅篩目錄單頁，不納入），對該專輯所有追蹤版本套用 `source_match.evidence`。本次回傳的商品寫入 source_checks（已配對 matched、其餘 unmatched，30 天），不進反查佇列；反查佇列已檢查過的商品保留原狀態。
3. 重新評分與 Sheet 同步；結果含 scan／demand 統計與 `timings`（scan、demand、analyze、sheet_sync）。

白天 10/16/22 反查每輪由 20 件提高為 60 件（`REVERSE_LIMIT`）；手動批次維持 1–40 件。`direct_matches.compute` 改用目錄號、條碼、歌手索引，只比對可能通過的組合，輸出與逐一比對相同（測試以舊迴圈對照）；3000 版本 × 4000 貨源由約 55 秒降為 0.7 秒。

## Discogs 與 Sheets

`discogs_client.py` 是 GET-only：`/database/search`、`/releases/`、`/marketplace/stats/`。2026-10-30 起行情幣別為 USD 時，`ingest.fetch_one` 直接採用 `/releases/` 回應內的 `lowest_price`／`num_for_sale`（該欄位固定為 USD，忽略 curr_abbr；已對 7 張正式唱片與 stats 逐一比對相同），每個版本只打 1 次；其他幣別或欄位缺漏仍補打 stats。使用設定內 token 和 User-Agent；SQLite api_budget 共用 1.1 秒間隔；剩餘額度低時冷卻，429／5xx 或暫時連線問題最多 4 次嘗試，尊重 Retry-After。不要另建無節流 client 平行灌請求。

`ingest.py` 保存版本與行情；`analyze.py` 分析；`comparisons.py` 算含幣別換算的價差／毛利／扣設定費用後淨利；`sheet_sync.py` 的 build_tables/sync 是唯一表格輸出契約。沿用已指定 Sheet 與應用程式管理的分頁，不能覆寫使用者其他分頁。快取命中並不代表來源報價新鮮，前端 48 小時篩選與缺值語意需保留。

配對、報價核對、草稿、正式刊登是不同狀態。`workflow.py` 匯出會重查已排除配對、48 小時確認期限、報價更新與來源 URL 一致性。Quicklister 是檔案匯出；`discogs_publish.py` 的 `/api/listings/publish` 才會呼叫 Discogs 建立刊登，且需後端 `DISCOGS_LISTING_WRITE=1`（2026-10-12 僅本機實作，未部署、未驗收）。送出紀錄在 meta `listing_submission:*`，結果不明時阻擋匯出與重送，見根目錄 docs/DISCOGS_LISTING.md。

## 驗證

```bash
.venv/bin/python -m unittest tests.test_source_queue tests.test_source_match tests.test_matching tests.test_direct_matches tests.test_comparisons
.venv/bin/python tests/run_offline.py
```

HTTP 完整流程測試在允許 localhost bind 的隔離測試環境執行；測試 subprocess 不應繼承正式 REMOTE_ACCESS_TOKEN／FRONTEND_ORIGIN／PUBLIC_API_ORIGIN，避免 fixture 被正式 Origin 拒絕。不得因此修改正式服務的認證設定。外部服務 mock、API 工作成功、真實平台連線與 Sheet 回讀各自說明，不混成「全流程已上線」。

2026-10-30 起排程收集與貨源刷新各平台並行（同站仍依序、間隔 3 秒），Discogs 維持依序；工作結果含 `timings` 分段秒數可判斷瓶頸，以及 `scores_pruned`（該輪刪除的舊評分列數，06a4151 之後的版本才寫入；之前的排程紀錄沒有此欄位，要看 `SIMPLES_Data_scores` 列數）。前端以 `Accept: application/vnd.simples.packed+json` 取得分欄壓縮的比價列（`workflow.comparisons_packed`，由 `state_pack.unpack` 還原）；診斷時不帶此標頭即取得原格式 `workflow.comparisons`。2026-10-29 起 Sheet 主資料源唯讀連線不再比對表格，快取到期改背景重載，`/api/state` 的 storage 含 loaded_at／refreshing／refresh_error；衍生結果依資料版本快取，資料變動後第一次讀取較慢屬正常。2026-10-30 起背景工作的 Sheet 寫入延後合併（60 秒或 25 筆一次、工作結束必沖刷），工作執行中 Sheet 原始分頁可能落後本機最多一分鐘，核對工作結果以 API 與工作完成後的 Sheet 為準。

診斷前端最近工作時，失敗 detail 可能只是例外名稱，執行中可能為 null。`frontend/lib/collection-job.ts` 同時辨識收集／排程工作名稱及 JSON detail，不能只找最近成功 JSON。完整待開發項目見根目錄 `docs/IMPLEMENTATION_STATUS.md`。

庫存讀回新模組 `inventory_sync.py` 與端點、分頁及關聯規則見根目錄 `docs/INVENTORY_SYNC.md`；完整快照另會對帳結果不明的刊登送出（`reconciled`）；此為開發中功能，勿將既有行情 API 成功視為庫存端點已驗收。

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

### 2026-09-13 VPS 刷新部署與正式驗收完成

透過 Chrome Hostinger SSH 管理加入臨時部署公鑰，連上 srv1542946；備份舊 source_refresh.py / source_queue.py 到 backups/refresh-20260913，部署 source_details.py、source_refresh.py、source_queue.py。三個檔案 SHA-256 與本機一致，主機 Python 編譯通過，僅重新啟動 music-business，服務 active。

正式 API 工作 #81 已完成（partial）：22 件嘗試、21 件更新；露天 16/16、Yahoo TW 2/2、Yahoo JP 2/2、Tower 1/2。Tower 8142237 身分核對不符，保留舊價格與舊抓取時間，記錄 identity_changed，並未偽裝成功。正式 SQLite 回讀確認四平台更新時間、價格與失敗保留結果；行情更新 20 版，1,191 件沿用快取，未新增主題或商品。Sheets 回報同步成功 143 行行情（未逐格回讀）。Chrome 正式網站登入與資料呈現正常。

排程 enabled，仍由 VPS 每日台灣時間 10:00、16:00、22:00 執行；下輪 9/13 10:00。新功能部署後的自動時段尚未到，已用相同正式流程手動驗收一輪，不宣稱排程新一輪已完成。部署臨時公鑰已從 Hostinger 移除。此紀錄取代上方後端待部署／管理連線阻塞狀態。

### 2026-09-13 版本證據與刷新优先順序

新增 identity_data：驗證 GTIN-8/12/13/14 檢查碼，統一等價補零表示，拒絕無效／全零碼。Discogs 搜尋 barcode 與版本 identifiers.Barcode 隨正常讀取保存；來源可讀明確 JAN/EAN/UPC/條碼標記，Tower 詳情的 GTIN/SKU 通過檢查碼後作商品碼證據，同步保存品牌 Label。SKU 通過檢查碼不等於已驗證 GS1 登記或唯一壓片；缺碼不猜。來源補充資料綁定原商品身分，名稱／格式／編號變更後不沿用；新增證據只讓該件重新反查，沒有清空全部身份快取。

雙方有效條碼衝突排除配對，即使名稱或唱片編號相同；相同碼仍須核對壓片，格式與唱片編號衝突不能被條碼／Label 蓋過。來源明確 Label 相同提供輔助理由；原同名／同格式仍是候選。直接比對快取升 v4，包含新證據；前端顯示條碼一致／衝突，不自動確認版本。

新增 refresh_priority：先保留至少 1 件、约四分之一名額輪替最久未嘗試的舊資料，其餘依採購意向、正預估毛利金額、Want 人數排序；採購意向／正毛利／Want≥100 至少隔 6 小時更新，其餘至少隔 24 小時。原 1 小時失敗重試冷卻、每輪露天最多20件及其他平台各2件、每日10/16/22排程不變。頻率是最短間隔，不保證所有資料在該期間輪到。工作明細保存優先／輪替選取數。

採購清單內容仍在瀏覽器；新增／移除已存商品同步 VPS 的優先設定。既有清單可按「將清單設為優先更新」，不下單、不上架、不建立人工報價。端點 /api/purchase-priority 接收既有 source_urls 與 enabled，驗證整批後原子更新，不接受任意未知網址。

174 項完整離線測試通過（15 項 socket 未跑）；相關前端17項＋新增條碼衝突項通過。本機完整型別檢查因既有依賴讀取停滯中止，未宣稱通過。後端已部署，正式 #86 驗證每個詳情平台1個優先＋1個輪替；6件5成功，日本Yahoo1件404保留失敗。新增Tower證據的正式 #87 與前端部署／採購優先畫面驗收正在進行，完成後補記。

正式驗收補記：Vercel 4DHTeEa2mpyFTWEjArGZZNrpvSEx 已成功部署；VPS 12 個後端檔案與本機 SHA-256 一致。正式 #87 以新證據只重新反查1件、沿用1190件，更新6件中的5件；Tower 3012920 名稱變更仍保留失敗，Sheets回報143行同步成功（未逐格讀回）。Tower正式庫新增1件商品碼及Label；另更新兩個既有Discogs版本，其中6967698保存有效條碼，6890075無有效條碼則保存空值。現階段不是所有來源都有條碼，沒有冒稱條碼配對已全面覆蓋。

Chrome正式網站以既有Yahoo商品驗證加入採購清單，VPS優先標記回讀為true；商品未滿6小時不會強制再次抓取。隨後透過畫面移除，清單回到0件、正式優先標記回讀0筆；未新增報價、下單或刊登。舊清單「將清單設為優先更新」按鈕與說明已顯示。自動排程維持每日10/16/22，部署後首個自動時段仍待到時驗證。

### 2026-09-13 Google Sheet 主資料源遷移

依最新要求，新增 Sheet 原始資料讀寫層，以記憶體 SQL 引擎沿用比對邏輯，不需要持久 VPS 業務資料庫。24 個正式業務資料分頁已建立並逐表回讀一致；獨立程序從 Sheet 讀回143版本、1269貨源與2609筆比對，未使用磁碟資料庫。採購清單同步介面與版本衝突檢查已實作。正式切換與前端驗收進行中，詳見 docs/SHEET_PRIMARY.md；不把遷移驗證當作正式服務已切換。


### 2026-09-13 Google Sheet 正式切換驗收

正式 API 已使用 google_sheets 且 persistent_local=false，程序沒有開啟本地業務庫。24 個原始資料分頁完成逐表比對；網站新增既有商品至採購清單後，Sheet 立即顯示同一筆，重啟服務及重新登入仍可還原。驗收選取已移除，清單 revision=2、0 件。Vercel 部署成功；184 項後端離線測試、11 項相關前端測試通過，15 項 socket 測試未跑。Sheet 原始表已加上欄寬與標題格式，不改資料值。排程仍為每日10/16/22，切換後自然時段尚待觀察。舊磁碟庫只保留遷移備份，回復前須先匯回切換後的新資料。


正式批次 #91（10:30–10:39）已完成，狀態 partial：反查20件、沿用1208件快取、更新20筆行情；貨源刷新26件中25件成功，Tower 3012920 因 title_changed 保留失敗，不硬套原商品。分析 Sheet 同步成功143行。獨立直接讀原始 Sheet：source_checks=1231、snapshots=301、scores=6979、jobs=91，且工作完成明細已存在 Sheet；這些讀回證明新資料不是只存在服務記憶體。沒有新匹配不代表流程失敗；本輪20件均為 unmatched，保留供日後增量比對。


### 2026-09-13 指定來源反查

正式 #92 已成功完成：收集 Rotten Blues 40件、反查原有佇列20件、刷新26/26貨源、更新20筆行情及Sheet分析同步成功。獨立Sheet回讀顯示Rotten Blues尚未輪到反查，因此新增 source_platform 過濾已存貨源（不新增搜尋、不重設其他來源進度／快取），limit驗證1–40。前端只選一個來源時可按「只比對…已存商品（最多40件）」；正常排程仍沿用全平台20件。工作明細明示指定來源。

Rotten Blues 明確「歌手《專輯》」名稱只在Discogs搜尋時抽出歌手及專輯，保留原商品名稱與版本文字供嚴格比對，不自動翻譯、不寬放格式／編號。26 項相關後端、8 項前端測試通過；部署與本次指定来源比對驗收補記於後。


### 2026-09-13 Rotten Blues 指定反查正式驗收

Vercel Eh2CemvhBiUKXrGiKKvE84bLsZyA 部署成功，VPS 已部署指定來源反查與搜尋名稱清理。正式工作 #93 指定 rottenblues、最多40件，不重新收集、不清除其他來源快取。驗收時 Sheet 直接回讀已完成15件：9件找到版本候選、6件 unmatched；工作仍 running，不代表首批40件完成。

正式 API 曾讀得15組 Rotten Blues 商品／版本比較，其中9組 Want>0 且正預估毛利；這是比較組數，不是9件獨立商品，也不代表壓片已確認。Chrome 正式網站實際顯示 Andrew Hill《Nefertiti》：來源 TWD350、Discogs release 6782488 參考價 USD29.98、Want38、價差／預估毛利 TWD596.31、毛利率63.0%，來源與Discogs連結可見。運費等未完整扣除，不能當作淨利或成交價。新增原始資料已存Google Sheet；本輪最終分析同步仍待工作結束。


### 2026-09-13 Sheet 寫入與比對完整性驗收

正式 #93 於11:47完成：Rotten Blues 40件反查、25件matched候選／15件unmatched、134筆行情更新、26/26舊貨源刷新成功，errors=[]，分析同步257版本成功。直接讀Google Sheet全部24張原始表，257版本、455筆行情、1309件貨源、1291筆搜尋與檢查可在獨立記憶體schema還原；欄位、NULL、主鍵唯一性與外鍵檢查通過，無磁碟業務庫回退。

正式API的2724組比較通過重複key、候選格式／品番／條碼衝突與毛利計算檢查。SIMPLES_Comparisons逐組對照同一API的來源價格、TWD售價、毛利與毛利率，2724/2724一致；SIMPLES_PlatformCandidates有1309件。915組符合正毛利且Want>0，不代表915件獨立商品或已核對壓片。Chrome正式進貨頁當時預設其他價格、新鮮度、供貨篩選後顯示372/2724，並非漏寫。

新增 sheet_audit.py 與 scripts/audit_sheet_data.py，唯讀診斷24張原始表與已運行正式API，不啟動抓取、不修改Sheet、不建立另一套後端。VPS已執行通過，無需重啟。重跑方式：在 /opt/music-business 執行 `.venv/bin/python scripts/audit_sheet_data.py`；exit 0通過、1資料檢查異常、2 API無法驗收。工具只證明讀取快照與結構／數學一致性，不取代壓片人工確認、來源庫存實查或逐次寫入回讀。API讀取與Sheet快照可能不同時，活躍批次中不能以數量變動認定漏寫。

16項診斷與Sheet儲存測試通過；既有測試有連線未關閉ResourceWarning，不影響本次結果。初版稽核對金額顯示四捨五入的毛利率容差太小，已按誤差界限修正並加低售價／高負毛利測試，未修改正式毛利算式以遷就檢查。


### 2026-09-13 每次同步自動讀回核對

sheet_sync 在寫入前檢查比較資料的重複、格式／品番／條碼及毛利算式；寫入後透過一次 batchGet 逐格比對本次寫入的展示分頁（含公式文字）。既有 Inputs 為使用者可編輯參數，不覆寫也不拿舊預設值比對。允許Google省略空白尾欄／尾列，其他差異使工作失敗；只有核對通過才更新last_sheet_sync並回傳verification。批次工作明細自動保存到Google Sheet jobs，前端顯示核對分頁數。原24張原始表完整性工具仍可單獨執行，本次自動核對範圍是同步展示表，不誤稱每輪都完整稽核所有原始表。

18項相關後端測試、6項前端工作明細測試通過；15項需要本機socket的整合測試因執行環境限制未能運行。正式部署與讀回驗收另補記。


正式驗收補記：Vercel G7xkR4fU7rZvKWi7cHY5to5BsTgj 成功部署。Chrome控制連線中斷後，以內建瀏覽器登入正式站，在進貨與Sheets按一次同步（12:01）。工作完成，掃描與設定展開明細顯示「Sheet 寫入後核對通過：5 個分頁，價格與比對資料已讀回確認」及「行情257列、報價0列」。這證明新後端已生效且本次實際寫入後讀回成功；5頁為Comparisons、PlatformCandidates、Discogs、Sources、Analysis，既有Inputs保留不寫。原始24頁稽核與自然排程時段驗證不包含在這次單次同步驗收內。後端部署程式備份位置 /opt/music-business/backups/sheet-readback-20260913。


### 2026-09-13 同步失敗原因與處理提示

新增白名單SyncFailure，區分比對資料異常、讀取失敗、寫入遭拒、寫入結果未知、讀回失敗、讀回不一致與非系統分頁衝突。POST逾時或5xx不宣稱未寫入，不自動重送。單次同步與定時批次皆保存安全的錯誤代碼與允許的分頁名，前端顯示對應處理提示；不保存Google原始回應、憑證或exception文字。既有歷史錯誤紀錄仍相容，不修改歷史或故意製造正式失敗。

22項相關後端與7項前端測試通過；正式部署與正常同步驗收另補記。


正式補記：後端5檔已部署，備份sync-diagnostics-20260913；另修正HTTP5xx為write_unknown，備份sync-diagnostics-http5xx-20260913。Vercel 5iG7eC3uhSZHiurxr5ksGALt9zbu成功。12:08使用正式API執行一次同步，Chrome工作明細顯示5個分頁讀回核對通過、257列行情同步成功。錯誤分支採模擬測試，未故意破壞正式Google Sheet或注入假工作紀錄。


### 2026-09-13 略過未變動的展示分頁

同步先讀取已有的受管理展示表，比較內容與公式，僅對不同或新建分頁送出寫入。所有受驗證分頁（含略過者）最後仍再次讀回核對；全部未變時不送展示表batchUpdate，但jobs及last_sheet_sync等原始紀錄仍正常寫入。Inputs保留原有使用者設定，頁面顯示本次寫入／略過數。此优化減少寫入量，不宣稱免讀取、不宣稱整個同步完全不寫Sheet或已量測加速比例。12項後端、7項前端測試通過，正式驗收另補記。


正式補記：後端已部署，備份sheet-incremental-20260913。正式#96於12:31完成，changed_tables=[]、unchanged_tables為Comparisons／PlatformCandidates／Discogs／Sources／Analysis，5頁再讀回通過：2724比較、1309貨源、257行情。Chrome正式站仍正常登入連線。前端計數提示尚未上線：GitHub commit87906e8的Vercel建置因build-rate-limit失敗，未付費升級或改走其他專案規避限制；待額度恢復再部署。程式已同步GitHub，現有前端沿用先前成功版。此限制不影響已部署的後端略過重寫與自動核對。

## 2026-09-14 待反查進度補強（本機待發布）

`workflow.source_queue.pending` 現在提供與排程相同判定的待反查總數，在同一記憶體查詢連線統計。既有 `unchecked` 只計從未反查；前端分開顯示首次與到期／身份變更重查。首次進度100%仍可能有重查工作，舊後端缺欄位顯示待取得。沿用既有身份快取、價格變動不重搜、失敗重試與分批規則；沒有新增資料分頁或修改業務紀錄。

驗證：支援的Python執行環境下後端離線222項通過（15項socket未跑）、前端97項、TypeScript、本機Vercel build通過。系統Python3.9首次測試因缺sqlite serialize而7項失敗，改用支援環境重跑後通過；沒有修改正式資料層遷就舊Python。本批未推送、未部署，正式API尚未有新pending欄位，正式畫面待合併發布驗收。部署完整額度仍未知。

## 2026-09-14 重查時間判定修正（本機待發布）

重查時間改以含時區的實際時間比較，排程待查數、API進度與反查批次共用同一判斷。不同UTC offset不再以字串先後誤判；損壞或缺時區的retry_at保留原資料並列入待查，由原每批上限逐次處理，成功完成該次查詢後沿用原規則保存新快取。不清空來源或快取、不立即啟動正式工作。

隔離測試涵蓋跨時區先後、等於到期時間、損壞／空／缺時區時間，以及處理後不重複查詢。後端226項離線測試通過，15項socket測試未執行。新行為尚未部署，不能宣稱正式環境已修復。

## 2026-09-14 22:26 最新發布規則與後端部署

每日 20 次只計 SIMPLES 在 Vercel 的正式與預覽部署；Vercel 帳號每日 100 次另行盤點。VPS 後端不受此額度限制，也不消耗 Vercel 次數。這段使用者最新要求取代下方所有「前後端合計20次」舊規則；不能因後端歷史部署次數未知阻擋後端維護。

守門的 frontend／preview 使用 scope=simples_vercel，統計 Vercel；backend 預留0次，只核對提交、測試與正式 API 閒置／下次排程，不要求 Vercel 次數。前端保留集中發布及防誤觸 Git 建置流程。舊 audit 必須重新盤點，不能沿用包含後端的基準。

後端 source_queue.py 已於台灣22:26部署，SHA256=7e4510455e8699d3b2d4ea0e147e2e406b85c1e30614cad75765f8d0a0e14523；備份 backups/queue-time-20260914T142625Z。修正重查時間比較並增加 pending；前端尚未部署。22:00自然工作#101成功，抓取153筆平台結果、反查20件（0候選／20未匹配）、更新20筆行情、刷新28/28貨源、Sheet寫3略過2且5頁讀回通過。部署後獨立Sheet稽核：24表、1528貨源、269版本、567行情快照；2736比較結構／格式／品番／條碼／算式全部通過。923個正毛利需求候選組合不是獨立商品或壓片確認。

集中發布排程時段仍為12:15與21:15；此次更新自動化遭自動審核拒絕，未生效。不可聲稱排程已採用新規則；需另確認持續自動部署授權。VPS資料排程10/16/22不受影響。


## 2026-09-17 公開唯讀目錄正式發布驗收

已將本機 5539113（tree f59f3a556068d6a846fc37137cd3ec368f316454）以保留遠端歷史的 fast-forward 同步為 GitHub c8c1eaa59fbe698d32830afb0a1138117376656a。Vercel 正式部署 7dKFrsG9H9cMQ1cNEtXeBQzhVfWk 為 Ready，正式 /version.json 讀回同一完整 SHA。發布前當日全帳號完整日期篩選盤點35次、SIMPLES 0次，本批新增1次正式前端部署；git.deploymentEnabled=false 保留，文件同步不另觸發建置。

正確 VPS srv1542946、/opt/music-business 於台灣21:34:13完成 server.py 與 public_catalog.py 部署並重啟單一 music-business 服務。備份 backups/public-catalog-20260917T133413Z。第一次傳輸因解壓完整性檢查失敗，在寫檔前停止；確認未寫入後修正，兩檔SHA256均與本機相同，服務active。未操作另一台VPS或crypig專案。

正式匿名 API HTTP200，277版本、2744組比較；逐層公開白名單核對通過，不含採購、草稿、jobs或CSRF。管理者API仍可讀工作、排程且含CSRF；匿名GET草稿匯出HTTP401。Chrome不輸入帳密即顯示目錄，預設近48小時等條件下10個版本；黑膠加US$30篩選顯示1個版本，來源/Discogs連結、格式、Want、價格、毛利率條可見。沒有測試購買、刊登或正式業務寫入；權限錯誤情境沿用已通過的隔離測試。

直接唯讀指定Sheet全部24原始表稽核通過：1601貨源、277版本、735行情快照，2744比較格式/編號/條碼/算式檢查通過；941個正毛利需求候選組合不是獨立商品或壓片確認。DATA_BACKEND=google_sheets與指定Sheet ID均核對正確。今天自然#108（10:00）、#109（16:00）成功；#109收集80筆、反查20件（0候選/20未匹配）、更新20行情、刷新28/28，展示頁寫3略過2、5頁读回通過。21:37:26再次讀取active=null，queue1601/unchecked53/pending70，下一輪22:00；本次部署後自然輪次尚未發生，不能稱已驗收。

本批程式驗證：30項後端、106項前端測試、型別檢查與build已通過。此節正式證據取代下方「公開目錄待發布／Hostinger登出」歷史狀態；完整業務流程與帳號密碼互動登入並未在本批重測。
