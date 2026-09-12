# AI 上架補充文案

程式提供 `POST /api/drafts/suggest-note`，body 為 `{ "draft_id": 1 }`，沿用管理者認證、Origin、CSRF 與工作鎖。只接受已存在且通過目前草稿核對的資料，不儲存或刊登。

後端環境變數（勿放在前端）：

- `OPENAI_API_KEY`：本專案可用的 API 金鑰。
- `OPENAI_LISTING_MODEL`：此帳號可用的文字模型名稱；無預設值，避免默默選擇費用／權限未知模型。

前端在編輯已存草稿時顯示「AI 協助英文文案」。首次草稿須先儲存；AI 讀取的是已儲存內容。前端與後端具備設定後才可按產生。只傳歌手、專輯、格式、品相與原補充內容，不傳成本、貨源連結、客戶資料或憑證。回傳待核對建議，可修改並套用至補充欄位，最後仍需按儲存。現有品相範本保留。

使用 [OpenAI Responses API](https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create)，`store=false`、最多 600 output tokens、20 秒 timeout。拒絕未完成、空白、超過 220 字或格式錯誤輸出；服務失敗不自動重試、不覆寫草稿。提示要求不虛構附件、庫存、品相或運送承諾，但不能保證模型永不出錯，仍須人工核對。

## 驗證與部署界線

- 12 項 AI／草稿相關隔離測試、前端型別與建置通過。
- 未取得並驗證 AI 金鑰／模型，未向 OpenAI 傳送正式商品資料，尚未完成真實 AI 呼叫驗收。
- 後端新增模組與端點尚待部署至 VPS；舊後端不回傳 ai_listing 能力時，前端停用 AI 按鈕。設定存在只代表 configured，不代表外部服務已驗證。
- 本功能只產生補充文案。正式 Discogs 刊登與庫存回讀仍未串接。
