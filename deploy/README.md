# VPS 部署

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
