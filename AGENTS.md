# 專案協作約定

使用者指定的唯一同步儲存庫：https://github.com/virus11456/music-business 。

- 每次實作或文件變更（包含 README）都要保留 Git commit 並推送至此儲存庫；沿用目前分支，不強制覆寫遠端歷史。
- 完成功能時更新 README.md、CHANGELOG.md 與相關 docs；區分已實測、僅實作、待完成。
- 推送前查看差異、執行適當驗證並確認没有金鑰／私人資料。排除 .env、secrets、data、logs、虛擬環境與 node_modules。
- 不提交本機 Google 服務帳戶憑證、Discogs token 或使用者資料；不得為同步而弱化 .gitignore。
- Google Sheet 使用資料庫中設定的既有試算表。客服 AI 在資料、比價與上架流程之後進行。
- VPS／Vercel 部署尚未選定；未獲明確指示不部署。
- 若 GitHub 同步受阻，保留本機變更，說明確切阻礙。
