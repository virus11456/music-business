# Google Sheets 連接設定

這份表的連結已經保存。自動寫入需要獨立帳號授權；公開連結不等於程式有寫入權限。

1. 在 Google Cloud 選擇或建立專案，啟用 Google Sheets API。
2. 在 IAM 與管理 → 服務帳戶，建立用於本工具的服務帳戶。無需為它授予整個專案 Owner 權限。
3. 服務帳戶 → 金鑰 → 新增金鑰 → 建立新金鑰 → JSON，下載到本機。
4. 在指定 Google Sheet 按「共用」，將服務帳戶的電子郵件地址加入為編輯者。
5. 告知我下載檔案的本機路徑即可，不必貼出 JSON 或 private_key。我會完成本機配置並測試同步。

程式設定名稱為 GOOGLE_SERVICE_ACCOUNT_FILE；Google 連接依賴在 requirements-google.txt。憑證只給後端讀取，前端只顯示是否設定。

若組織政策不允許建立金鑰，保留政策並改用 OAuth 授權流程；目前版本尚未實作 OAuth。

參考：[Google 建立服務帳戶](https://docs.cloud.google.com/iam/docs/service-accounts-create)、[Google 建立金鑰](https://docs.cloud.google.com/iam/docs/keys-create-delete)。


## 最新更新：2026-09-10 Google 與 GitHub

Google 服務帳戶已建立並保存於本機排除目錄，Sheets API 已啟用。真實同步及前端 API 同步均成功，回讀確認 141 筆平台商品與 1 筆行情。尚無核對後報價，因此分析公式仍待實際資料驗證。後續固定將程式碼、README、CHANGELOG 與 docs 同步到 https://github.com/virus11456/music-business 。
