# Vercel 前端部署

## 現況與發布限制（2026-09-14）

以下 Mac 後端與未接通說明是歷史。正式後端已採 VPS／Google Sheet 架構，見 `deploy/README.md` 與 `docs/SHEET_PRIMARY.md`。所有發布先走 `scripts/release_guard.py`；每日全部正式／預覽／前後端合計 20 次，完整額度未知就只留本機提交。

本次 Chrome 核對正式版本仍為 `0edd07f`、部署 `5iG7eC3uhSZHiurxr5ksGALt9zbu`（Ready），尚未包含略過分頁數提示。Git 仍連接 main、Root Directory=frontend、Node=24.x、Ignored Build Step=Automatic、沒有 Deploy Hooks。Skip deployments when unaffected 已勾選，但歷史文件 commit 仍有部署紀錄，不視為完整保護。

新增 `git.deploymentEnabled=false` 僅為本機待同步設定。沒有重試 Vercel build，沒有宣稱 rate-limit 已解除；當日後端部署數及正式 `/api/state` 未能核實前不發布。實際停用自動建置、批次發布及線上驗收仍待完成。

使用者已於 2026-09-10 授權將前端部署到 Vercel。後端、SQLite、憑證與每天三次的程式排程仍在 Mac；本次不部署後端。

## 部署設定

從 Vercel 匯入 `virus11456/music-business`，Root Directory 選 `frontend`。使用該目錄的 vercel.json：Vite、`pnpm run build:vercel`、輸出 `dist-vercel`、安裝 `pnpm install --frozen-lockfile`。Node.js 請用符合 package.json 的 22.13 以上版本。

原本本機 Vinext / Cloudflare 設定保留；Vercel 使用獨立的 Vite 靜態建置入口，重用相同 React 畫面。部署不需要 Discogs 或 Google 金鑰，也不包含資料庫。

## 目前限制

線上版顯示後端尚未連接，資料操作停用，不會假造資料或嘗試存取訪客電腦的 localhost。Vercel 前端不能直接存取 Mac 的 127.0.0.1。已新增選用的遠端登入與來源限制。需在 VPS 設定管理者存取碼、允許前端網址及公開 API 網址，透過 HTTPS 代理連入；Vercel 的 VITE_API_ORIGIN 設定公開 API 網址後重新部署。詳細步驟見 deploy/README.md。尚未取得 VPS 連線資料，所以目前公開站仍未連接後端。

## 驗證與進度

2026-09-10 已在使用者 Vercel 帳號 virus11456 的專案下完成部署，專案名 music-business。線上網址：https://music-business.vercel.app 。GitHub main 分支、frontend 根目錄、Vite 設定已套用，部署來源 e6e1cbb。Vercel 顯示部署成功，已從瀏覽器開啟正式網址，確認 React 畫面載入、顯示後端尚未連接、更新與新增按鈕停用。未設定後端環境變數，也未上傳任何金鑰。

官方依據：https://vercel.com/docs/frameworks/frontend/vite

## 2026-09-11 VPS 接通更新

使用者核准由 Web Console 架設，後端已搬到 Hostinger srv1542946。Vercel 建置預設 API 為 https://srv1542946.hstgr.cloud，可由 VITE_API_ORIGIN 覆蓋；公開設定僅含網址，不含憑證。前端仍使用 https://music-business.vercel.app。先前「後端未串接」段落為歷史紀錄，以本節及最新驗收紀錄為準。
