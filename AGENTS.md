# 專案協作約定

使用者指定的唯一同步儲存庫：https://github.com/virus11456/music-business 。

- 每次實作或文件變更（包含 README）都要保留 Git commit 並推送至此儲存庫；沿用目前分支，不強制覆寫遠端歷史。
- 完成功能時更新 README.md、CHANGELOG.md 與相關 docs；區分已實測、僅實作、待完成。
- 推送前查看差異、執行適當驗證並確認没有金鑰／私人資料。排除 .env、secrets、data、logs、虛擬環境與 node_modules。
- 不提交本機 Google 服務帳戶憑證、Discogs token 或使用者資料；不得為同步而弱化 .gitignore。
- Google Sheet 為唯一業務主資料源，沿用 GOOGLE_SPREADSHEET_ID 指向使用者已指定的試算表；不得以本機或 VPS 磁碟庫回退。客服 AI 在資料、比價與上架流程之後進行。
- 已授權部署：Vercel 前端 music-business.vercel.app；Hostinger srv1542946 後端 srv1542946.hstgr.cloud，/opt/music-business，systemd music-business。最新架構以使用者指定 Google Sheet 為唯一業務資料源，VPS 只保留單一執行程序與排程。遷移進度見 docs/SHEET_PRIMARY.md；切換前保留舊庫以防漏資料。Mac 正式後端已停用，不啟動雙重排程。臨時 SSH 公鑰傳輸後移除，不留永久部署金鑰。
- 若 GitHub 同步受阻，保留本機變更，說明確切阻礙。

- 爬蟲與資料收集操作使用 [.agents/skills/record-source-crawlers/SKILL.md](.agents/skills/record-source-crawlers/SKILL.md)；新增或修改平台抓取、分批反查、排程、同步時，必須同步更新對應 skill reference。skill 隨專案版本管理，定時執行仍由程式負責。

- 使用者要求以正式網站操作搭配正式 API／資料庫資料回讀驗收；單元測試與本機建置只能補充，不能冒稱正式流程已驗證。驗收寫入使用已授權真實業務資料，避免將示範商品混入正式庫；明確記錄唯讀、寫入及未實測的範圍。
