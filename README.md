# 📊 tw-stock-portfolio | 台股動態即時監控與持股分析戰略終端

> **崔董（Mark Tsui）專屬台股投資決策與持股動態戰略儀表板**  
> 整合富果 Fugle 富果行情 API、即時損益風控雷達、均線技術指標與高質感終端雙模介面。

---

## 🔗 正式公開線上存取入口 (Live Dashboard)

* **線上儀表板網址**：[https://tsuiagent1.github.io/tw-stock-portfolio/](https://tsuiagent1.github.io/tw-stock-portfolio/)
* **原始碼儲存庫**：[https://github.com/tsuiagent1/tw-stock-portfolio](https://github.com/tsuiagent1/tw-stock-portfolio)
* **部署架構**：GitHub Pages 靜態即時發布 + GitHub Actions 排程自動同步

---

## 🚀 核心功能與戰略模組

1. **持股組合與損益實時監控**
   - 追蹤核心台股持股（台積電 2330、聯發科 2454、鴻海 2317、廣達 2382、元大台灣50 0050 等）。
   - 即時計算投資組合總市值、總損益率、單日漲跌幅與曝險比例。

2. **雙模視覺介面（深色戰略 / 淺色專業）**
   - **Dark Terminal（黑客深色戰略風）**：沉浸式高對比終端黑底，適合夜間與高強度盤中盯盤。
   - **Light Professional（高質感明亮風）**：典雅簡約紙感設計，清晰護眼，適合日間常規決策與報表閱讀。
   - 右上角一鍵切換，狀態持久化儲存於瀏覽器 LocalStorage。

3. **技術指標與風控紀律雷達**
   - 多週期移動平均線（MA5 週線、MA20 月線、MA60 季線）狀態診斷。
   - 停損警示機制（動態監控 -5% / -8% 嚴格停損線），防範下檔風險。
   - 成交量能與乖離率動態監控。

4. **富果 Fugle API 自動化串接**
   - 支援富果行情 API 權杖即時更新最新股價資訊。
   - 搭配 GitHub Actions 於台股交易時段自動抓取盤後行情並更新 `portfolio.json`。

---

## 🛠️ 目錄結構

```text
├── .github/workflows/
│   └── update_portfolio.yml   # 交易日定期抓取 Fugle 盤後數據之自動化流程
├── index.html                 # 終端儀表板前端核心（含深淺雙模與即時互動面板）
├── portfolio.json             # 持股清單、成本均價與最新行情數據庫
├── update_fugle.py            # 富果 Fugle API 盤後資料自動同步 Python 腳本
└── README.md                  # 專案說明與公開入口導航
```

---

## 📈 使用與操作說明

- **即時瀏覽**：直接點擊 [線上儀表板網址](https://tsuiagent1.github.io/tw-stock-portfolio/) 即可載入即時持股戰略面板。
- **主題切換**：點擊儀表板右上角「🌙 深色 / ☀️ 淺色」按鈕即時切換顯示主題。
- **手動同步**：點擊儀表板右上角「🔄 立即同步」可重新整理最新持股數據與市況。
