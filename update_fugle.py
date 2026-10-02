#!/usr/bin/env python3
"""
崔董專屬台股投資組合 — 富果 Fugle Market Data API 自動更新腳本
支援盤後與盤中定時抓取最新成交價，重新計算投組總市值、未實現損益、持股權重與 -10% 硬性停損風控線。
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime

# 富果 API 設定
FUGLE_API_BASE = "https://api.fugle.tw/marketdata/v1.0/stock"
API_KEY = os.environ.get("FUGLE_API_KEY", "").strip()

# 基準持股資料 (若 portfolio.json 存在則自該檔讀取基礎部位)
PORTFOLIO_FILE = "portfolio.json"

DEFAULT_HOLDINGS = [
    {
        "symbol": "6139",
        "ticker": "6139.TW",
        "name": "亞翔",
        "sector": "無塵室工程/半導體設備",
        "shares": 75,
        "cost_price": 890.13,
        "current_price": 759.0,
        "cost_amount": 66760,
    },
    {
        "symbol": "0050",
        "ticker": "0050.TW",
        "name": "元大台灣50",
        "sector": "市值型ETF",
        "shares": 400,
        "cost_price": 107.10,
        "current_price": 112.90,
        "cost_amount": 42840,
    },
    {
        "symbol": "2308",
        "ticker": "2308.TW",
        "name": "台達電",
        "sector": "AI電源/散熱/綠能",
        "shares": 12,
        "cost_price": 1857.67,
        "current_price": 1905.00,
        "cost_amount": 22292,
    },
    {
        "symbol": "6278",
        "ticker": "6278.TW",
        "name": "台表科",
        "sector": "SMT/光電板/PCB",
        "shares": 100,
        "cost_price": 216.12,
        "current_price": 216.50,
        "cost_amount": 21612,
    },
    {
        "symbol": "3455",
        "ticker": "3455.TW",
        "name": "由田",
        "sector": "AOI光學檢測/先進封裝",
        "shares": 60,
        "cost_price": 250.70,
        "current_price": 287.00,
        "cost_amount": 15042,
    },
    {
        "symbol": "2313",
        "ticker": "2313.TW",
        "name": "華通",
        "sector": "低軌衛星/HDI板",
        "shares": 60,
        "cost_price": 250.20,
        "current_price": 224.50,
        "cost_amount": 15012,
    },
    {
        "symbol": "2330",
        "ticker": "2330.TW",
        "name": "台積電",
        "sector": "晶圓代工龍頭",
        "shares": 5,
        "cost_price": 2391.20,
        "current_price": 2510.00,
        "cost_amount": 11956,
    }
]

def fetch_fugle_quote(symbol, api_key):
    """呼叫富果 REST API 取得即時報價"""
    url = f"{FUGLE_API_BASE}/intraday/quote/{symbol}"
    req = urllib.request.Request(url)
    req.add_header("X-API-KEY", api_key)
    req.add_header("User-Agent", "TsuiAgentPortfolio/1.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # 優先取得 closePrice 或 lastPrice 或 previousClose
            close_price = data.get("closePrice") or data.get("lastPrice") or data.get("previousClose")
            change = data.get("change", 0.0)
            change_percent = data.get("changePercent", 0.0)
            return {
                "success": True,
                "price": float(close_price) if close_price else None,
                "change": float(change) if change else 0.0,
                "change_percent": float(change_percent) if change_percent else 0.0,
                "raw": data
            }
    except Exception as e:
        print(f"⚠️ 抓取 {symbol} 失敗: {e}", file=sys.stderr)
        return {"success": False, "error": str(e)}

def update_portfolio():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始執行台股投資組合更新...")

    # 1. 載入既有持股基礎
    holdings = DEFAULT_HOLDINGS
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if "holdings" in saved and len(saved["holdings"]) > 0:
                    holdings = saved["holdings"]
                    print(f"已從 {PORTFOLIO_FILE} 載入既有持股基底 ({len(holdings)} 檔)")
        except Exception as e:
            print(f"讀取既有檔案失敗，採用預設持股: {e}")

    # 2. 若有提供 API Key 則逐檔抓取最新市價
    if not API_KEY:
        print("未檢測到 FUGLE_API_KEY 環境變數，將使用目前現存價格重新試算。")
    else:
        print("檢測到 FUGLE_API_KEY，正在向富果行情 API 查詢最新報價...")
        for h in holdings:
            sym = h.get("symbol") or h["ticker"].split(".")[0]
            res = fetch_fugle_quote(sym, API_KEY)
            if res.get("success") and res.get("price"):
                old_p = h["current_price"]
                new_p = res["price"]
                h["current_price"] = new_p
                # 計算今日損益
                h["today_pnl"] = round((new_p - (new_p - res["change"])) * h["shares"])
                print(f"  ✓ {h['name']} ({sym}): 現價 {old_p} -> {new_p} (漲跌: {res['change']})")
            else:
                print(f"  - {h['name']} ({sym}): 維持原價 {h['current_price']}")
            time.sleep(0.3)  # 遵守 API 限流保護

    # 3. 重新計算投組損益與風控指標
    total_cost = 0
    total_market_value = 0
    total_today_pnl = 0

    for h in holdings:
        cost = round(h["cost_price"] * h["shares"])
        mkt = round(h["current_price"] * h["shares"])
        pnl = mkt - cost
        ret = round(pnl / cost, 4) if cost > 0 else 0.0
        stop_loss_price = round(h["cost_price"] * 0.90, 2)

        h["cost_amount"] = cost
        h["market_value"] = mkt
        h["pnl"] = pnl
        h["return_rate"] = ret
        h["stop_loss_price"] = stop_loss_price

        # 風控狀態判斷 (-10% 硬性停損)
        if ret <= -0.10:
            h["risk_status"] = "danger" if ret <= -0.13 else "warning"
            h["risk_flag"] = f"🚨 跌破 -10% 硬性停損線 ({ret*100:.2f}%)"
        elif ret >= 0.10:
            h["risk_status"] = "strong"
            h["risk_flag"] = f"🔥 強勢獲利表現 (+{ret*100:.2f}%)"
        else:
            h["risk_status"] = "healthy"
            h["risk_flag"] = "持股狀態正常"

        total_cost += cost
        total_market_value += mkt
        total_today_pnl += h.get("today_pnl", 0)

    # 計算權重與 CR3
    holdings_sorted = sorted(holdings, key=lambda x: x["market_value"], reverse=True)
    cr3 = 0.0
    for idx, h in enumerate(holdings):
        h["weight"] = round(h["market_value"] / total_market_value, 4) if total_market_value > 0 else 0.0

    for idx, h in enumerate(holdings_sorted[:3]):
        cr3 += h["weight"]

    win_count = sum(1 for h in holdings if h["pnl"] > 0)
    win_rate = round(win_count / len(holdings), 3) if holdings else 0.0
    unrealized_pnl = total_market_value - total_cost
    return_rate = round(unrealized_pnl / total_cost, 4) if total_cost > 0 else 0.0

    output_data = {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "market": "TW",
        "currency": "TWD",
        "summary": {
            "total_market_value": total_market_value,
            "total_cost": total_cost,
            "unrealized_pnl": unrealized_pnl,
            "return_rate": return_rate,
            "today_pnl": total_today_pnl,
            "win_rate": win_rate,
            "cr3": round(cr3 * 100, 2),
            "holdings_count": len(holdings)
        },
        "holdings": holdings
    }

    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("✅ 投組更新完畢，已成功寫入 portfolio.json！")
    print(f"總市值: NT$ {total_market_value:,} | 未實現損益: NT$ {unrealized_pnl:,} ({return_rate*100:.2f}%)")

if __name__ == "__main__":
    update_portfolio()
