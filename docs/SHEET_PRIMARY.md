# Google Sheet 主資料源

## 2026-09-14 自然排程回讀

本次經Chrome直接選取指定Sheet的SIMPLES_Data_jobs，讀回#97（9/13 16:00:06–16:08:48）與#98（22:00:23–22:09:59）均success，時間轉為Asia/Taipei。#98保存收集73筆結果、反查20、行情更新20、刷新28/28，以及changed_tables=3、unchanged_tables=2、verification.ok=true／tables=5；當次PlatformCandidates展示1379列、Comparisons2724組、Discogs257列。#97先處理佇列未收集新頁，符合既有設計。

後續於台灣02:55登入正確VPS主控台，以既有憑證讀公開HTTPS API200，active=null、google_sheets且persistent_local=false。執行既有scripts/audit_sheet_data.py完成24張原始表還原、主外鍵及NULL稽核，errors=[]；1379貨源、257版本、495行情快照。API2724組比較的身份衝突與毛利算式稽核也無錯，915正毛利需求組合並非独立商品或確定壓片。範圍為唯讀單次快照，未做寫入探測或重新逐格比對展示表。下一自然時段9/14 10:00仍待發生。

使用者於 2026-09-13 明確指定：既有 Google Sheet 為唯一業務資料來源；VPS 只執行程式與排程，不維護另一份持久業務庫。此要求取代先前 VPS 主庫／Sheet 副本的安排。

## 實作

`DATA_BACKEND=google_sheets`、`GOOGLE_SPREADSHEET_ID` 與既有服務帳戶授權啟用新資料層。`db.connect` 將原 SQL 查詢交給記憶體 SQLite，資料由 Sheet 載入；不開啟本地業務資料庫，也不在 Sheet 失敗時退回舊庫。每次業務變更須 Google Sheets 批次寫入成功才回報成功。失敗或結果不明時重新讀回，不盲目重送。

`SIMPLES_Data_` 分頁為原始業務資料：版本、歷史行情、貨源、版本建議、未配對快取、抓取進度、費用、匯率、評分、決策、採購、草稿、刊登／匯出紀錄與排程狀態。保留 ID 關係。`__null_columns` 區分真正缺值與空字串，不應任意修改。金鑰／登入憑證不放進 Sheet，未知 meta 設定不匯出；API 限速計數及可重建比對快取僅在記憶體。

既有 `SIMPLES_Comparisons` 等為分析／閱讀用途的衍生表，沿用原同步流程更新；修改衍生表不會變更原始資料。既有 Inputs 保留。主資料表快取 5 分鐘（`SHEET_CACHE_SECONDS`，最少 30 秒；2026-10-30 起，原為 30 秒）；到期後由背景執行緒重新讀取 Sheet，期間請求仍以現有快照回應，讀取失敗時保留舊快照並於 10 秒後再試（2026-10-29 起，取代原本到期即同步阻塞重載）。唯讀連線不再逐表比對；只有真的改動資料列的交易才做寫入前後比對與 Sheet 寫入。背景讀取期間若有本機寫入，該次讀取結果作廢，下一輪再讀。寫入結果不明時仍強制下一次同步重讀。背景工作期間 Sheet 寫入延後合併（每 60 秒或 25 筆、工作結束必沖刷），人工單筆修改仍即時寫入。程序重啟重新載入 Sheet。Google Sheet 仍有讀寫配額及多人協作限制，部署維持單一後端寫入程序；寫入前核對最後讀取，遇衝突停止，不能宣稱 Google 提供完整資料庫式 compare-and-swap。避免在程式寫入同時直接修改系統資料列。

採購清單改存 `SIMPLES_Data_purchase_items`，並與刷新優先設定一併寫入。清單版本防止兩裝置覆蓋；舊 localStorage 清單由使用者按合併匯入，不自動清除。

## 遷移與驗證

`scripts/migrate_sheet_data.py --db <舊庫> --sheet-id <既有指定 ID>` 預設唯讀盤點。`--write-missing` 只建立缺少的專用分頁，既有同名但未標為本系統／內容不同時停止；不覆蓋使用者其他分頁。完成後逐表讀回比較實際值。`--verify` 可單獨複核。切換前需確認正式工作空閒，保留可回復的舊程式與遷移前資料，且停止舊寫入程序。

目前正式遷移讀回：143 版本、281 歷史行情、1269 貨源、1211 反查／檢查紀錄、6836 評分，24 表一致。獨立 Sheet 模式可讀回 2609 比對，初始化約 9.21 秒，PRAGMA database_list 的檔案路徑為空。正式服務切換、重啟及網站清單持久性验收已完成，見下方紀錄。

## 正式切換驗收（2026-09-13）

正式後端已切換。API 回報 `storage.backend=google_sheets`、`persistent_local=false`；檢查主程序 `/proc/<pid>/fd`，沒有開啟 `/opt/music-business/data/` 內檔案。排程仍啟用、10:00 工作已完成、下一輪16:00；10:00 是切換前執行，切換後自然時段尚待觀察。

Chrome 正式頁加入既有 Yahoo TW 商品（6967698／101758319812），Sheet 的 purchase_items 立即出現資料；重啟 music-business 後 API 與重新登入的網頁仍讀回 revision=1、同一選取。已透過畫面移除驗收選取。沒有建立商品報價、刊登、付款或第二套排程。Vercel GQCsgpNKYx2ePhJrDYyfRHdZ9TBN 部署成功。新存儲流程實際反查驗收已完成，見下方批次紀錄。

舊資料庫與舊程式僅暫留作遷移回復備份，不再被正式服務讀寫。不要直接切回舊庫，否則會遺失切換後已寫進 Sheet 的資料；回復前必須匯回新資料並再核對。

自動化調用請讀 `SIMPLES_Data_` 原始分頁：貨源用 platform_candidates，版本用 releases，歷史行情與 Want/Have 用 snapshots，反查結果用 version_searches，採購用 purchase_items，上架用 listing_drafts/published_listings。其他分頁保留抓取進度與審閱紀錄。分頁列數不是唯一可套利商品數。


正式批次 #91（10:30–10:39）已完成，狀態 partial：反查20件、沿用1208件快取、更新20筆行情；貨源刷新26件中25件成功，Tower 3012920 因 title_changed 保留失敗，不硬套原商品。分析 Sheet 同步成功143行。獨立直接讀原始 Sheet：source_checks=1231、snapshots=301、scores=6979、jobs=91，且工作完成明細已存在 Sheet；這些讀回證明新資料不是只存在服務記憶體。沒有新匹配不代表流程失敗；本輪20件均為 unmatched，保留供日後增量比對。
