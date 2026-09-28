# -*- coding: utf-8 -*-
import time
from news_bot import AllCurrencyAndGoldNewsBot

def send_tests():
    bot = AllCurrencyAndGoldNewsBot()
    print("[*] Starting multi-currency test broadcast to Telegram...")

    test_events = [
        {
            "country": "USD",
            "title": "Non-Farm Employment Change (NFP)",
            "actual": "245K",
            "forecast": "165K",
            "previous": "142K"
        },
        {
            "country": "EUR",
            "title": "ECB Main Refinancing Rate Decision",
            "actual": "3.65%",
            "forecast": "3.65%",
            "previous": "3.75%"
        },
        {
            "country": "GBP",
            "title": "CPI Inflation Rate (YoY)",
            "actual": "3.1%",
            "forecast": "2.2%",
            "previous": "2.0%"
        },
        {
            "country": "JPY",
            "title": "BOJ Monetary Policy Statement & Rate Hike",
            "actual": "0.50%",
            "forecast": "0.25%",
            "previous": "0.25%"
        },
        {
            "country": "AUD",
            "title": "RBA Interest Rate Decision",
            "actual": "4.35%",
            "forecast": "4.10%",
            "previous": "4.10%"
        },
        {
            "country": "CAD",
            "title": "BOC Rate Statement & Employment Change",
            "actual": "45.2K",
            "forecast": "22.5K",
            "previous": "-1.4K"
        },
        {
            "country": "NZD",
            "title": "RBNZ Official Cash Rate",
            "actual": "5.25%",
            "forecast": "5.00%",
            "previous": "5.00%"
        },
        {
            "country": "CHF",
            "title": "SNB Monetary Policy Assessment",
            "actual": "1.00%",
            "forecast": "1.25%",
            "previous": "1.25%"
        }
    ]

    for ev in test_events:
        c = ev["country"]
        t = ev["title"]
        a = ev["actual"]
        f = ev["forecast"]
        p = ev["previous"]

        analysis = bot.scraper.analyze_currency_impact(t, c, a, f, p)

        msg = (
            f"⚡ <b>ECONOMIC NEWS RELEASE: {t} ({c})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Actual:</b> <code>{a}</code>\n"
            f"🎯 <b>Forecast:</b> <code>{f}</code> (Prev: <code>{p}</code>)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Deviation:</b> <b>{analysis['deviation']}</b>"
        )

        print(f"[+] Sending {c} economic news result...")
        bot.broadcast(msg)
        time.sleep(1.0)

    # Send 1 Breaking War News alert as well
    war_headline = "BREAKING: Air Defense Systems Activated in the Middle East Following Military Escalation"
    war_msg = (
        f"🚨 <b>BREAKING GEOPOLITICAL & WAR NEWS [GLOBAL WIRE]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 <b>Headline:</b> <b>{war_headline}</b>\n"
        f"⏰ <b>Time:</b> <code>09:45 PM SLT</code>\n"
        f"🔗 <a href=\"https://news.google.com\">Read Full Wire Report</a>"
    )
    print("[+] Sending Geopolitical / War News test alert...")
    bot.broadcast(war_msg, color=0xE74C3C)
    time.sleep(1.5)

    print("\n[+] Testing US Bank Holiday Alert broadcast with Market Early Close Times...")
    bot.send_us_bank_holiday_alert()
    time.sleep(1.5)

    print("\n[+] Testing Today's High-Impact News Schedule with Dates & Times & Holiday Info...")
    bot.send_daily_schedule()
    time.sleep(1.5)

    print("\n[+] Testing Weekly High-Impact News Calendar Schedule (Date by Date)...")
    weekly_msg = bot.scraper.get_weekly_schedule_message()
    bot.broadcast_telegram(weekly_msg)
    time.sleep(1.5)

    print("\n[+] Testing Pre-News Warning Alert with Date & Time...")
    test_pre_msg = (
        "⚠️ <b>PRE-NEWS WARNING (USD)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Event:</b> Non-Farm Employment Change (NFP) (USD)\n"
        "🗓️ <b>Date:</b> <b>Friday, 11 Sep 2026</b>\n"
        "⏰ <b>Release Time:</b> <b>06:00 PM SLT</b> <i>(12:30 UTC)</i> [in 15m]\n"
        "📊 <b>Forecast:</b> <code>165K</code> | <b>Previous:</b> <code>142K</code>\n"
        "⚡ <b>Action:</b> Prepare for USD & Market Volatility Shock!"
    )
    bot.broadcast_telegram(test_pre_msg)
    time.sleep(1.5)

    print("\n[+] Testing Daily Gold & DXY MSNR/Orderflow Report generation...")
    bot.send_daily_analysis()
    time.sleep(1.0)
    print("[+] All currency, US Holiday Alert, Schedule Calendar & Daily MSNR test broadcasts completed successfully!")

if __name__ == "__main__":
    send_tests()

