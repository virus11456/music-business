# 進貨平台與 API 狀態（2026-09-10 查核）

不是所有平台都已接通。已實測的首頁搜尋為 Yahoo 台灣、Yahoo 日本、露天、Tower；每個平台每次最多 40 筆。實測代表當次成功，不代表全站完整資料或持續可用。

| 平台 | 本專案現況 | 官方 API 查核 |
|---|---|---|
| Discogs | 官方 API 已接，行情與版本搜尋可用 | 正式上架尚未接通 |
| Google Sheets | 官方 API 已接，讀寫成功 | 分析原生公式已做四種情況測試 |
| Yahoo 台灣 | 解析公開搜尋頁 | 尚未確認可申請的現行全站商品搜尋 API |
| Yahoo 日本拍賣 | 解析公開搜尋頁 | 舊 Auction Web API 已於 2018-02-22 結束；不可拿 Shopping API 當拍賣 API |
| 露天 | 使用網站前端查詢與商品明細介面 | 有官方 Open API 廠商規格與申請金鑰流程；全站其他賣家搜尋的授權範圍待確認 |
| Tower | 解析公開搜尋頁 | 尚未找到公開可申請的商品搜尋 API |
| 日本樂天市場 | 2026-10-31 已接官方 Ichiba 商品搜尋 API（待正式實測） | 有官方 Ichiba Item Search API，最新查核版本 2026-07-01，需自己的 applicationId 與 accessKey |
| eBay | 2026-10-31 已接官方 Browse API（待正式實測） | 有官方 Browse API，支援關鍵字與商品資料查詢，需要開發者應用程式憑證及 application token，正式權限依帳號與 API 規則確認 |
| Mercari | 尚未接通 | 找到 Mercari Shops API，products 限自己的店鋪；不能作為全站個人二手市場搜尋的證據 |
| Disk Union、HMV 中古、Record City | 只有通路連結，未接通 | 公開全站搜尋 API 尚未確認 |

建議優先申請日本樂天與 eBay，兩者官方功能直接對應跨賣家商品搜尋。露天需向平台確認讀取其他賣家商品與全站搜尋範圍，再決定是否取代目前網站介面。未申請、未使用官方文件內示範金鑰，也未採購第三方爬蟲服務。

## 官方來源

- Yahoo 日本終止公告：https://developer.yahoo.co.jp/changelog/2018-02-20-auction160.html
- 露天商品 API 規格：https://www.ruten.com.tw/help/wp-content/uploads/2025/11/RUTEN-OPEN-API-product.pdf
- 日本樂天商品搜尋：https://webservice.rakuten.co.jp/documentation/ichiba-item-search
- eBay Browse：https://developer.ebay.com/develop/api/buy
- Mercari Shops：https://api.mercari-shops.com/docs/index.html

## 尚待完成

自動匯率仍未接通。本次直接讀取台銀頁面未取得可解析的牌告資料，未寫入任何猜測匯率；本機仍可手動設定有來源與日期的匯率。
