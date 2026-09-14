# 專案協作約定

## 2026-09-14 純Git同步與連接器流程

已確認Vercel Git連接停用時，純Git同步不觸發部署，不要求Vercel額度或其他專案停止發布；仍須乾淨提交、測試、正式API與自動建置停用證據。release_guard.validate/reserve 的target=sync負責上述檢查。

CLI無登入時允許使用既有GitHub連接器：先讀遠端main，確認是已審查的基準；以受追蹤差異建立tree，必須與本機HEAD tree相同；新commit以剛讀取的遠端main為parent，保留遠端歷史與本機提交。更新分支前再次讀遠端parent及自動部署設定，以reserve(...,target='sync',slots=0)記錄新鮮盤點，通過後僅對virus11456/music-business main做force=false的fast-forward；結果未知先讀回不重送。建立未連到分支的Git objects不觸發部署。不能借此進行Vercel發布，發布仍須另計額度。此明確流程優先於舊文件僅允許Git CLI的描述。

## 2026-09-14 22:26 最新發布規則與後端部署

每日 20 次只計 SIMPLES 在 Vercel 的正式與預覽部署；Vercel 帳號每日 100 次另行盤點。VPS 後端不受此額度限制，也不消耗 Vercel 次數。這段使用者最新要求取代下方所有「前後端合計20次」舊規則；不能因後端歷史部署次數未知阻擋後端維護。

守門的 frontend／preview 使用 scope=simples_vercel，統計 Vercel；backend 預留0次，只核對提交、測試與正式 API 閒置／下次排程，不要求 Vercel 次數。前端保留集中發布及防誤觸 Git 建置流程。舊 audit 必須重新盤點，不能沿用包含後端的基準。

後端 source_queue.py 已於台灣22:26部署，SHA256=7e4510455e8699d3b2d4ea0e147e2e406b85c1e30614cad75765f8d0a0e14523；備份 backups/queue-time-20260914T142625Z。修正重查時間比較並增加 pending；前端尚未部署。22:00自然工作#101成功，抓取153筆平台結果、反查20件（0候選／20未匹配）、更新20筆行情、刷新28/28貨源、Sheet寫3略過2且5頁讀回通過。部署後獨立Sheet稽核：24表、1528貨源、269版本、567行情快照；2736比較結構／格式／品番／條碼／算式全部通過。923個正毛利需求候選組合不是獨立商品或壓片確認。

集中發布排程時段仍為12:15與21:15；此次更新自動化遭自動審核拒絕，未生效。不可聲稱排程已採用新規則；需另確認持續自動部署授權。VPS資料排程10/16/22不受影響。


使用者指定的唯一同步儲存庫：https://github.com/virus11456/music-business 。

- 每次實作或文件變更（包含 README）都要保留 Git commit 並推送至此儲存庫；沿用目前分支，不強制覆寫遠端歷史。
- 2026-09-14 最新發布規則優先於上一條：每天 Asia/Taipei 全部正式、預覽、前端、後端部署合計最多 20 次。先累積本機提交與測試；未能完整盤點當日次數時禁止推送／部署，文件提交也不例外。依 deploy/README.md 使用發布守門，不能直接設定 SIMPLES_RELEASE_GUARDED 或使用 --no-verify 繞過。
- 本機守門不是帳號全域限流。發布前核對所有相關發布者、Vercel 全環境與 VPS 紀錄，确认獨占發布時段；無法協調或盤點則停止。禁止付費升級、改用其他專案規避額度。
- 完成功能時更新 README.md、CHANGELOG.md 與相關 docs；區分已實測、僅實作、待完成。
- 推送前查看差異、執行適當驗證並確認没有金鑰／私人資料。排除 .env、secrets、data、logs、虛擬環境與 node_modules。
- 不提交本機 Google 服務帳戶憑證、Discogs token 或使用者資料；不得為同步而弱化 .gitignore。
- Google Sheet 為唯一業務主資料源，沿用 GOOGLE_SPREADSHEET_ID 指向使用者已指定的試算表；不得以本機或 VPS 磁碟庫回退。客服 AI 在資料、比價與上架流程之後進行。
- 已授權部署：Vercel 前端 music-business.vercel.app；Hostinger srv1542946 後端 srv1542946.hstgr.cloud，/opt/music-business，systemd music-business。最新架構以使用者指定 Google Sheet 為唯一業務資料源，VPS 只保留單一執行程序與排程。遷移進度見 docs/SHEET_PRIMARY.md；切換前保留舊庫以防漏資料。Mac 正式後端已停用，不啟動雙重排程。臨時 SSH 公鑰傳輸後移除，不留永久部署金鑰。
- 若 GitHub 同步受阻，保留本機變更，說明確切阻礙。

- 爬蟲與資料收集操作使用 [.agents/skills/record-source-crawlers/SKILL.md](.agents/skills/record-source-crawlers/SKILL.md)；新增或修改平台抓取、分批反查、排程、同步時，必須同步更新對應 skill reference。skill 隨專案版本管理，定時執行仍由程式負責。

- 使用者要求以正式網站操作搭配正式 API／資料庫資料回讀驗收；單元測試與本機建置只能補充，不能冒稱正式流程已驗證。驗收寫入使用已授權真實業務資料，避免將示範商品混入正式庫；明確記錄唯讀、寫入及未實測的範圍。
