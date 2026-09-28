# -*- coding: utf-8 -*-
import time
import json
import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from colorama import init, Fore, Style
from tabulate import tabulate
from news_scraper import ForexNewsScraper
from orderflow_analyzer import OrderflowMSNRAnalyzer

init(autoreset=True)

class AllCurrencyAndGoldNewsBot:
    def __init__(self, config_path="config.json", subscribers_path="subscribers.json"):
        self.config_path = config_path
        self.subscribers_path = subscribers_path
        self.config = self.load_config(config_path)
        self.subscribers = self.load_subscribers()
        self.scraper = ForexNewsScraper()
        self.orderflow_analyzer = OrderflowMSNRAnalyzer()
        self.alerted_events = set()
        self.released_events = set()
        self.last_update_id = 0
        self.last_daily_analysis_date = None
        self.last_daily_schedule_date = None
        self.last_holiday_alert_date = None
        
        self.executor = ThreadPoolExecutor(max_workers=50)
        
        threading.Thread(target=self.listen_for_subscribers, daemon=True).start()
        
        if self.config.get("trading", {}).get("enable_breaking_war_news", True):
            threading.Thread(target=self.monitor_breaking_war_news, daemon=True).start()

        if self.config.get("trading", {}).get("enable_daily_orderflow_analysis", True):
            threading.Thread(target=self.monitor_daily_analysis, daemon=True).start()

        if self.config.get("trading", {}).get("enable_daily_news_schedule", True):
            threading.Thread(target=self.monitor_daily_schedule, daemon=True).start()

    def load_config(self, path):
        if not os.path.exists(path):
            return {
                "telegram": {"enabled": True, "bot_token": "", "chat_id": ""},
                "trading": {
                    "target_currencies": ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"],
                    "min_impact": "High",
                    "enable_breaking_war_news": True,
                    "enable_daily_orderflow_analysis": True,
                    "daily_analysis_utc_hour": 21,
                    "daily_analysis_utc_minute": 0,
                    "enable_daily_news_schedule": true,
                    "daily_schedule_utc_hour": 0,
                    "daily_schedule_utc_minute": 0,
                    "pre_news_alert_minutes": [15, 5],
                    "auto_poll_interval_seconds": 25,
                    "news_release_fast_poll_seconds": 4
                }
            }
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_subscribers(self):
        subs = set()
        primary_id = self.config.get("telegram", {}).get("chat_id")
        if primary_id:
            subs.add(str(primary_id))

        if os.path.exists(self.subscribers_path):
            try:
                with open(self.subscribers_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s in data:
                        subs.add(str(s))
            except Exception:
                pass
        return subs

    def save_subscribers(self):
        try:
            with open(self.subscribers_path, "w", encoding="utf-8") as f:
                json.dump(list(self.subscribers), f, indent=2)
        except Exception as e:
            print(f"[!] Error saving subscribers: {e}")

    def listen_for_subscribers(self):
        token = self.config.get("telegram", {}).get("bot_token")
        if not token:
            return

        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={self.last_update_id + 1}&timeout=10&allowed_updates=[\"message\",\"channel_post\",\"my_chat_member\",\"chat_member\"]"
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        message = (
                            update.get("message")
                            or update.get("channel_post")
                            or update.get("edited_channel_post")
                            or update.get("my_chat_member")
                            or update.get("chat_member")
                            or {}
                        )
                        chat = message.get("chat", {})
                        chat_id = str(chat.get("id", ""))
                        text = str(message.get("text", "")).strip().lower()

                        if chat_id and chat_id not in self.subscribers:
                            self.subscribers.add(chat_id)
                            self.save_subscribers()
                            print(Fore.GREEN + f"\n[+] New Subscriber/Channel Connected: ID {chat_id} ({chat.get('title', chat.get('username', 'User'))})")
                            
                            welcome_msg = (
                                "👋 <b>Welcome to GoldFlow Fx News Bot!</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                "🏆 You are now subscribed to receive:\n"
                                "• <b>Live High-Impact News Signals (USD, EUR, GBP, JPY, AUD, CAD)</b>\n"
                                "• <b>Daily & Weekly News Dates & Schedule Reports</b>\n"
                                "• <b>US Bank Holiday & Market Close Time Alerts</b>\n"
                                "• <b>Breaking War & Geopolitical Financial Alerts</b>\n"
                                "• <b>Daily Gold & DXY MSNR/Orderflow Reports</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                "💬 <b>Available Commands:</b>\n"
                                "• /today - Today's High-Impact News & Holiday status\n"
                                "• /holiday - US Bank Holiday & Market Early Close Times\n"
                                "• /week - Full Weekly High-Impact Calendar Schedule\n"
                                "• /gold - Gold & USD High-Impact News Events\n"
                                "• /analysis - Instant Daily MSNR & Orderflow Report"
                            )
                            self.executor.submit(self.send_telegram_to_chat, chat_id, welcome_msg)

                        # Handle Interactive Commands
                        if text in ["/today", "/schedule", "/news", "/today@goldflow_fx_news_bot"]:
                            sched_msg = self.scraper.get_daily_schedule_message()
                            self.executor.submit(self.send_telegram_to_chat, chat_id, sched_msg)
                        elif text in ["/holiday", "/holidays", "/us_holiday", "/holiday@goldflow_fx_news_bot"]:
                            hol_msg = self.scraper.get_us_bank_holiday_message()
                            self.executor.submit(self.send_telegram_to_chat, chat_id, hol_msg)
                        elif text in ["/week", "/calendar", "/week@goldflow_fx_news_bot", "/calendar@goldflow_fx_news_bot"]:
                            week_msg = self.scraper.get_weekly_schedule_message()
                            self.executor.submit(self.send_telegram_to_chat, chat_id, week_msg)
                        elif text in ["/gold", "/xau", "/gold@goldflow_fx_news_bot"]:
                            gold_sched = self.scraper.get_weekly_schedule_message(currencies=["USD"])
                            gold_msg = (
                                "🏆 <b>GOLD (XAUUSD) & USD UPCOMING HIGH-IMPACT DATES:</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n" + gold_sched
                            )
                            self.executor.submit(self.send_telegram_to_chat, chat_id, gold_msg)
                        elif text in ["/analysis", "/msnr"]:
                            self.executor.submit(self.send_telegram_to_chat, chat_id, "⏳ Generating fresh Daily MSNR & Orderflow Report...")
                            self.executor.submit(self.send_daily_analysis)
                        elif text in ["/help", "/start", "/commands"]:
                            help_msg = (
                                "🤖 <b>GoldFlow FX Bot Commands Menu:</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                "📅 /today - <i>Today's High-Impact News & Holiday Status</i>\n"
                                "🏦 /holiday - <i>US Bank Holiday & Market Early Close Times</i>\n"
                                "🗓️ /week - <i>Weekly High-Impact Calendar Schedule</i>\n"
                                "🏆 /gold - <i>Gold & USD High-Impact News Events</i>\n"
                                "📊 /analysis - <i>Generate Live MSNR & Orderflow Report</i>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                "🎯 <i>Automated Live Signal Powered by GoldFlow Fx News Bot</i>"
                            )
                            self.executor.submit(self.send_telegram_to_chat, chat_id, help_msg)
            except Exception:
                pass
            time.sleep(2)

    def monitor_breaking_war_news(self):
        """Monitors real-time High-Impact Breaking War & Geopolitical headlines every 10 minutes (BBC, Al Jazeera, CNN, Reuters)"""
        while True:
            try:
                breaking_items = self.scraper.fetch_breaking_war_and_geopolitics()
                # Limit to top 2 critical alerts per 10-minute cycle to prevent spam
                for item in breaking_items[:2]:
                    source = item.get("source", "GLOBAL WIRE")
                    title = item.get("title", "")
                    gold_imp = item.get("gold_impact", "")
                    mood = item.get("market_mood", "")
                    explanation = item.get("gold_explanation", "")
                    link = item.get("link", "")
                    time_slt = item.get("timestamp", "")

                    print("\n" + Fore.RED + Style.BRIGHT + "=" * 68)
                    print(Fore.RED + Style.BRIGHT + f"⚡ [{source}] BREAKING GEOPOLITICAL / WAR NEWS")
                    print(Fore.WHITE + f"📰 Headline: {title}")
                    print(Fore.YELLOW + f"⏰ Time: {time_slt}")
                    print(Fore.RED + "=" * 68 + "\n")

                    link_text = f'\n🔗 <a href="{link}">Read Full Report on {source}</a>' if link else ""

                    news_msg = (
                        f"🚨 <b>BREAKING GEOPOLITICAL & WAR NEWS [{source}]</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📰 <b>Headline:</b> <b>{title}</b>\n"
                        f"⏰ <b>Time:</b> <code>{time_slt}</code>"
                        f"{link_text}"
                    )
                    self.broadcast(news_msg, color=0xE74C3C)
                    time.sleep(2)

            except Exception:
                pass

            poll_interval = self.config.get("trading", {}).get("breaking_news_poll_interval_seconds", 600)
            time.sleep(poll_interval)

    @staticmethod
    def html_to_discord(html_text):
        if not html_text:
            return ""
        import re
        text = html_text
        text = re.sub(r'<a\s+href="([^"]+)">([^<]+)</a>', r'[\2](\1)', text)
        text = re.sub(r'</?(b|strong)>', '**', text)
        text = re.sub(r'</?(i|em)>', '*', text)
        text = re.sub(r'</?code>', '`', text)
        text = re.sub(r'</?u>', '__', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()

    def send_discord_webhook(self, message, color=None):
        disc_conf = self.config.get("discord", {})
        if not disc_conf.get("enabled", False):
            return
        
        webhook_url = disc_conf.get("webhook_url", "").strip()
        if not webhook_url or not webhook_url.startswith("http"):
            return

        bot_name = disc_conf.get("bot_name", "GoldFlow FX News & Orderflow Bot")
        avatar_url = disc_conf.get("avatar_url", "https://i.imgur.com/4M34hi2.png")

        discord_text = self.html_to_discord(message)
        
        # Determine Embed Color
        if color is None:
            if "STRONG BUY" in message or "BUY" in message or "BULLISH" in message:
                color = 0x2ECC71 # Green
            elif "STRONG SELL" in message or "SELL" in message or "BEARISH" in message or "WAR" in message:
                color = 0xE74C3C # Red
            elif "HOLIDAY" in message or "GOLD" in message:
                color = 0xF1C40F # Gold / Yellow
            else:
                color = 0x3498DB # Blue / Default

        # Discord Embed has 4096 char description limit
        payload = {
            "username": bot_name,
            "avatar_url": avatar_url,
            "embeds": [
                {
                    "author": {
                        "name": bot_name,
                        "icon_url": avatar_url
                    },
                    "description": discord_text[:4000],
                    "color": color,
                    "footer": {
                        "text": "🎯 Developer: Sandun Madusanka (Trader / Fundamental Trader)"
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }

        try:
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            print(Fore.RED + f"[!] Discord Webhook Error: {e}")

    def send_telegram_to_chat(self, chat_id, message):
        token = self.config.get("telegram", {}).get("bot_token")
        if not token:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            requests.post(url, json=payload, timeout=4)
        except Exception:
            pass

    def broadcast(self, message, color=None):
        """Unified broadcast to Discord Webhook and Telegram Subscribers"""
        # 1. Broadcast to Discord
        if self.config.get("discord", {}).get("enabled", False):
            self.executor.submit(self.send_discord_webhook, message, color)

        # 2. Broadcast to Telegram
        tg_conf = self.config.get("telegram", {})
        if tg_conf.get("enabled", False):
            branded_msg = message + "\n━━━━━━━━━━━━━━━━━━━━\n🎯 <i>Developer: Sandun Madusanka (Trader / Fundamental Trader)</i>"
            for cid in list(self.subscribers):
                self.executor.submit(self.send_telegram_to_chat, cid, branded_msg)

    def broadcast_telegram(self, message):
        """Legacy alias redirecting to unified broadcast"""
        self.broadcast(message)

    def send_daily_analysis(self):
        """Generates and sends Sinhala & English Daily Orderflow/MSNR Reports to Discord & Telegram"""
        try:
            sh_rep, en_rep = self.orderflow_analyzer.generate_daily_reports()
            if not sh_rep or not en_rep:
                print(Fore.RED + "[!] Could not generate daily reports (API data missing)")
                return
            
            print(Fore.GREEN + Style.BRIGHT + f"\n[+] Broadcasting Daily MSNR/Orderflow Report to Discord & Telegram...")

            # 1. Send to Discord
            if self.config.get("discord", {}).get("enabled", False):
                self.send_discord_webhook(sh_rep, color=0xF1C40F)
                time.sleep(1.2)
                self.send_discord_webhook(en_rep, color=0x3498DB)

            # 2. Send to Telegram
            if self.config.get("telegram", {}).get("enabled", False):
                goldflow_channel = self.config.get("telegram", {}).get("goldflow_channel_id")
                primary_admin = self.config.get("telegram", {}).get("chat_id")
                
                target_recipients = set()
                if goldflow_channel:
                    target_recipients.add(str(goldflow_channel))
                if primary_admin:
                    target_recipients.add(str(primary_admin))

                for cid in target_recipients:
                    self.send_telegram_to_chat(cid, sh_rep)
                    time.sleep(1.0)
                    self.send_telegram_to_chat(cid, en_rep)
                    time.sleep(1.0)

            print(Fore.GREEN + "[+] Daily Reports successfully delivered!")
        except Exception as e:
            print(Fore.RED + f"[!] Error in send_daily_analysis: {e}")

    def send_us_bank_holiday_alert(self):
        """Generates and broadcasts US Bank Holiday Alert with Market Close Times to Discord & Telegram"""
        try:
            hol_info = self.scraper.check_us_bank_holiday()
            if hol_info.get("is_holiday"):
                hol_msg = self.scraper.get_us_bank_holiday_message()
                print(Fore.YELLOW + Style.BRIGHT + f"\n[+] Broadcasting US Bank Holiday Alert ({hol_info['holiday_name']}) to Discord & Telegram...")
                self.broadcast(hol_msg, color=0xF1C40F)
                print(Fore.GREEN + "[+] US Bank Holiday Alert successfully delivered!")
        except Exception as e:
            print(Fore.RED + f"[!] Error in send_us_bank_holiday_alert: {e}")

    def send_daily_schedule(self):
        """Generates and broadcasts Today's High-Impact News Schedule to Discord & Telegram"""
        try:
            sched_msg = self.scraper.get_daily_schedule_message()
            print(Fore.GREEN + Style.BRIGHT + "\n[+] Broadcasting Today's High-Impact News Schedule to Discord & Telegram...")
            self.broadcast(sched_msg, color=0x3498DB)
            print(Fore.GREEN + "[+] Daily Schedule successfully delivered!")

            # If today is a US Bank Holiday and holiday alerts are enabled, send the dedicated Holiday Schedule Alert
            if self.config.get("trading", {}).get("enable_us_holiday_alerts", True):
                hol_info = self.scraper.check_us_bank_holiday()
                if hol_info.get("is_holiday"):
                    time.sleep(2.0)
                    self.send_us_bank_holiday_alert()
        except Exception as e:
            print(Fore.RED + f"[!] Error in send_daily_schedule: {e}")

    def monitor_daily_schedule(self):
        """Monitors daily schedule broadcast time (default 00:00 UTC / 05:30 SLT) and triggers morning calendar"""
        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                today_str = now_utc.strftime("%Y-%m-%d")
                
                target_h = self.config.get("trading", {}).get("daily_schedule_utc_hour", 0)
                target_m = self.config.get("trading", {}).get("daily_schedule_utc_minute", 0)
                
                if now_utc.hour == target_h and now_utc.minute >= target_m and self.last_daily_schedule_date != today_str:
                    self.last_daily_schedule_date = today_str
                    self.send_daily_schedule()
            except Exception:
                pass
            time.sleep(30)

    def monitor_daily_analysis(self):
        """Monitors daily close time (UTC) and triggers daily analysis report"""
        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                today_str = now_utc.strftime("%Y-%m-%d")
                
                target_h = self.config.get("trading", {}).get("daily_analysis_utc_hour", 21)
                target_m = self.config.get("trading", {}).get("daily_analysis_utc_minute", 0)
                
                # Check if current UTC hour matches and hasn't run today
                if now_utc.hour == target_h and now_utc.minute >= target_m and self.last_daily_analysis_date != today_str:
                    self.last_daily_analysis_date = today_str
                    self.send_daily_analysis()
            except Exception:
                pass
            time.sleep(30)

    def banner(self):
        os.system("cls" if os.name == "nt" else "clear")
        print(Fore.YELLOW + "=" * 68)
        print(Fore.YELLOW + Style.BRIGHT + "   ⚡ LIVE ALL-CURRENCIES & GOLD (WAR/NEWS) TRADING BOT ⚡")
        print(Fore.CYAN + "   [USD, EUR, GBP, JPY, AUD, CAD + XAUUSD Gold War/News Signals]")
        print(Fore.YELLOW + "=" * 68)
        print(Fore.WHITE + f"[*] System Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(Fore.WHITE + f"[*] Monitored Currencies: USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF")
        print(Fore.WHITE + f"[*] War/Breaking News   : " + Fore.GREEN + "ACTIVE (Financial Wire Stream 🟢)")
        print(Fore.WHITE + f"[*] Daily Gold/DXY MSNR : " + Fore.GREEN + "ACTIVE (NY Close Live MSNR/Orderflow 🟢)")
        print(Fore.WHITE + f"[*] Daily News Schedule : " + Fore.GREEN + "ACTIVE (Morning Calendar Dates Broadcast 🟢)")
        print(Fore.WHITE + f"[*] Discord Broadcast   : {'ENABLED 🟢' if self.config.get('discord', {}).get('enabled') and self.config.get('discord', {}).get('webhook_url') else 'DISABLED ⚪'}")
        print(Fore.WHITE + f"[*] Telegram Broadcast  : {'ENABLED 🟢' if self.config.get('telegram', {}).get('enabled') else 'DISABLED ⚪'}")
        print(Fore.YELLOW + "-" * 68 + "\n")

    def run(self):
        self.banner()
        print(Fore.YELLOW + "[*] Monitoring All Currencies & Breaking Geopolitical News for Gold...\n")

        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                min_impact = self.config["trading"].get("min_impact", "High")
                currencies = self.config["trading"].get("target_currencies", ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"])
                
                events = self.scraper.get_upcoming_events(min_impact=min_impact, currencies=currencies)
                
                table_data = []
                fast_poll_needed = False

                for ev in events:
                    ev_time = ev["datetime_utc"]
                    diff = (ev_time - now_utc).total_seconds()
                    mins_diff = diff / 60.0
                    title = ev.get("title", "")
                    country = ev.get("country", "")
                    impact = ev.get("impact", "")
                    forecast = ev.get("forecast", "-")
                    previous = ev.get("previous", "-")
                    actual = ev.get("actual", "")
                    event_id = f"{country}_{title}_{ev_time.isoformat()}"

                    if actual != "":
                        status_str = Fore.GREEN + f"RELEASED ({actual})"
                    elif mins_diff < 0 and mins_diff > -10:
                        status_str = Fore.RED + Style.BRIGHT + "RELEASING NOW ⚡"
                        fast_poll_needed = True
                    elif mins_diff <= 15:
                        status_str = Fore.YELLOW + f"IN {int(mins_diff)} MINS ⚠️"
                        if mins_diff <= 2:
                            fast_poll_needed = True
                    else:
                        hours = int(mins_diff // 60)
                        rem_m = int(mins_diff % 60)
                        status_str = Fore.WHITE + f"in {hours}h {rem_m}m"

                    time_slt_table = ev.get("datetime_slt", ev_time).strftime("%a %I:%M%p SLT")
                    table_data.append([country, impact, title[:26], time_slt_table, forecast, previous, status_str])

                    # 1. Pre-News Warning Alert for Currency / Gold
                    for pre_m in self.config["trading"].get("pre_news_alert_minutes", [15, 5]):
                        pre_key = f"{event_id}_PRE_{pre_m}"
                        if 0 <= mins_diff <= pre_m and (mins_diff > pre_m - 2) and pre_key not in self.alerted_events:
                            self.alerted_events.add(pre_key)
                            date_str = ev.get("datetime_slt", ev_time).strftime("%A, %d %b %Y")
                            time_slt_str = ev.get("datetime_slt", ev_time).strftime("%I:%M %p SLT")
                            time_utc_str = ev_time.strftime("%H:%M UTC")

                            msg = (
                                f"⚠️ <b>UPCOMING HIGH-IMPACT NEWS ({country})</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"📌 <b>Event:</b> {title} ({country})\n"
                                f"🗓️ <b>Date:</b> <b>{date_str}</b>\n"
                                f"⏰ <b>Release Time:</b> <b>{time_slt_str}</b> <i>({time_utc_str})</i> [in {pre_m}m]\n"
                                f"📊 <b>Forecast:</b> <code>{forecast}</code> | <b>Previous:</b> <code>{previous}</code>"
                            )
                            print(Fore.MAGENTA + Style.BRIGHT + f"\n[!] Broadcasted Pre-News Alert for {country} ({pre_m}m before {title})")
                            self.broadcast(msg, color=0xF1C40F)

                    # 2. News Release Instant Result Trigger for Specific Currency
                    if actual != "" and event_id not in self.released_events:
                        self.released_events.add(event_id)
                        analysis = self.scraper.analyze_currency_impact(title, country, actual, forecast, previous)
                        
                        print("\n" + "=" * 68)
                        print(Fore.YELLOW + Style.BRIGHT + f"⚡ {country} ECONOMIC NEWS RELEASED: {title}")
                        print(f"📊 Actual: {actual} | Forecast: {forecast} | Previous: {previous}")
                        print(Fore.CYAN + f"📈 Deviation: {analysis['deviation']}")
                        print("=" * 68 + "\n")

                        # Broadcast Pure Fundamental Result
                        news_result_msg = (
                            f"⚡ <b>ECONOMIC NEWS RELEASE: {title} ({country})</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📊 <b>Actual:</b> <code>{actual}</code>\n"
                            f"🎯 <b>Forecast:</b> <code>{forecast}</code> (Prev: <code>{previous}</code>)\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📈 <b>Deviation:</b> <b>{analysis['deviation']}</b>"
                        )
                        self.broadcast(news_result_msg, color=0x2ECC71 if "Higher" in analysis['deviation'] else (0xE74C3C if "Lower" in analysis['deviation'] else 0x3498DB))

                # Render Table
                self.banner()
                if table_data:
                    headers = ["Currency", "Impact", "News Event", "Time (UTC)", "Forecast", "Previous", "Countdown"]
                    print(tabulate(table_data[:8], headers=headers, tablefmt="fancy_grid"))
                else:
                    print(Fore.GREEN + "[*] All high-impact events for this week have completed.")
                    print(Fore.YELLOW + "[*] Live War / Geopolitical Wire monitoring is active in background 🟢")

                if fast_poll_needed:
                    poll_sec = self.config["trading"].get("news_release_fast_poll_seconds", 4)
                    print(Fore.RED + Style.BRIGHT + f"\n⚡ NEWS WINDOW ACTIVE! Fast Polling every {poll_sec}s for instant result...")
                    time.sleep(poll_sec)
                else:
                    poll_sec = self.config["trading"].get("auto_poll_interval_seconds", 25)
                    print(Fore.WHITE + f"\n[*] Monitoring All Currencies & War News ({len(self.subscribers)} Connected)...")
                    time.sleep(poll_sec)

            except KeyboardInterrupt:
                print(Fore.YELLOW + "\n[!] Bot stopped by user. Goodbye!")
                break
            except Exception as e:
                print(Fore.RED + f"[!] Error in main loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = AllCurrencyAndGoldNewsBot()
    bot.run()
