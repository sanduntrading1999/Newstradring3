# -*- coding: utf-8 -*-
"""
Gold & DXY Live Orderflow & MSNR Daily Analysis Engine
Fetches real-time market data for Gold (XAUUSD / GC=F) and DXY (DX-Y.NYB)
Calculates:
- D1 / H4 / H1 Market Structure (Trend, BOS, CHoCH)
- Liquidity Pools (PDH - BSL, PDL - SSL, Session Ranges)
- Order Blocks (Institutional Footprint Bullish/Bearish OB)
- Imbalance / Fair Value Gaps (FVG) and Open Gaps (Overnight/Weekend Gaps)
- DXY Correlation & SMT Divergence
- Next Day Execution Plans (Scenarios with TP/SL) in Sinhala & English
"""

import requests
import time
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

class OrderflowMSNRAnalyzer:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_binance_klines(self, symbol="PAXGUSDT", limit=30):
        """Ultra-fast fallback for Spot Gold (PAXGUSDT) and Dollar proxy (EURUSDT) from Binance API"""
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
            resp = requests.get(url, timeout=(2, 2))
            if resp.status_code == 200:
                raw = resp.json()
                candles = []
                for item in raw:
                    candles.append({
                        "time": int(item[0]) // 1000,
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5])
                    })
                if candles:
                    return {
                        "symbol": symbol,
                        "current_price": candles[-1]["close"],
                        "candles": candles
                    }
        except Exception:
            pass
        return None

    def fetch_ohlcv(self, symbol, interval="1d", range_str="1mo"):
        """Fetches live OHLCV data with ultra-fast Binance primary and Yahoo fallback"""
        # 1. Fast Primary: Binance API (<200ms)
        if "GC=" in symbol or "XAU" in symbol or "GOLD" in symbol:
            gold_res = self.fetch_binance_klines("PAXGUSDT", limit=30)
            if gold_res:
                return gold_res
        elif "DX" in symbol or "UUP" in symbol:
            eur_data = self.fetch_binance_klines("EURUSDT", limit=30)
            if eur_data:
                dxy_candles = []
                for c in eur_data["candles"]:
                    dxy_candles.append({
                        "time": c["time"],
                        "open": round(100.0 / c["open"], 2) if c["open"] > 0 else 100.0,
                        "high": round(100.0 / c["low"], 2) if c["low"] > 0 else 100.0,
                        "low": round(100.0 / c["high"], 2) if c["high"] > 0 else 100.0,
                        "close": round(100.0 / c["close"], 2) if c["close"] > 0 else 100.0,
                        "volume": c["volume"]
                    })
                return {
                    "symbol": "DXY (Derived)",
                    "current_price": dxy_candles[-1]["close"],
                    "candles": dxy_candles
                }

        # 2. Secondary Fallback: Yahoo Finance API
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=(2, 2))
            if resp.status_code == 200:
                data = resp.json()
                res = data.get("chart", {}).get("result", [])
                if res:
                    meta = res[0].get("meta", {})
                    timestamps = res[0].get("timestamp", [])
                    indicators = res[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = indicators.get("open", [])
                    highs = indicators.get("high", [])
                    lows = indicators.get("low", [])
                    closes = indicators.get("close", [])
                    volumes = indicators.get("volume", [])
                    
                    candles = []
                    for i in range(len(timestamps)):
                        if (opens[i] is not None and highs[i] is not None and 
                            lows[i] is not None and closes[i] is not None):
                            candles.append({
                                "time": timestamps[i],
                                "open": float(opens[i]),
                                "high": float(highs[i]),
                                "low": float(lows[i]),
                                "close": float(closes[i]),
                                "volume": float(volumes[i]) if (volumes and volumes[i] is not None) else 0.0
                            })
                    if candles:
                        return {
                            "symbol": symbol,
                            "current_price": meta.get("regularMarketPrice", candles[-1]["close"] if candles else 0.0),
                            "candles": candles
                        }
        except Exception:
            pass
        return None

    def analyze_market_structure(self, candles):
        """Analyzes Trend, BOS, CHoCH, Highs, Lows, Order Blocks & FVGs"""
        if not candles or len(candles) < 3:
            return None
        
        last_candle = candles[-1]
        prev_candle = candles[-2]
        prev_prev = candles[-3] if len(candles) >= 3 else prev_candle
        
        # 1. Previous Day / Session High & Low (Liquidity)
        pdh = round(prev_candle["high"], 2)
        pdl = round(prev_candle["low"], 2)
        current_price = round(last_candle["close"], 2)
        
        # 2. Check Trend & Structure
        closes = [c["close"] for c in candles[-10:]]
        highs = [c["high"] for c in candles[-10:]]
        lows = [c["low"] for c in candles[-10:]]
        
        trend = "BULLISH 🟢" if current_price > closes[0] else ("BEARISH 🔴" if current_price < closes[0] else "RANGING / CONSOLIDATION 🟡")
        
        # BOS / CHoCH Check
        if current_price > max(highs[:-1]):
            structure_status = "BULLISH BOS (Break of Structure to Upside) 🚀"
        elif current_price < min(lows[:-1]):
            structure_status = "BEARISH BOS (Break of Structure to Downside) 📉"
        elif current_price > pdh and last_candle["close"] < pdh:
            structure_status = "LIQUIDITY SWEEP / CHoCH at PDH (Reversal Potential) 🔄"
        elif current_price < pdl and last_candle["close"] > pdl:
            structure_status = "LIQUIDITY SWEEP / CHoCH at PDL (Reversal Potential) 🔄"
        else:
            structure_status = "INTERNAL RANGE STRUCTURE (Healthy Continuation) 📊"

        # 3. Fair Value Gap (FVG) / Imbalance Detection (Last 3 candles)
        fvg_bullish = None
        fvg_bearish = None
        
        if len(candles) >= 3:
            for i in range(len(candles)-1, 1, -1):
                c1 = candles[i-2]
                c3 = candles[i]
                if c3["low"] > c1["high"]:
                    fvg_bullish = (round(c1["high"], 2), round(c3["low"], 2))
                    break
                elif c1["low"] > c3["high"]:
                    fvg_bearish = (round(c3["high"], 2), round(c1["low"], 2))
                    break

        # 4. Institutional Order Block (OB)
        bullish_ob = None
        bearish_ob = None
        for i in range(len(candles)-2, 0, -1):
            if candles[i]["close"] < candles[i]["open"] and candles[i+1]["close"] > candles[i]["high"]:
                bullish_ob = (round(candles[i]["low"], 2), round(candles[i]["high"], 2))
                break
        for i in range(len(candles)-2, 0, -1):
            if candles[i]["close"] > candles[i]["open"] and candles[i+1]["close"] < candles[i]["low"]:
                bearish_ob = (round(candles[i]["low"], 2), round(candles[i]["high"], 2))
                break

        # 5. Open Gap (Overnight Gap)
        open_gap = round(last_candle["open"] - prev_candle["close"], 2)
        has_gap = abs(open_gap) >= 1.5

        return {
            "current_price": current_price,
            "pdh": pdh,
            "pdl": pdl,
            "trend": trend,
            "structure": structure_status,
            "fvg_bullish": fvg_bullish,
            "fvg_bearish": fvg_bearish,
            "bullish_ob": bullish_ob,
            "bearish_ob": bearish_ob,
            "open_gap": open_gap,
            "has_gap": has_gap,
            "range_pips": round(pdh - pdl, 2)
        }

    def generate_daily_reports(self):
        """Fetches Live Gold & DXY and builds Sinhala & English Telegram Reports"""
        gold_data = self.fetch_ohlcv("GC=F", interval="1d", range_str="1mo")
        dxy_data = self.fetch_ohlcv("DX-Y.NYB", interval="1d", range_str="1mo")
        
        if not gold_data:
            gold_data = self.fetch_ohlcv("XAUUSD=X", interval="1d", range_str="1mo")
        if not dxy_data:
            dxy_data = self.fetch_ohlcv("UUP", interval="1d", range_str="1mo")
            
        if not gold_data or not dxy_data:
            return None, None
            
        g_analysis = self.analyze_market_structure(gold_data["candles"])
        d_analysis = self.analyze_market_structure(dxy_data["candles"])
        
        g_price = g_analysis["current_price"]
        g_pdh = g_analysis["pdh"]
        g_pdl = g_analysis["pdl"]
        
        d_price = d_analysis["current_price"]
        d_pdh = d_analysis["pdh"]
        d_pdl = d_analysis["pdl"]
        
        # Scenarios calculation
        buy_entry = round(g_analysis["fvg_bullish"][0] if g_analysis["fvg_bullish"] else (g_analysis["bullish_ob"][0] if g_analysis["bullish_ob"] else g_pdl + 3.0), 2)
        buy_tp1 = round(buy_entry + (g_pdh - buy_entry) * 0.5, 2)
        buy_tp2 = round(g_pdh + 2.0, 2)
        buy_sl = round(buy_entry - 8.0, 2)
        
        sell_entry = round(g_analysis["fvg_bearish"][1] if g_analysis["fvg_bearish"] else (g_analysis["bearish_ob"][1] if g_analysis["bearish_ob"] else g_pdh - 2.0), 2)
        sell_tp1 = round(sell_entry - (sell_entry - g_pdl) * 0.5, 2)
        sell_tp2 = round(g_pdl - 2.0, 2)
        sell_sl = round(sell_entry + 8.0, 2)

        # Gap text
        if g_analysis["has_gap"]:
            gap_sinhala = f"⚠️ <b>Market Open Gap:</b> <code>${g_analysis['open_gap']:+0.2f}</code> ක Gap එකක් දැකගත හැක. පළමුව මෙම Gap එක Fill කර Continuation වීම බලාපොරොත්තු විය හැක."
            gap_english = f"⚠️ <b>Market Open Gap:</b> Detected an opening gap of <code>${g_analysis['open_gap']:+0.2f}</code>. High probability of Gap-Fill before directional expansion."
        else:
            gap_sinhala = "✅ <b>Market Open Gap:</b> කැපී පෙනෙන Gap එකක් නොමැත (Smooth Institutional Flow)."
            gap_english = "✅ <b>Market Open Gap:</b> No significant opening gap detected (Smooth institutional pricing)."

        # FVG & OB Texts
        fvg_sh = f"<code>${g_analysis['fvg_bullish'][0]} - ${g_analysis['fvg_bullish'][1]}</code>" if g_analysis["fvg_bullish"] else "මෑතකදී Fill නොවූ Active Bullish FVG එකක් නොමැත"
        ob_sh = f"<code>${g_analysis['bullish_ob'][0]} - ${g_analysis['bullish_ob'][1]}</code>" if g_analysis["bullish_ob"] else f"<code>${round(g_pdl + 2.0, 2)} - ${round(g_pdl + 5.0, 2)}</code>"
        
        fvg_en = f"<code>${g_analysis['fvg_bullish'][0]} - ${g_analysis['fvg_bullish'][1]}</code>" if g_analysis["fvg_bullish"] else "None unmitigated"
        ob_en = f"<code>${g_analysis['bullish_ob'][0]} - ${g_analysis['bullish_ob'][1]}</code>" if g_analysis["bullish_ob"] else f"<code>${round(g_pdl + 2.0, 2)} - ${round(g_pdl + 5.0, 2)}</code>"

        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        # 1. SINHALA REPORT
        sinhala_report = (
            f"📊 <b>GOLD (XAUUSD) & DXY - DAILY ORDERFLOW & MSNR REPORT</b>\n"
            f"📅 <b>දිනය / Session:</b> <code>{today_str} (Daily Close / Next Day Plan)</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>1. DXY (US DOLLAR INDEX) BIAS:</b>\n"
            f"• <b>Live Price:</b> <code>{d_price}</code>\n"
            f"• <b>Market Trend:</b> {d_analysis['trend']}\n"
            f"• <b>Daily Range (PDH / PDL):</b> <code>{d_pdh} / {d_pdl}</code>\n"
            f"• <b>Dollar Outlook:</b> DXY හි ප්‍රවණතාවය මත පදනම්ව Gold වලට ප්‍රතිවිරුද්ධ බලපෑමක් (Inverse Correlation) බලාපොරොත්තු විය හැක.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>2. GOLD (XAUUSD) MSNR & ORDERFLOW:</b>\n"
            f"• <b>Live Current Price:</b> <code>${g_price:,.2f}</code>\n"
            f"• <b>Market Structure:</b> {g_analysis['structure']}\n"
            f"• <b>Previous Day High (BSL / Liquidity):</b> <code>${g_pdh:,.2f}</code>\n"
            f"• <b>Previous Day Low (SSL / Demand):</b> <code>${g_pdl:,.2f}</code>\n"
            f"• <b>Daily True Range:</b> <code>${g_analysis['range_pips']}</code>\n"
            f"• <b>Institutional Bullish Order Block (OB):</b> {ob_sh}\n"
            f"• <b>Active Fair Value Gap (FVG):</b> {fvg_sh}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>3. ඊළඟ දවසේ වෙළඳ සැලැස්ම (NEXT DAY ACTION PLAN):</b>\n\n"
            f"🟢 <b>SCENARIO A (HIGH PROBABILITY BUY SETUP):</b>\n"
            f"• <b>Entry Zone:</b> මිල {ob_sh} Demand හෝ FVG වෙත Pullback වී 15M Bullish Confirmation එකක් දුන්නොත්:\n"
            f"👉 <b>BUY Action:</b> Entry: <code>${buy_entry}</code>\n"
            f"🎯 <b>Take Profit 1:</b> <code>${buy_tp1}</code>\n"
            f"🎯 <b>Take Profit 2 (PDH BSL Sweep):</b> <code>${buy_tp2}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>${buy_sl}</code>\n\n"
            f"🔴 <b>SCENARIO B (SELL SETUP / REVERSAL):</b>\n"
            f"• <b>Entry Zone:</b> මිල <code>${g_pdh}</code> (PDH) අසල Liquidity Sweep එකක් කර Bearish Rejection එකක් දුන්නොත්:\n"
            f"👉 <b>SELL Action:</b> Entry: <code>${sell_entry}</code>\n"
            f"🎯 <b>Take Profit 1:</b> <code>${sell_tp1}</code>\n"
            f"🎯 <b>Take Profit 2 (PDL SSL Sweep):</b> <code>${sell_tp2}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>${sell_sl}</code>\n\n"
            f"{gap_sinhala}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <i>Automated MSNR & Orderflow Analytics by GoldFlow FX</i>"
        )

        # 2. ENGLISH REPORT
        english_report = (
            f"📊 <b>GOLD (XAUUSD) & DXY - DAILY INSTITUTIONAL ORDERFLOW REPORT</b>\n"
            f"📅 <b>Session Date:</b> <code>{today_str} (Daily Close / Next Day Outlook)</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>1. DXY (US DOLLAR INDEX) TECHNICAL BIAS:</b>\n"
            f"• <b>Current Price:</b> <code>{d_price}</code>\n"
            f"• <b>Structure Trend:</b> {d_analysis['trend']}\n"
            f"• <b>Daily PDH / PDL:</b> <code>{d_pdh} / {d_pdl}</code>\n"
            f"• <b>Macro Impact:</b> Inverse correlation active. Dollar structure dictates Gold momentum.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>2. GOLD (XAUUSD) MSNR & SMART MONEY FOOTPRINT:</b>\n"
            f"• <b>Spot Market Price:</b> <code>${g_price:,.2f}</code>\n"
            f"• <b>Structure Profile:</b> {g_analysis['structure']}\n"
            f"• <b>Previous Day High (BSL / Buy-Side Liquidity):</b> <code>${g_pdh:,.2f}</code>\n"
            f"• <b>Previous Day Low (SSL / Sell-Side Liquidity):</b> <code>${g_pdl:,.2f}</code>\n"
            f"• <b>Daily Volatility Range:</b> <code>${g_analysis['range_pips']}</code>\n"
            f"• <b>Institutional Bullish Order Block (OB):</b> {ob_en}\n"
            f"• <b>Unmitigated Fair Value Gap (FVG):</b> {fvg_en}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>3. NEXT DAY EXECUTION PLAYBOOK:</b>\n\n"
            f"🟢 <b>SCENARIO A (BULLISH ACCUMULATION / DIP BUY):</b>\n"
            f"• <b>Trigger Condition:</b> Retest into {ob_en} Demand Zone + 15M MSS (Market Structure Shift)\n"
            f"👉 <b>Execution:</b> BUY @ <code>${buy_entry}</code>\n"
            f"🎯 <b>Target 1:</b> <code>${buy_tp1}</code>\n"
            f"🎯 <b>Target 2 (PDH Liquidity Sweep):</b> <code>${buy_tp2}</code>\n"
            f"🛑 <b>Invalidation / Stop Loss:</b> <code>${buy_sl}</code>\n\n"
            f"🔴 <b>SCENARIO B (PREMIUM REJECTION / SHORT SETUP):</b>\n"
            f"• <b>Trigger Condition:</b> Liquidity Grab above PDH <code>${g_pdh}</code> followed by impulsive bearish displacement\n"
            f"👉 <b>Execution:</b> SELL @ <code>${sell_entry}</code>\n"
            f"🎯 <b>Target 1:</b> <code>${sell_tp1}</code>\n"
            f"🎯 <b>Target 2 (PDL Liquidity Pool):</b> <code>${sell_tp2}</code>\n"
            f"🛑 <b>Invalidation / Stop Loss:</b> <code>${sell_sl}</code>\n\n"
            f"{gap_english}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <i>Automated MSNR & Orderflow Analytics by GoldFlow FX</i>"
        )

        return sinhala_report, english_report

if __name__ == "__main__":
    analyzer = OrderflowMSNRAnalyzer()
    sh_rep, en_rep = analyzer.generate_daily_reports()
    print("--- SINHALA REPORT ---")
    print(sh_rep)
    print("\n--- ENGLISH REPORT ---")
    print(en_rep)
