# Discogs 刊登讀回

2026-09-12 已部署 VPS，服務重新啟動並通過 `/api/state` 檢查。真實 `/oauth/identity` 成功，但庫存端點回傳 HTTP 403：`You are currently suspended and not allowed to access this resource.` 此為 Discogs 回覆的帳號限制；需要解除限制後重新驗收，不能將已部署或 fixture 成功當作正式讀回成功。

正式工作 #55 已記錄失敗，未建立庫存快照、未更動 Discogs 刊登。部署前已備份程式及資料庫至 VPS 的 `/opt/music-business-backups/inventory-20260912T035222`。API 欄位契約及真實刊登關聯仍待成功取得資料後驗證。

- `POST /api/inventory/sync`：使用目前 token 的 `/oauth/identity` 確定帳號，再 GET `/users/{username}/inventory`，每次一頁／100 件，上限 100 頁。共用既有節流 client，不寫入 Discogs。
- 中間頁保存於 meta 的 `discogs_inventory_pending`；讀完且筆數一致才更新 `discogs_inventory_snapshot`。重複 ID、頁數變更、空白中間頁、格式錯誤或帳號變更時停止，不覆寫完整快照。
- `POST /api/inventory/reset`：清除暫存分頁進度，保留完整快照與刊登紀錄。沿用工作鎖、認證與 CSRF。
- 前端上架整理增加讀回／接續頁碼與刊登明細。快照顯示原始狀態、更新時間、關聯結果；後端尚未支援時停用按鈕。此功能目前為手動按鈕觸發，尚未加入每日排程。
- 以已登錄 listing ID + release ID，或本系統 `simples-{draft_id}-release-{release_id}` 識別碼關聯。後者須有對應匯出紀錄，且草稿未於該匯出後修改。For Sale 才補登已上架；衝突不覆蓋。只對到專輯名稱／版本不能自動登錄。
- 已售、下架或快照中未出現的刊登，不會刪除本地曾刊登紀錄；主清單的已上架仍表示刊登歷史，當前遠端狀態請看讀回明細。尚未實作跨快照消失項目的原因判定或主清單已售狀態整合。

驗證：5 項庫存回歸案例，連同匯出紀錄共 8 項通過；144 項離線測試通過，15 項 socket 測試未執行。前端型別與建置通過。未改動真實刊登或清除正式資料。
