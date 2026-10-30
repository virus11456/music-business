## 2026-10-30 排程工作加速與重啟預熱（本機實作，待部署）

- **已抓資料直接交叉比對**：每個 Discogs 版本的目錄號、歌手與條碼改為每次重算只正規化一次，不再對每件貨源重複處理；以正式資料形狀（418 件貨源 × 360 版本）驗證輸出與原寫法逐筆相同（5955 組），2.56 秒 → 1.13 秒，正式約 1600 件貨源時差距更大。歌手為空的版本原寫法在部分情況會丟例外導致讀取失敗，現在視為無法以歌手名稱配對。
- **不同網站並行**：排程收集與貨源刷新改為各平台同時進行，同一平台仍依序並保留 3 秒間隔；報告依固定平台順序組裝。Discogs 反查與行情受每分鐘 60 次限制，維持依序。共用的刷新紀錄表改在開跑前建立。
- **分段耗時**：反向收集工作結果新增 `timings`（collect、source_refresh、reverse_match、market、fx、analyze、sheet_sync，秒），保存在 Sheet 的工作紀錄，下一次排程後即可看出實際瓶頸。
- **預熱**：服務啟動與每次背景工作結束後，在背景先產生公開與管理者兩份回應快取，第一個訪客不必等重算（原本重啟後首次約 7.4 秒）。

驗證：6 項新測試（交叉比對與原寫法等價、空歌手、不同網站並行而同站依序、收集順序與頁碼、分段耗時欄位、預熱命中與 SQLite 模式不預熱）；完整後端離線測試通過。前端無變更，部署只需後端。

## 2026-10-30 正式部署 57c9e81（前端＋後端）與量測

main 經發布守門 fast-forward 至 57c9e81（PR #4）。Vercel 正式部署 dpl_4MAVn3jiHnnYdaBeavbSChVF2bVq，`/version.json` 讀回 57c9e81；部署前全帳號當日 13 次（12 次為其他專案），SIMPLES 為本日第 2 次。前端先上線時以 Accept 要求新格式，實測舊後端照舊回原格式 200、6037 組。後端由操作者在 srv1542946 以 45 個 .py 完整替換（含新增 state_pack.py，manifest SHA256 59198d60b90860c104070e7ef4fe6c6747a4b2778dadfda06037d743fa2c20fb）。

外部量測匿名 `/api/state`：

| 項目 | 原格式 | 新格式 |
|---|---|---|
| 未壓縮 | 9.05 MB | 1.28 MB |
| gzip 傳輸 | 518 KB | 174 KB |
| 快取命中總耗時 | 2.2 秒 | 1.8 秒 |
| 內容未變 | 304、0 B | 304、0 B |

伺服器端快取命中 61 毫秒；重啟後首次 7.4 秒（同步載入 Sheet）加 0.47 秒打包，之後依資料版本重用。新格式還原後與原格式回應逐欄相同（6037 組）。外部總耗時其餘部分為量測端網路往返。

## 2026-10-30 比價資料瘦身：欄位分欄與重複值字典（本機實作，待部署）

正式匿名回應實測 6037 組比較（418 個貨源、350 個版本、8 種配對依據文字），JSON 9.05 MB，平均每組 1.5 KB，多數是相同貨源／版本資料逐列重複與欄位名稱重複。新增 `state_pack.py`：比價列改為依欄位分欄，重複值以字典加索引傳送，缺少的欄位另列索引，可完整還原。前端以 `Accept: application/vnd.simples.packed+json` 要求新格式（CORS 安全標頭、不觸發預檢），後端看到才回新格式並以 `Vary: Accept` 區分；未帶此標頭（含舊前端、curl 診斷）照舊回原格式。前端 `normalizeState` 兩種格式都能還原成相同的 `workflow.comparisons`，元件不變，前後端可任意先後部署。

以正式資料驗證：Python 打包與 TypeScript 還原後與原始資料逐欄相同。比價部分原始 8.93 MB → 1.17 MB，gzip 0.50 MB → 0.16 MB；桌機 JSON 解析時間相近（原格式 26 毫秒、新格式含還原 36 毫秒），效益在傳輸量與回應字串記憶體，行動網路下較明顯。打包結果與 gzip 依資料版本快取。還原後重複值在多列間共用同一物件，前端程式已確認不會就地修改比價列。

驗證：Python 7 項（還原含 null／缺欄位／布林與數字不混淆、字典化、版本拒絕、不改快取、前後端共用對照檔、兩種格式內容一致）、handler 1 項、前端 4 項；完整後端離線、前端測試、tsc 與 build 通過。未部署，需前端（Vercel 1 次）與後端。

## 2026-10-30 正式部署 1b50615（後端）與量測

main 經發布守門 fast-forward 至 1b50615（PR #3），本批只有後端，Vercel 未新增部署。操作者確認 SIMPLES_Data_jobs 無 running、最新 #236（10/29 22:00）已完成後，在 srv1542946 以 44 個 .py 完整替換（manifest SHA256 e5102db9ff9ef3dc7140fe4d6a578286fe4ac3252a6305563ea6b09e4d631360），18:37:30 UTC 重啟，active、NRestarts=0；備份 /opt/music-business/backups/full-20261029T183718Z（7cc99a9 版本）。DEPLOYED_COMMIT 寫入因權限失敗，尚未更新。

外部量測匿名 `/api/state`（Server-Timing 為伺服器端時間）：

| 請求 | 伺服器處理 | 外部總耗時 |
|---|---|---|
| 重啟後第一次（同步載入 Sheet） | 7.5 秒 | 10.2 秒 |
| 快取命中 | 0.07 秒 | 2.1 秒 |
| 內容未變 304 | — | 1.1 秒、0 B |

外部總耗時其餘部分為量測端到 VPS 的網路往返與 0.52 MB 下載。尚待：管理者畫面體感、10/30 10:00 第一輪延後沖刷排程結果。

## 2026-10-30 回應序列化快取、Server-Timing 與 Sheet 重載間隔（本機實作，待部署）

部署 7cc99a9 後實測匿名 `/api/state` 每次仍約 2.5 秒：每個請求都重新投影公開目錄、序列化約 9 MB JSON、再壓縮與計算 ETag。改為依資料版本快取序列化結果、gzip 內容與 ETag；匿名目錄只依資料版本，管理者另納入工作狀態、排程等小欄位。合成資料重複請求由 140 到 230 毫秒降到 1 到 2 毫秒。

修正前一批的問題：管理者回應的 `storage.loaded_seconds_ago` 每秒變動，使登入後的 ETag 永遠不同、304 無效；改為固定的 `storage.loaded_at` 時間戳。回應加 `Server-Timing`（state、encode、cache 命中與否），可在瀏覽器開發工具直接看伺服器端耗時。瀏覽器先斷線時不再記為 500。

Sheet 主資料背景重載間隔由 30 秒改為 5 分鐘（`SHEET_CACHE_SECONDS` 可調、最少 30 秒）。本程序是唯一寫入者，寫入衝突檢查不變；只影響直接在 Sheet 手動改原始分頁後，網站最多 5 分鐘才看到。

驗證：6 項新測試（重用與命中、管理者驗證碼一秒後仍穩定且隨資料或工作變動、SQLite 模式不快取、重載間隔預設與下限、handler 使用快取與 Server-Timing、斷線不回 500），完整後端離線測試通過。前端無變更，部署只需後端。

## 2026-10-30 正式部署 7cc99a9（前端＋後端）與量測

main 經發布守門 fast-forward 至 7cc99a9（含 PR #1、#2）。Vercel 正式部署 dpl_AspLJTf9TeCSG1nrFGLt9jzHiSt7 Ready，`/version.json` 讀回 7cc99a9，今日 SIMPLES Vercel 1 次。後端由操作者在 srv1542946 以 44 個 .py 完整替換（manifest SHA256 c07f626cec0a34580e2f3e4c14b93585763ceb30ec343cf05ec052f22f1a6f8c），部署前讀 log 與工作紀錄確認閒置。

從外部對匿名 `/api/state` 實測：

| 項目 | 部署前 | 部署後 |
|---|---|---|
| 冷讀（快取過期） | 63 秒，9.0 MB | — |
| 一般讀取 | 26 秒，9.0 MB | 2.5 秒，gzip 0.52 MB |
| 內容未變（If-None-Match） | 不支援 | 304，0 B，1.0 秒 |

舊後端回應超過前端 30 秒逾時，即 log 中 500／BrokenPipe 的原因。尚待：管理者登入後的畫面體感、明日 10:00 第一輪延後沖刷的排程結果。匿名回應未壓縮仍 9 MB、每次重新投影與序列化約 1.4 秒，列為下一項優化。

## 2026-10-30 背景工作寫入批次化與比價重算優化（本機實作，待部署）

背景工作（排程、反查、刷新、同步）原本每改一列就對 Google Sheet 做一次讀回比對與寫入，一輪工作數十次往返且每次持鎖約 1 到 2 秒。現在 `Dashboard.start` 內的工作改用資料層的延後沖刷：每筆交易仍立即寫入記憶體並可被讀取，Sheet 寫入每 60 秒或每 25 筆合併一次，工作結束（含失敗）一定沖刷；沖刷結果不明時還原本機檢視並強制重讀，Sheet 被外部改動則在沖刷時偵測並拒絕；有未沖刷資料時不會啟動背景重載。工作期間只有該工作執行緒寫入（dashboard 鎖阻擋其他修改），單筆人工修改仍即時寫入 Sheet。`storage.pending_writes` 顯示尚未沖刷的交易數。

比價重算改為每次建立先一次載入版本、最新行情、標籤、條碼、來源身份、排除配對、刊登紀錄與各幣別匯率，不再逐列查詢；單筆草稿利潤複核沿用逐列查詢的相同介面。待查計數也共用身份快取。合成資料（635 組比較、1600 貨源）重算由 0.21 秒降到 0.16 秒，正式資料逐列查詢比例更高，預期差距更大；實際以部署後量測為準。

驗證：9 項延後沖刷隔離測試（合併寫入、門檻、沖刷失敗還原、交易失敗保留先前工作、工作例外仍沖刷、未沖刷不重載、外部改動偵測、Dashboard 工作三次寫入、本機表不寫 Sheet），完整後端離線測試通過。未部署。

## 2026-10-29 畫面卡頓修正：壓縮、304 不重繪、前端記憶化（本機實作，待部署）

合成資料下 `/api/state` 回應約 1.25 MB，正式資料更大；前端每輪輪詢都整包下載、解析並整頁重繪。修正：後端對 `/api/state` 回應以 gzip 壓縮（合成資料 1.25 MB → 0.06 MB），並附 ETag；前端帶 If-None-Match，內容未變時後端回 304、前端不解析也不重繪，登入狀態改變時重置驗證碼。版本候選（`platforms.matches`）只回傳畫面列出的 200 筆近期貨源對應的搜尋結果，不再送出全部反查結果。首頁的比價索引與刊登狀態改以 useMemo 只在資料或篩選條件變動時重算，打字搜尋與輪詢不再重跑數千列。

驗證：5 項新後端測試（gzip／identity、304 與資料變動後的新 ETag、匿名與管理者驗證碼不互通、錯誤回應不壓縮、matches 範圍）、2 項前端 api 測試；完整後端離線 290 項與前端 112 項測試、tsc、build 通過。未部署，正式環境效果待量測。

## 2026-10-29 載入速度與讀取失敗修正（本機實作，待部署）

量測正式規模的合成資料（277 版本、1600 貨源）：`/api/state` 一次約 7 秒，其中 6.6 秒花在 Sheet 主資料源每次開連線都整份複製 24 張表做前後比對（一次 state 開 12 次連線、比對 24 次），加上前端每 4 秒固定輪詢，請求堆積後 30 秒逾時就顯示讀取失敗；Sheet 快取 30 秒到期時還會同步重載約 9 秒。

修正：唯讀連線只保留快照、不比對，僅在交易真的改動資料列時才還原快照比對並寫入 Sheet（寫入語意與衝突檢查不變）；快取到期改為背景重載、期間照常回應，讀取失敗保留舊快照並 10 秒後重試，背景讀取期間若有本機寫入則作廢該次結果；`records` 與 `workflow` 衍生結果以資料版本（世代＋變更計數）快取，資料未變直接重用；前端改為上一輪回來後再排下一輪，慢或失敗時自動拉長到最多 20 秒。合成資料量測：未變動時 state 由 2.4 秒降到 0.01 秒以下，資料變動後重算約 0.9 秒。

驗證：新增 9 項隔離測試（唯讀不比對、本機表不寫 Sheet、失敗交易仍強制重讀、到期不阻塞、重載期間寫入不被覆蓋、重載失敗續用舊快照、啟動同步載入、衍生快取失效、SQLite 模式不快取），後端離線與前端測試、tsc、build 通過。未部署 VPS，正式環境時間尚未量測；storage 新增 loaded_seconds_ago／refreshing／refresh_error 供核對。

## 2026-10-12 Discogs 刊登送出（本機實作，待啟用與部署）

新增 `discogs_publish.py` 與 `POST /api/listings/publish`：以已勾選、通過匯出檢查的草稿直接建立 Discogs 刊登（預設 Draft，可選 For Sale），每件先記錄再送、只送一次。4xx 為 failed 可重送；5xx／斷線／回應不完整為 uncertain，停止同批其餘草稿並阻擋該草稿的匯出、AI 文案與再送，直到庫存讀回自動對帳或人工以 `/api/listings/submissions/resolve` 核對。成功寫入 published_listings。需後端 `DISCOGS_LISTING_WRITE=1` 才啟用；Discogs 帳號仍停權，未送出任何真實請求。前端上架整理頁新增「送出到 Discogs」面板與草稿送出狀態標示。

驗證：16 項新隔離測試，後端離線 275 項、前端 109 項、tsc 與 build:vercel 通過。未部署、未正式驗收；詳見 docs/DISCOGS_LISTING.md。

## 2026-09-17 公開唯讀目錄正式發布驗收

已將本機 5539113（tree f59f3a556068d6a846fc37137cd3ec368f316454）以保留遠端歷史的 fast-forward 同步為 GitHub c8c1eaa59fbe698d32830afb0a1138117376656a。Vercel 正式部署 7dKFrsG9H9cMQ1cNEtXeBQzhVfWk 為 Ready，正式 /version.json 讀回同一完整 SHA。發布前當日全帳號完整日期篩選盤點35次、SIMPLES 0次，本批新增1次正式前端部署；git.deploymentEnabled=false 保留，文件同步不另觸發建置。

正確 VPS srv1542946、/opt/music-business 於台灣21:34:13完成 server.py 與 public_catalog.py 部署並重啟單一 music-business 服務。備份 backups/public-catalog-20260917T133413Z。第一次傳輸因解壓完整性檢查失敗，在寫檔前停止；確認未寫入後修正，兩檔SHA256均與本機相同，服務active。未操作另一台VPS或crypig專案。

正式匿名 API HTTP200，277版本、2744組比較；逐層公開白名單核對通過，不含採購、草稿、jobs或CSRF。管理者API仍可讀工作、排程且含CSRF；匿名GET草稿匯出HTTP401。Chrome不輸入帳密即顯示目錄，預設近48小時等條件下10個版本；黑膠加US$30篩選顯示1個版本，來源/Discogs連結、格式、Want、價格、毛利率條可見。沒有測試購買、刊登或正式業務寫入；權限錯誤情境沿用已通過的隔離測試。

直接唯讀指定Sheet全部24原始表稽核通過：1601貨源、277版本、735行情快照，2744比較格式/編號/條碼/算式檢查通過；941個正毛利需求候選組合不是獨立商品或壓片確認。DATA_BACKEND=google_sheets與指定Sheet ID均核對正確。今天自然#108（10:00）、#109（16:00）成功；#109收集80筆、反查20件（0候選/20未匹配）、更新20行情、刷新28/28，展示頁寫3略過2、5頁读回通過。21:37:26再次讀取active=null，queue1601/unchecked53/pending70，下一輪22:00；本次部署後自然輪次尚未發生，不能稱已驗收。

本批程式驗證：30項後端、106項前端測試、型別檢查與build已通過。此節正式證據取代下方「公開目錄待發布／Hostinger登出」歷史狀態；完整業務流程與帳號密碼互動登入並未在本批重測。

## 2026-09-16 公開唯讀目錄（本機實作，待發布驗收）

驗證：30 項後端權限／登入測試、106 項前端測試、型別檢查及正式 build 通過。Hostinger 已登出，目前無法核對正式 API active／jobs／schedule／source_queue，故尚未推送或部署。遠端 main 仍 ccce258，Git 自動部署設定仍為 false。

發布順序：先部署相容舊後端的新版前端（舊後端仍要求登入），確認 Ready 後才於工作閒置時部署 server.py 與 public_catalog.py。不可先改後端讓舊前端收到精簡公開回應。兩者完成後，以無 Authorization 的正式 GET 驗證公開白名單、瀏覽器驗證免登入，並以管理者 GET 驗證私密資料仍可讀。

使用者明確核准無需登入即可查看唱片、貨源連結、來源價格、Discogs 參考價、Want 與預估毛利／毛利率。`public_catalog.py` 以欄位白名單產生公開回應；排除人工報價內的草稿／採購資訊、採購清單、上架草稿、決策、通知、Sheet 連結、工作紀錄、API 狀態及憑證。所有寫入與 CSV 匯出仍須原有驗證；Host／Origin 規則保留。公開端不回傳 CSRF，帶錯誤憑證不降級為公開成功。

前端同一網址預設顯示免登入目錄，保留格式、最低售價、Want／毛利排序及最佳貨源折疊；管理者可另開登入表單。Google Sheet 主資料源、既有帳密與排程不變。部署與正式匿名／管理者權限驗收須另記錄，不能把本機測試視為上線完成。

# VPS 部署

## 2026-09-15 前台帳密重設（待正式發布）

登入頁新增設定／重設帳號密碼畫面；管理者在指定VPS產生30分鐘一次性驗證連結，前台不提供公開索取token的端點。連結token放URL fragment並於畫面載入後清除，伺服器僅保存token雜湊與期限。新密碼須由使用者自行在前台填寫兩次，不必操作終端。帳密更新使用scrypt與原子檔案寫入，重設token先消耗，跨程序鎖避免重複使用；成功後清除現有session。原存取碼備援仍保留。

自動審核曾拒絕帶HTTP連結發放端點的方案；已移除，改成本機限定發放並通過檢查。23項後端登入／重設與來源防護测试通過，沒有在正式環境設定測試密碼或消耗正式連結。正式部署及使用者完成設定需另驗收。

## 2026-09-14 帳號密碼登入（待設定與部署）

新增單一管理者帳號密碼登入、scrypt加鹽雜湊、8小時記憶體工作階段、每分鐘10次全域登入限速、登出撤銷；保留原管理者存取碼備援。登入限定原有HTTPS Origin與Host，寫入沿用CSRF。新secret檔案secrets/admin-login.json屬身分驗證設定，不是業務資料，不提交Git或輸出密碼。服務重啟撤銷工作階段。

密碼由使用者親自在srv1542946互動終端執行 `sudo -u music /opt/music-business/.venv/bin/python /opt/music-business/scripts/setup_admin_login.py` 設定（預設帳號admin），不得將新密碼傳入對話、命令參數或由代理代填。至少15字元，須輸入兩次；原子寫入且權限600。設定完成後重啟服務會撤銷舊session。不得在設定或正式驗證尚未完成時聲稱可以帳號密碼登入。

本次正式唯讀診斷：API預檢204、未登入401，CORS允許正式前端；Chrome登入表单顯示管理者存取碼，實際登入失敗原因仍待使用者確認。沒有重設既有憑證。

## 2026-09-14 23:17 前端集中發布完成

使用者明確授權後，Vercel已重新連接virus11456/music-business；保留frontend/vercel.json git.deploymentEnabled=false。重新連接未自動建立部署；手動指定61db27e正式發布一次，deployment RRQ87ipjqbVksLbnhSJNUtxXrVc1，Ready，建置6秒。公開正式/version.json HTTP200回傳完整61db27e629abca5a4019b56ef129e15aa789b3f9；首頁HTTP200，已送出新JS index-tAinbgqb.js。Chrome正式首頁可見SIMPLES，等待管理者登入。本次未進行登入後互動驗收或新增業務寫入，不冒稱全部正常流程已驗證。

發布前23:15:59正式API active=null、無running工作、#101 success，Sheet主資料源正常，queue1528／unchecked139／pending149，下次9/15 10:00。Vercel發布前當日完整兩頁：帳號33、SIMPLES0；此次增加1個正式部署。本機保守預留另含先前被審核拒絕的嘗試，不把預留數當實際部署數。沒有新增預覽部署，沒有重啟後端。

本批已發布寫入／略過分頁提示、實際工作數量與未知狀態、重查進度、唱片刊登未知狀態篩選。101前端測試、型別檢查與建置已通過；故障情境限隔離測試。後端時間修正已於22:26部署。持續自動發布heartbeat的獨立授權尚未更新；本次授權只恢復Vercel/GitHub連接。

## 2026-09-14 發布窗口範圍

SIMPLES發布前核對project_deployments_idle=true（本專案沒有排隊或執行中的Vercel部署），並使用新鮮專案／帳號次數及本機鎖定預留。其他專案不必停止發布；不宣稱能鎖定全帳號。此流程取代舊exclusive_release_window要求。每次正式操作前重新核對可用次數，結果不明先查紀錄，不自動重試。

## 2026-09-14 純Git同步與連接器流程

已確認Vercel Git連接停用時，純Git同步不觸發部署，不要求Vercel額度或其他專案停止發布；仍須乾淨提交、測試、正式API與自動建置停用證據。release_guard.validate/reserve 的target=sync負責上述檢查。

CLI無登入時允許使用既有GitHub連接器：先讀遠端main，確認是已審查的基準；以受追蹤差異建立tree，必須與本機HEAD tree相同；新commit以剛讀取的遠端main為parent，保留遠端歷史與本機提交。更新分支前再次讀遠端parent及自動部署設定，以reserve(...,target='sync',slots=0)記錄新鮮盤點，通過後僅對virus11456/music-business main做force=false的fast-forward；結果未知先讀回不重送。建立未連到分支的Git objects不觸發部署。不能借此進行Vercel發布，發布仍須另計額度。此明確流程優先於舊文件僅允許Git CLI的描述。

## 2026-09-14 22:26 最新發布規則與後端部署

正式 HTTPS API 部署後讀回：active=null，google_sheets／persistent_local=false；source_queue total=1528、unchecked=139、pending=149；最新工作仍#101 success。systemd active、啟動22:26:25、NRestarts=0；下一輪2026-09-15 10:00。本次沒有觸發新抓取／同步寫入，部署後完整自然輪次尚待觀察。發布守門與來源佇列28項測試通過。

每日 20 次只計 SIMPLES 在 Vercel 的正式與預覽部署；Vercel 帳號每日 100 次另行盤點。VPS 後端不受此額度限制，也不消耗 Vercel 次數。這段使用者最新要求取代下方所有「前後端合計20次」舊規則；不能因後端歷史部署次數未知阻擋後端維護。

守門的 frontend／preview 使用 scope=simples_vercel，統計 Vercel；backend 預留0次，只核對提交、測試與正式 API 閒置／下次排程，不要求 Vercel 次數。前端保留集中發布及防誤觸 Git 建置流程。舊 audit 必須重新盤點，不能沿用包含後端的基準。

後端 source_queue.py 已於台灣22:26部署，SHA256=7e4510455e8699d3b2d4ea0e147e2e406b85c1e30614cad75765f8d0a0e14523；備份 backups/queue-time-20260914T142625Z。修正重查時間比較並增加 pending；前端尚未部署。22:00自然工作#101成功，抓取153筆平台結果、反查20件（0候選／20未匹配）、更新20筆行情、刷新28/28貨源、Sheet寫3略過2且5頁讀回通過。部署後獨立Sheet稽核：24表、1528貨源、269版本、567行情快照；2736比較結構／格式／品番／條碼／算式全部通過。923個正毛利需求候選組合不是獨立商品或壓片確認。

集中發布排程時段仍為12:15與21:15；此次更新自動化遭自動審核拒絕，未生效。不可聲稱排程已採用新規則；需另確認持續自動部署授權。VPS資料排程10/16/22不受影響。



## 2026-09-14 固定集中發布時段

使用者要求主動訂定發布時間，已建立本項工作heartbeat「SIMPLES 集中發布」（simples），每日Asia/Taipei **12:15、21:15** 接續盤點、集中發布及正式驗收；首次2026-09-14 12:15。這是發布工作提醒，與VPS每天10/16/22資料排程及Discogs申訴追蹤分開。沒有待發變更不空部署；有待發變更主動排除阻礙，不能無限停在本機完成。20次總上限與真實盤點要求不變；若仍受阻須報具體原因與下個時段，不把排程建立當作部署成功。

同批修正工作明細：缺少／無效數量顯示未知，實際0保留；不明Sheet錯誤與損壞明細先要求讀回，不引導直接重送。新前端仍待上述集中發布驗收。

## 目前發布規則（2026-09-14）

每天以 Asia/Taipei 00:00 至翌日 00:00 計算，全部部署合計最多 **20 次**，包含正式、預覽、前端、後端。保守將已啟動、失敗、取消、結果未知及重試各算一次；不能只統計 Ready。前後端同批各部署一次就是 2 次。唯讀查驗、測試及本機 build 不算部署。Vercel 其他專案也可能共用額度；未釐清總範圍前採團隊全部部署加後端，不改其他專案設定。

先累積本機開發、測試及 commit，再集中發布。推送／文件更新可能觸發 Vercel；**額度未知時只保留本機提交**。禁止 force push、reset 遠端歷史、付費升級或以其他專案規避上限。

`frontend/vercel.json` 新增 `git.deploymentEnabled=false`，用來停用所有分支的自動 Git 部署（含預覽）。這是待同步設定，**不是目前 Vercel 已停用的證明**。第一次同步前先從 Vercel Git 設定停用連接並確認沒有排隊建置，避免為套用保護先耗用不明額度；之後維持明確發布。Ignored Build Step 的取消紀錄不能當作零次，也不能冒充部署計數器。官方設定：[Git Configuration](https://vercel.com/docs/project-configuration/git-configuration#turning-off-all-automatic-deployments)。

### 單一發布窗口

發布操作者（可由開發代理完成，不要求使用者補業務資料）負責：

1. 唯讀查驗 Vercel 當日所有環境／狀態／分頁，及後端部署紀錄；補入所有已啟動或不明結果，不以 systemd 重啟次數直接當部署次數。與其他發布者確認本批期間不另行部署，無法確認就不發布。
2. 讀正式 `/api/state` 的 active、jobs、schedule、source_queue；工作未完、狀態未知或距下個排程不到 15 分鐘時暫緩。不手動重送自然工作。
3. 完成本批測試、檢查 Git 差異與憑證排除、提交。由 `deploy/release-audit.example.json` 產生忽略追蹤的 `secrets/release-audit.json`，只保存安全盤點摘要、證據位置和目前 HEAD；不放 Authorization、CSRF、憑證或原始 API 回應。未知欄位維持 null／false，不能為通過守門而猜值。
4. 用 `python3 scripts/release_guard.py --target frontend --check` 試算。盤點有效期 5 分鐘、API 狀態 2 分鐘；跨台灣日期／HEAD 改變需重新查驗。
5. 每次外部部署用 `python3 scripts/release_guard.py --target frontend -- <單次部署命令與參數>`；預覽用 `preview`、後端用 `backend`。每次命令只能含一次外部部署，不能包迴圈、重試或同時部署前後端。程式先鎖定同一盤點檔、持久預留 1 次，再執行命令；失敗、逾時或中斷不退回次數。不自動重試。
6. 已確認自動部署停用後，Git 單純同步用 `python3 scripts/release_guard.py --target sync -- git push origin HEAD:main`，不消耗部署次數但仍需要完整證據。任何待發布工作只能在遠端狀態與額度均已核對後執行。
7. 等部署結束，核對正式版本與網站／API／Sheet，再報告完成。寫入結果不明先讀回；不得把 accepted、running、本機 build 或單元測試當作正式驗收。

`deploy/pre-push` 是本機防誤推送 hook，複製至 `.git/hooks/pre-push` 並設可執行；既有 hook 不可直接覆寫，須整合。此工作副本已安裝。環境旗標僅由守門子程序設定，不可手動用來跳過核對。

**限制：**這套守門保護使用同一盤點檔的發布窗口，不是已上線的跨裝置／全帳號計數器。不能攔截他人直接按 Vercel Redeploy、其他 checkout、GitHub connector 或直接 SSH 部署；因此未能確認獨占窗口／完整基準就保持阻擋。更新盤點時先查明既有預留是否已包含在實際紀錄，不可清空不明預留求取額度。9/14 02:55已在Vercel移除SIMPLES Git連接並確認未連接儲存庫，正式首頁仍HTTP200；未觸發部署。團隊當日可見12次（10正式、2預覽），其他發布者仍活動。VPS沒有完整部署流水帳；程式mtime與service生命周期沒有今日變更不足以當作精確零次。總額度未核實，本批不發布。

## 現行後端架構

唯一正式後端是 srv1542946、`/opt/music-business`、systemd `music-business`；**不要操作 srv1527356**。Google Sheet 是唯一持久業務資料源，`DATA_BACKEND=google_sheets`；SQLite 只作記憶體 SQL。不在 Mac 啟動正式後端或排程，不再按下面歷史第 3 步搬入磁碟庫。既有 Inputs／採購／未配對快取均保留，詳見 `docs/SHEET_PRIMARY.md`。

## 歷史重建紀錄（不直接照做）

2026-09-11 已部署於使用者核准的 Hostinger srv1542946（Ubuntu 24.04 / 2 核心 / 8 GB）。後端 https://srv1542946.hstgr.cloud，程式 /opt/music-business，使用 music 帳號與 systemd。以下保留重建步驟。

1. 在主機建立非 root 的 music 帳號，專案放 /opt/music-business；建立 data、logs、secrets 目錄並設定 music 擁有權。
2. Python 3.11+ 建立 .venv；安裝 google-auth 與 requests（目前 Mac 已驗證版本分別 2.58.0、2.34.2）。
3. 私密傳入 Discogs 設定、Google service-account JSON 及 SQLite 一致性備份；環境檔與憑證權限 600。轉移後以 VPS 為唯一正式資料與排程，停用 Mac 正式排程，避免雙重執行。
4. .env 設 REMOTE_ACCESS_TOKEN 為本機產生的隨機至少 32 字元管理者存取碼；FRONTEND_ORIGIN=https://music-business.vercel.app；PUBLIC_API_ORIGIN=https://實際後端網域。所有網址不得含路徑或查詢。
5. DNS 指向主機，Caddy 提供 HTTPS，反向代理 API 至 loopback 8765；外部不開放 8765。Caddyfile.example 必須換成實際網域。
6. 確認路徑後安裝 music-business.service，啟動一個後端程序。內建台灣時間 10:00、16:00、22:00 排程；不要另外安裝 crontab.example，避免重複。
7. Vercel 設定 VITE_API_ORIGIN=https://實際後端網域 並重新部署。只把公開網址放 Vercel，不把管理者存取碼或第三方金鑰放進前端建置設定。
8. 驗證未登入回傳 401、錯誤來源 403，登入後讀取、更新、Sheets 同步、CSV 下載與排程正常。存取碼只保留於頁面記憶體，重新整理需再登入。

單一管理者存取碼是目前的登入方式，非多帳號權限系統。更換存取碼並重啟服務即可撤銷舊碼。勿在代理存取日誌記錄 Authorization。

Caddy 官方參考：https://caddyserver.com/docs/caddyfile/directives/reverse_proxy


### 2026-09-15 帳密儲存修正

正式重設曾因systemd ProtectSystem=strict禁止寫入secrets而中斷回應，帳密檔未建立。認證狀態改存已允許寫入的data/auth（僅認證設定，不是業務資料）；目錄700、檔案600。部署需保留原一次性重置紀錄並核對服務隔離內可寫性，不放寬systemd保護。儲存OSError回覆安全503與AUTH_STORAGE_UNAVAILABLE，不洩漏原始例外。使用者輸入與提交新密碼仍需本人完成；正式儲存結果待驗證。
