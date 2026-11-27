#!/usr/bin/env python3
"""
崔董專屬台股投資組合 — 免金鑰證交所公開行情（Yahoo Finance 備援）自動更新腳本
盤後抓取當日收盤價，重新計算投組總市值、未實現損益、持股權重與 -10% 硬性停損風控線。
若任一檔持股缺少當日收盤價，則保留原 portfolio.json 資料，不進行覆寫。
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

TZ_TAIPEI = timezone(timedelta(hours=8))

TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_OPENAPI_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
YAHOO_CHART_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

PORTFOLIO_FILE = "portfolio.json"

DEFAULT_HOLDINGS = [
    {
        "symbol": "6139",
        "ticker": "6139.TW",
        "name": "亞翔",
        "sector": "無塵室工程/半導體設備",
        "shares": 75,
        "cost_price": 890.13,
        "current_price": 597.0,
        "cost_amount": 66760,
    },
    {
        "symbol": "2308",
        "ticker": "2308.TW",
        "name": "台達電",
        "sector": "AI電源/散熱/綠能",
        "shares": 50,
        "cost_price": 1593.72,
        "current_price": 1125.0,
        "cost_amount": 79686,
    },
    {
        "symbol": "2330",
        "ticker": "2330.TW",
        "name": "台積電",
        "sector": "晶圓代工龍頭",
        "shares": 15,
        "cost_price": 2401.27,
        "current_price": 2180.0,
        "cost_amount": 36019,
    },
    {
        "symbol": "0050",
        "ticker": "0050.TW",
        "name": "元大台灣50",
        "sector": "市值型ETF",
        "shares": 200,
        "cost_price": 99.84,
        "current_price": 92.4,
        "cost_amount": 19968,
    },
]


def _parse_float(val):
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if not s or s in ("-", "--", "N/A", "null"):
        return None
    if s.startswith("X"):
        s = s[1:]
    try:
        return float(s)
    except ValueError:
        return None


def _http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_twse_mis_quotes(symbols, trade_date_ymd):
    """主要來源 1：證交所 MIS 公開行情（支援盤後即時收盤價與昨收）"""
    results = {}
    if not symbols:
        return results

    for prefix in ("tse", "otc"):
        pending = [s for s in symbols if s not in results]
        if not pending:
            break
        ex_ch = "|".join(f"{prefix}_{s}.tw" for s in pending)
        url = f"{TWSE_MIS_URL}?ex_ch={ex_ch}&json=1&delay=0"
        try:
            data = _http_get_json(url, timeout=15)
            for item in data.get("msgArray", []):
                sym = str(item.get("c", "")).strip()
                if sym not in pending:
                    continue
                if str(item.get("d", "")).strip() != trade_date_ymd:
                    continue
                close_price = _parse_float(item.get("z"))
                if close_price is None or close_price <= 0:
                    continue
                prev_close = _parse_float(item.get("y"))
                change = round(close_price - prev_close, 4) if (prev_close and prev_close > 0) else 0.0
                results[sym] = {
                    "price": close_price,
                    "change": change,
                    "source": f"TWSE MIS ({prefix.upper()})",
                }
        except Exception as e:
            print(f"⚠️ 證交所 MIS ({prefix.upper()}) 查詢失敗: {e}", file=sys.stderr)

    return results


def fetch_twse_openapi_quotes(symbols, trade_date_roc):
    """主要來源 2：證交所 OpenAPI STOCK_DAY_ALL（盤後每日收盤彙整）"""
    results = {}
    if not symbols:
        return results

    target_set = set(symbols)
    try:
        data = _http_get_json(TWSE_OPENAPI_URL, timeout=20)
        if not isinstance(data, list):
            return results
        for row in data:
            sym = str(row.get("Code", "")).strip()
            if sym not in target_set:
                continue
            if str(row.get("Date", "")).strip() != trade_date_roc:
                continue
            close_price = _parse_float(row.get("ClosingPrice"))
            if close_price is None or close_price <= 0:
                continue
            change = _parse_float(row.get("Change"))
            results[sym] = {
                "price": close_price,
                "change": change if change is not None else 0.0,
                "source": "TWSE OpenAPI",
            }
    except Exception as e:
        print(f"⚠️ 證交所 OpenAPI 查詢失敗: {e}", file=sys.stderr)

    return results


def fetch_yahoo_quote(ticker, trade_date_iso):
    """備援來源：Yahoo Finance 行情 API"""
    for host in YAHOO_CHART_HOSTS:
        url = f"{host}/v8/finance/chart/{ticker}?interval=1d&range=5d"
        try:
            data = _http_get_json(url, timeout=15)
            result = (data.get("chart") or {}).get("result") or []
            if not result:
                continue
            item = result[0]
            meta = item.get("meta", {})
            timestamps = item.get("timestamp") or []
            closes = ((item.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []

            today_close = None
            prev_close = None
            for ts, c in zip(timestamps, closes):
                if c is None:
                    continue
                c_val = _parse_float(c)
                if c_val is None or c_val <= 0:
                    continue
                bar_date = datetime.fromtimestamp(ts, tz=TZ_TAIPEI).strftime("%Y-%m-%d")
                if bar_date == trade_date_iso:
                    today_close = c_val
                elif bar_date < trade_date_iso:
                    prev_close = c_val

            if today_close is None:
                rm_time = meta.get("regularMarketTime")
                rm_price = _parse_float(meta.get("regularMarketPrice"))
                if rm_time and rm_price and rm_price > 0:
                    rm_date = datetime.fromtimestamp(rm_time, tz=TZ_TAIPEI).strftime("%Y-%m-%d")
                    if rm_date == trade_date_iso:
                        today_close = rm_price

            if today_close is not None and today_close > 0:
                change = round(today_close - prev_close, 4) if (prev_close and prev_close > 0) else 0.0
                return {
                    "price": today_close,
                    "change": change,
                    "source": "Yahoo Finance",
                }
        except urllib.error.HTTPError as e:
            print(f"⚠️ Yahoo Finance ({host}) 抓取 {ticker} 失敗: HTTP {e.code}", file=sys.stderr)
            if e.code == 429:
                time.sleep(2.0)
        except Exception as e:
            print(f"⚠️ Yahoo Finance ({host}) 抓取 {ticker} 失敗: {e}", file=sys.stderr)

    return None


def update_portfolio():
    now_tw = datetime.now(TZ_TAIPEI)
    today_iso = now_tw.strftime("%Y-%m-%d")
    today_ymd = now_tw.strftime("%Y%m%d")
    today_roc = f"{now_tw.year - 1911}{now_tw.strftime('%m%d')}"

    print(f"[{now_tw.strftime('%Y-%m-%d %H:%M:%S')} TST] 開始執行台股投資組合盤後更新...")

    # 1. 載入既有持股基礎（保留股數與成本）
    holdings = DEFAULT_HOLDINGS
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved.get("holdings"), list) and len(saved["holdings"]) > 0:
                    holdings = saved["holdings"]
                    print(f"已從 {PORTFOLIO_FILE} 載入既有持股基底 ({len(holdings)} 檔)")
        except Exception as e:
            print(f"⚠️ 讀取既有 {PORTFOLIO_FILE} 失敗，改用預設持股: {e}", file=sys.stderr)

    symbols = [h.get("symbol") or h["ticker"].split(".")[0] for h in holdings]

    # 2. 主要來源：免金鑰證交所公開行情 (TWSE MIS -> TWSE OpenAPI)
    quotes = fetch_twse_mis_quotes(symbols, today_ymd)

    missing_after_mis = [s for s in symbols if s not in quotes]
    if missing_after_mis:
        print(f"證交所 MIS 尚缺 {missing_after_mis}，查詢證交所 OpenAPI STOCK_DAY_ALL...")
        openapi_quotes = fetch_twse_openapi_quotes(missing_after_mis, today_roc)
        quotes.update(openapi_quotes)

    # 3. 備援來源：Yahoo Finance
    missing_after_twse = [s for s in symbols if s not in quotes]
    if missing_after_twse:
        print(f"證交所行情尚缺 {missing_after_twse}，切換 Yahoo Finance 備援查詢...")
        for h in holdings:
            sym = h.get("symbol") or h["ticker"].split(".")[0]
            if sym in quotes:
                continue
            ticker = h.get("ticker") or f"{sym}.TW"
            yf_res = fetch_yahoo_quote(ticker, today_iso)
            if yf_res:
                quotes[sym] = yf_res
            time.sleep(0.3)

    # 4. 嚴格檢查：若有任一檔缺少當日收盤價，就保留原資料
    final_missing = [s for s in symbols if s not in quotes]
    if final_missing:
        print(
            f"⚠️ 以下標的缺少 {today_iso} 當日收盤價：{', '.join(final_missing)}。"
            f"依規則保留原 {PORTFOLIO_FILE} 資料，不進行覆寫。"
        )
        return

    # 5. 全數取得當日收盤價，更新現價與當日損益（保留原股數與成本）
    for h in holdings:
        sym = h.get("symbol") or h["ticker"].split(".")[0]
        res = quotes[sym]
        old_p = h["current_price"]
        new_p = res["price"]
        h["current_price"] = new_p
        h["today_pnl"] = round(res["change"] * h["shares"])
        print(
            f"  ✓ {h['name']} ({sym}) [{res['source']}]: "
            f"現價 {old_p} -> {new_p} (漲跌: {res['change']:+.2f})"
        )

    # 6. 重新計算投組損益與風控指標
    total_cost = 0
    total_market_value = 0
    total_today_pnl = 0

    for h in holdings:
        cost = h.get("cost_amount") or round(h["cost_price"] * h["shares"])
        mkt = round(h["current_price"] * h["shares"])
        pnl = mkt - cost
        ret = round(pnl / cost, 4) if cost > 0 else 0.0
        stop_loss_price = round(h["cost_price"] * 0.90, 2)

        h["cost_amount"] = cost
        h["market_value"] = mkt
        h["pnl"] = pnl
        h["return_rate"] = ret
        h["stop_loss_price"] = stop_loss_price

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

    holdings_sorted = sorted(holdings, key=lambda x: x["market_value"], reverse=True)
    cr3 = 0.0
    for h in holdings:
        h["weight"] = round(h["market_value"] / total_market_value, 4) if total_market_value > 0 else 0.0

    for h in holdings_sorted[:3]:
        cr3 += h["weight"]

    win_count = sum(1 for h in holdings if h["pnl"] > 0)
    win_rate = round(win_count / len(holdings), 3) if holdings else 0.0
    unrealized_pnl = total_market_value - total_cost
    return_rate = round(unrealized_pnl / total_cost, 4) if total_cost > 0 else 0.0

    output_data = {
        "as_of_date": today_iso,
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
            "holdings_count": len(holdings),
        },
        "holdings": holdings,
    }

    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("✅ 投組更新完畢，已成功寫入 portfolio.json！")
    print(f"總市值: NT$ {total_market_value:,} | 未實現損益: NT$ {unrealized_pnl:,} ({return_rate*100:.2f}%)")


if __name__ == "__main__":
    update_portfolio()
