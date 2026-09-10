# Vercel 前端部署

使用者已於 2026-09-10 授權將前端部署到 Vercel。後端、SQLite、憑證與每天三次的程式排程仍在 Mac；本次不部署後端。

## 部署設定

從 Vercel 匯入 `virus11456/music-business`，Root Directory 選 `frontend`。使用該目錄的 vercel.json：Vite、`pnpm run build:vercel`、輸出 `dist-vercel`、安裝 `pnpm install --frozen-lockfile`。Node.js 請用符合 package.json 的 22.13 以上版本。

原本本機 Vinext / Cloudflare 設定保留；Vercel 使用獨立的 Vite 靜態建置入口，重用相同 React 畫面。部署不需要 Discogs 或 Google 金鑰，也不包含資料庫。

## 目前限制

線上版顯示後端尚未連接，資料操作停用，不會假造資料或嘗試存取訪客電腦的 localhost。Vercel 前端不能直接存取 Mac 的 127.0.0.1。已新增選用的遠端登入與來源限制。需在 VPS 設定管理者存取碼、允許前端網址及公開 API 網址，透過 HTTPS 代理連入；Vercel 的 VITE_API_ORIGIN 設定公開 API 網址後重新部署。詳細步驟見 deploy/README.md。尚未取得 VPS 連線資料，所以目前公開站仍未連接後端。

## 驗證與進度

2026-09-10 已在使用者 Vercel 帳號 virus11456 的專案下完成部署，專案名 music-business。線上網址：https://music-business.vercel.app 。GitHub main 分支、frontend 根目錄、Vite 設定已套用，部署來源 e6e1cbb。Vercel 顯示部署成功，已從瀏覽器開啟正式網址，確認 React 畫面載入、顯示後端尚未連接、更新與新增按鈕停用。未設定後端環境變數，也未上傳任何金鑰。

官方依據：https://vercel.com/docs/frameworks/frontend/vite
