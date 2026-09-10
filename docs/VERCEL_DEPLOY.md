# Vercel 前端部署

使用者已於 2026-09-10 授權將前端部署到 Vercel。後端、SQLite、憑證與每天三次的程式排程仍在 Mac；本次不部署後端。

## 部署設定

從 Vercel 匯入 `virus11456/music-business`，Root Directory 選 `frontend`。使用該目錄的 vercel.json：Vite、`pnpm run build:vercel`、輸出 `dist-vercel`、安裝 `pnpm install --frozen-lockfile`。Node.js 請用符合 package.json 的 22.13 以上版本。

原本本機 Vinext / Cloudflare 設定保留；Vercel 使用獨立的 Vite 靜態建置入口，重用相同 React 畫面。部署不需要 Discogs 或 Google 金鑰，也不包含資料庫。

## 目前限制

線上版顯示後端尚未連接，資料操作停用，不會假造資料或嘗試存取訪客電腦的 localhost。Vercel 前端不能直接存取 Mac 的 127.0.0.1。下一步需部署具有 HTTPS、登入驗證與受限制來源設定的後端，再連接前端；現有 local-only server 不可直接裸露到公網。

## 驗證與進度

Vercel 靜態建置與 TypeScript 檢查通過。Vercel 帳號目前未登入，尚未建立雲端專案或取得部署網址。等待使用者登入後完成匯入、建置與網址驗證。

官方依據：https://vercel.com/docs/frameworks/frontend/vite
