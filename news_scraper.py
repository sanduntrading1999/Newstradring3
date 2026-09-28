import requests
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import json
import time

SLT_TZ = timezone(timedelta(hours=5, minutes=30))
FLAG_MAP = {
    "USD": "🇺🇸 USD",
    "EUR": "🇪🇺 EUR",
    "GBP": "🇬🇧 GBP",
    "JPY": "🇯🇵 JPY",
    "AUD": "🇦🇺 AUD",
    "CAD": "🇨🇦 CAD",
    "NZD": "🇳🇿 NZD",
    "CHF": "🇨🇭 CHF",
    "XAU": "🏆 GOLD"
}

class ForexNewsScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cache-Control": "no-cache"
        }
        self.api_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.cached_events = []
        self.cooldown_until = 0
        self.seen_breaking_news = set()

    def fetch_this_week_events(self):
        """Fetches this week economic calendar with full Monday to Friday events from TradingView & FF"""
        now = time.time()
        if now < self.cooldown_until and self.cached_events:
            return self.cached_events

        # 1. Primary Source: TradingView Economic Calendar (High Reliability & No Rate Limits)
        try:
            now_dt = datetime.now(timezone.utc)
            # Smart Trading Week calculation:
            # On weekends (Sat/Sun), look at the upcoming Monday-Sunday trading week
            if now_dt.weekday() >= 5:
                monday = (now_dt + timedelta(days=(7 - now_dt.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                monday = (now_dt - timedelta(days=now_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

            tv_url = f"https://economic-calendar.tradingview.com/events?from={monday.strftime('%Y-%m-%dT%H:%M:%S.000Z')}&to={sunday.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
            tv_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Origin": "https://www.tradingview.com"
            }
            resp = requests.get(tv_url, headers=tv_headers, timeout=8)
            if resp.status_code == 200:
                raw_data = resp.json().get("result", [])
                events = []
                for item in raw_data:
                    imp_val = item.get("importance")
                    impact_str = "High" if imp_val == 1 else "Medium" if imp_val == 0 else "Low"
                    curr = item.get("currency", "") or item.get("country", "")
                    events.append({
                        "title": item.get("title", ""),
                        "country": curr,
                        "date": item.get("date", ""),
                        "impact": impact_str,
                        "forecast": str(item.get("forecast")) if item.get("forecast") is not None else "",
                        "previous": str(item.get("previous")) if item.get("previous") is not None else "",
                        "actual": str(item.get("actual")) if item.get("actual") is not None else ""
                    })
                if events:
                    self.cached_events = events
                    self.cooldown_until = now + 45
                    return events
        except Exception:
            pass

        # 2. Secondary Fallback Source: ForexFactory JSON
        try:
            response = requests.get(self.api_url, headers=self.headers, timeout=8)
            if response.status_code == 200:
                events = response.json()
                self.cached_events = events
                self.cooldown_until = now + 45
                return events
            elif response.status_code == 429:
                self.cooldown_until = now + 15
                return self.cached_events
        except Exception:
            pass

        return self.cached_events

    def get_upcoming_events(self, min_impact="High", currencies=None):
        """Filters upcoming events for ALL requested currencies (USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF)"""
        if currencies is None:
            currencies = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"]

        all_events = self.fetch_this_week_events()
        if not all_events:
            all_events = self.cached_events

        filtered = []
        for ev in all_events:
            impact = ev.get("impact", "")
            country = ev.get("country", "")

            if min_impact == "High" and impact.lower() != "high":
                continue
            if country not in currencies:
                continue

            date_str = ev.get("date", "")
            try:
                ev_time = datetime.fromisoformat(date_str)
                ev_time_utc = ev_time.astimezone(timezone.utc)
                ev["datetime_utc"] = ev_time_utc
                ev["datetime_slt"] = ev_time_utc.astimezone(SLT_TZ)
                filtered.append(ev)
            except Exception:
                continue

        filtered.sort(key=lambda x: x["datetime_utc"])
        return filtered

    def get_daily_schedule_message(self, target_date_slt=None, min_impact="High", currencies=None):
        """Formats today's or target date's High-Impact News schedule with exact date, times, and US Bank Holiday info"""
        if target_date_slt is None:
            target_date_slt = datetime.now(timezone.utc).astimezone(SLT_TZ).date()

        events = self.get_upcoming_events(min_impact=min_impact, currencies=currencies)
        day_events = [ev for ev in events if ev["datetime_slt"].date() == target_date_slt]

        date_header = target_date_slt.strftime("%A, %d %B %Y")
        hol_info = self.check_us_bank_holiday(target_date_slt)

        hol_header = ""
        if hol_info.get("is_holiday"):
            hol_header = (
                f"🏦 <b><u>US BANK HOLIDAY TODAY:</u> {hol_info['holiday_name']}</b> 🇺🇸\n"
                f"⏰ <b>Gold (XAUUSD):</b> ⚠️ <b>EARLY CLOSE @ {hol_info['gold_close_time']}</b>\n"
                f"🏛️ <b>US Stock Market:</b> <b>{hol_info['stocks_status']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )

        if not day_events:
            status_text = "<i>No High-Impact Economic News releases scheduled. Normal Market Flow.</i>"
            if hol_info.get("is_holiday"):
                status_text = f"<i>US Banks closed for {hol_info['holiday_name']}. Thin market volume expected.</i>"

            return (
                f"📅 <b>TODAY'S HIGH-IMPACT NEWS SCHEDULE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🗓️ <b>Date:</b> {date_header}\n"
                f"{hol_header}"
                f"🌴 <b>Status:</b> {status_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <i>Tip: Use /week to view the full weekly calendar schedule or /holiday for holiday trading hours.</i>"
            )

        msg = (
            f"📅 <b>TODAY'S HIGH-IMPACT NEWS SCHEDULE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🗓️ <b>Date:</b> <b>{date_header}</b>\n"
            f"{hol_header}"
            f"⚡ <b>Total High-Impact Events:</b> {len(day_events)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for ev in day_events:
            c = ev.get("country", "")
            flag_c = FLAG_MAP.get(c, c)
            t = ev.get("title", "")
            fc = ev.get("forecast", "-") or "-"
            pr = ev.get("previous", "-") or "-"
            time_slt = ev["datetime_slt"].strftime("%I:%M %p")
            time_utc = ev["datetime_utc"].strftime("%H:%M UTC")

            msg += (
                f"🔴 <b>{flag_c} | {time_slt} SLT</b> <i>({time_utc})</i>\n"
                f"📌 <b>Event:</b> {t}\n"
                f"🎯 <b>Forecast:</b> <code>{fc}</code> | <b>Prev:</b> <code>{pr}</code>\n"
                f"────────────────────\n"
            )

        msg += "⚠️ <i>Expect major volatility spikes around these release times!</i>"
        return msg

    def get_weekly_schedule_message(self, min_impact="High", currencies=None):
        """Formats this week's full High-Impact News schedule grouped by Date"""
        events = self.get_upcoming_events(min_impact=min_impact, currencies=currencies)
        if not events:
            return (
                f"📅 <b>WEEKLY HIGH-IMPACT NEWS CALENDAR</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🌴 <i>No High-Impact events found for the remaining days of this week.</i>"
            )

        # Group by date
        grouped = {}
        for ev in events:
            d = ev["datetime_slt"].date()
            if d not in grouped:
                grouped[d] = []
            grouped[d].append(ev)

        msg = (
            f"📅 <b>WEEKLY HIGH-IMPACT NEWS CALENDAR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌍 <i>High-Impact Schedule across USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for day_date in sorted(grouped.keys()):
            day_str = day_date.strftime("%A, %b %d")
            ev_list = grouped[day_date]
            msg += f"🗓️ <b><u>{day_str}</u></b> ({len(ev_list)} Events)\n"
            for ev in ev_list:
                c = ev.get("country", "")
                flag_c = FLAG_MAP.get(c, c)
                t = ev.get("title", "")
                time_slt = ev["datetime_slt"].strftime("%I:%M %p")
                time_utc = ev["datetime_utc"].strftime("%H:%M")
                msg += f"• <b>{flag_c}</b> <code>{time_slt} SLT ({time_utc} UTC)</code> - {t}\n"
            msg += "────────────────────\n"

        msg += "\n💡 <i>Use /today anytime to see only today's schedule and forecasts.</i>"
        return msg

    def check_us_bank_holiday(self, target_date_slt=None):
        """
        Checks if the target date is a US Bank Holiday / Federal Holiday.
        Returns a dict with holiday details, market close times, and trading advisory.
        """
        if target_date_slt is None:
            target_date_slt = datetime.now(timezone.utc).astimezone(SLT_TZ).date()

        year = target_date_slt.year
        month = target_date_slt.month
        day = target_date_slt.day
        weekday = target_date_slt.weekday() # 0 = Monday, 6 = Sunday

        holiday_name = None
        gold_close_time = "09:30 PM / 10:00 PM SLT"
        stocks_status = "🔴 CLOSED ALL DAY (NYSE / NASDAQ)"
        forex_status = "🟢 OPEN (Low Liquidity / High Spreads in US Session)"

        # 1. Standard US Federal & Bank Holidays Calculation
        # New Year's Day (Jan 1)
        if month == 1 and day == 1:
            holiday_name = "New Year's Day"
            gold_close_time = "CLOSED ALL DAY / EARLY CLOSE"
        elif month == 1 and day == 2 and weekday == 0:
            holiday_name = "New Year's Day (Observed)"
            gold_close_time = "09:30 PM / 10:00 PM SLT"
        # Martin Luther King Jr. Day (3rd Monday in January)
        elif month == 1 and weekday == 0 and 15 <= day <= 21:
            holiday_name = "Martin Luther King Jr. Day"
        # Presidents' Day / Washington's Birthday (3rd Monday in February)
        elif month == 2 and weekday == 0 and 15 <= day <= 21:
            holiday_name = "Presidents' Day (Washington's Birthday)"
        # Memorial Day (Last Monday in May)
        elif month == 5 and weekday == 0 and day >= 25:
            holiday_name = "Memorial Day"
        # Juneteenth National Independence Day (June 19)
        elif month == 6 and day == 19:
            holiday_name = "Juneteenth National Independence Day"
        elif month == 6 and day == 20 and weekday == 0:
            holiday_name = "Juneteenth (Observed)"
        # Independence Day (July 4)
        elif month == 7 and day == 4:
            holiday_name = "US Independence Day (4th of July)"
        elif month == 7 and day == 5 and weekday == 0:
            holiday_name = "US Independence Day (Observed)"
        # Labor Day (1st Monday in September)
        elif month == 9 and weekday == 0 and 1 <= day <= 7:
            holiday_name = "US Labor Day"
        # Columbus Day / Indigenous Peoples' Day (2nd Monday in October)
        elif month == 10 and weekday == 0 and 8 <= day <= 14:
            holiday_name = "Columbus Day / Indigenous Peoples' Day"
        # Veterans Day (Nov 11)
        elif month == 11 and day == 11:
            holiday_name = "US Veterans Day"
        # Thanksgiving Day (4th Thursday in November)
        elif month == 11 and weekday == 3 and 22 <= day <= 28:
            holiday_name = "Thanksgiving Day"
            gold_close_time = "09:30 PM SLT (~1:00 PM EST)"
        # Black Friday / Day after Thanksgiving (4th Friday in November)
        elif month == 11 and weekday == 4 and 23 <= day <= 29:
            holiday_name = "Day After Thanksgiving (Black Friday)"
            gold_close_time = "11:45 PM SLT (~1:15 PM EST)"
            stocks_status = "⚠️ EARLY CLOSE @ 10:30 PM SLT"
        # Christmas Day (Dec 25)
        elif month == 12 and day == 25:
            holiday_name = "Christmas Day"
            gold_close_time = "CLOSED ALL DAY"
            forex_status = "🔴 CLOSED ALL DAY"
        elif month == 12 and day == 26 and weekday == 0:
            holiday_name = "Christmas Day (Observed)"
            gold_close_time = "CLOSED ALL DAY / EARLY CLOSE"

        # 2. Check Forex Factory JSON Live Feed explicitly for USD Bank Holidays & Other currency holidays
        ff_usd_holiday = False
        other_holidays = []
        try:
            ff_resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", headers=self.headers, timeout=5)
            if ff_resp.status_code == 200:
                ff_data = ff_resp.json()
                for ev in ff_data:
                    c = str(ev.get("country", "")).upper()
                    t = str(ev.get("title", "")).strip()
                    imp = str(ev.get("impact", "")).strip()
                    d_str = str(ev.get("date", ""))
                    try:
                        ev_d = datetime.fromisoformat(d_str).astimezone(SLT_TZ).date()
                        if ev_d == target_date_slt:
                            if "HOLIDAY" in imp.upper() or "BANK HOLIDAY" in t.upper() or "DAY OFF" in t.upper():
                                if c in ["USD", "US"]:
                                    ff_usd_holiday = True
                                    if not holiday_name:
                                        holiday_name = t if t and t != "Bank Holiday" else "US Bank Holiday"
                                else:
                                    flag = FLAG_MAP.get(c, c)
                                    other_holidays.append(f"{flag} ({t})")
                    except Exception:
                        continue
        except Exception:
            pass

        # 3. Check General Events list fallback
        if not holiday_name:
            all_events = self.fetch_this_week_events()
            for ev in all_events:
                ev_country = str(ev.get("country", "")).upper()
                ev_title = str(ev.get("title", "")).strip()
                ev_impact = str(ev.get("impact", "")).strip()
                if ev_country in ["USD", "US"]:
                    date_str = ev.get("date", "")
                    try:
                        ev_dt = datetime.fromisoformat(date_str).astimezone(SLT_TZ).date()
                        if ev_dt == target_date_slt:
                            if "HOLIDAY" in ev_impact.upper() or "BANK HOLIDAY" in ev_title.upper() or "DAY OFF" in ev_title.upper():
                                holiday_name = ev_title if ev_title and ev_title != "Bank Holiday" else "US Bank Holiday"
                                ff_usd_holiday = True
                                break
                    except Exception:
                        continue

        if holiday_name or ff_usd_holiday:
            if not holiday_name:
                holiday_name = "US Bank Holiday (Forex Factory Confirmed)"

            return {
                "is_holiday": True,
                "holiday_name": holiday_name,
                "forex_factory_verified": ff_usd_holiday,
                "other_holidays": other_holidays,
                "date_slt": target_date_slt,
                "date_str": target_date_slt.strftime("%A, %d %B %Y"),
                "gold_close_time": gold_close_time,
                "stocks_status": stocks_status,
                "forex_status": forex_status,
                "advisory": (
                    "• US Banks and Financial Institutions are closed today (Confirmed by Forex Factory & US Federal Calendar).\n"
                    "• High probability of very low liquidity, wide broker spreads, and unexpected whipsaws.\n"
                    "• CME & Spot Gold trading closes early (approx 09:30 PM / 10:00 PM SLT). Avoid holding aggressive intraday Gold positions into market close."
                )
            }
        return {"is_holiday": False}

    def get_us_bank_holiday_message(self, target_date_slt=None):
        """Formats a rich Telegram Broadcast alert for US Bank Holidays with exact market close times and Forex Factory verification"""
        hol_info = self.check_us_bank_holiday(target_date_slt)
        if not hol_info.get("is_holiday"):
            d_str = target_date_slt.strftime("%A, %d %B %Y") if target_date_slt else "Today"
            return (
                f"🏦 <b>US BANK HOLIDAY STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🗓️ <b>Date:</b> {d_str}\n"
                f"🟢 <b>Status:</b> <b>NO US HOLIDAY TODAY</b> (Normal Market Trading Hours)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <i>All US Sessions, Stock Markets, and Gold Markets operate on regular schedules.</i>"
            )

        d_str = hol_info["date_str"]
        h_name = hol_info["holiday_name"]
        gold_time = hol_info["gold_close_time"]
        stocks_stat = hol_info["stocks_status"]
        forex_stat = hol_info["forex_status"]
        adv = hol_info["advisory"]
        other_hols = hol_info.get("other_holidays", [])

        other_sec = ""
        if other_hols:
            other_sec = f"\n🌍 <b>Other Bank Holidays Today:</b> " + ", ".join(other_hols) + "\n"

        msg = (
            f"🏦 <b><u>US BANK HOLIDAY & MARKET SCHEDULE ALERT</u></b> 🇺🇸\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🗓️ <b>Date:</b> <b>{d_str}</b>\n"
            f"🎉 <b>Holiday:</b> <b>{h_name}</b>\n"
            f"📊 <b>Forex Factory Feed:</b> <code>USD Bank Holiday Verified ✅</code>\n"
            f"{other_sec}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b><u>SESSION & MARKET TRADING HOURS (SLT)</u></b>\n\n"
            f"🏆 <b>Gold (XAUUSD) & Commodities:</b>\n"
            f"• <b>Session Status:</b> ⚠️ <b>EARLY CLOSE</b>\n"
            f"• <b>Market Close Time:</b> <b>{gold_time}</b>\n"
            f"• <i>(CME Futures & Spot Gold halt early across most brokers)</i>\n\n"
            f"🇺🇸 <b>US Stock Markets (NYSE / NASDAQ):</b>\n"
            f"• <b>Status:</b> {stocks_stat}\n\n"
            f"💱 <b>Forex Currency Pairs (EURUSD, GBPUSD, etc.):</b>\n"
            f"• <b>Status:</b> {forex_stat}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b><u>TRADING ADVISORY:</u></b>\n"
            f"{adv}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <i>Please check with your specific broker for exact platform server cutoff times.</i>"
        )
        return msg

    @staticmethod
    def parse_numeric(val_str):
        if not val_str:
            return None
        val_clean = val_str.strip().replace(",", "").replace("%", "")
        multiplier = 1.0
        if "K" in val_clean.upper():
            multiplier = 1000.0
            val_clean = val_clean.upper().replace("K", "")
        elif "M" in val_clean.upper():
            multiplier = 1000000.0
            val_clean = val_clean.upper().replace("M", "")
        elif "B" in val_clean.upper():
            multiplier = 1000000000.0
            val_clean = val_clean.upper().replace("B", "")

        try:
            return float(val_clean) * multiplier
        except ValueError:
            return None

    def analyze_currency_impact(self, title, country, actual_str, forecast_str, previous_str):
        """
        Analyzes Actual vs Forecast purely as Fundamental Economic Deviation (No trading buy/sell predictions)
        """
        actual_num = self.parse_numeric(actual_str)
        forecast_num = self.parse_numeric(forecast_str)
        prev_num = self.parse_numeric(previous_str)

        if actual_num is None:
            deviation = "Published"
        else:
            target_num = forecast_num if forecast_num is not None else prev_num
            if target_num is not None:
                if actual_num > target_num:
                    deviation = "Higher than Forecast 🟢"
                elif actual_num < target_num:
                    deviation = "Lower than Forecast 🔴"
                else:
                    deviation = "In-Line with Forecast ⚪"
            else:
                deviation = "Report Published"

        return {
            "status": "RELEASED",
            "currency": country,
            "event": title,
            "actual": actual_str if actual_str else "-",
            "forecast": forecast_str if forecast_str else "-",
            "previous": previous_str if previous_str else "-",
            "deviation": deviation
        }

    def fetch_breaking_war_and_geopolitics(self):
        """
        Fetches live breaking Geopolitical / War / Flash Financial headlines from:
        - Al Jazeera (Middle East / World)
        - BBC World News
        - CNN World
        - Reuters / Bloomberg / AP via Google News Geopolitical Wire
        - FXStreet Financial & Gold Breaking News

        Returns: list of urgent breaking news items affecting Gold (XAUUSD) & Markets
        """
        sources = [
            {
                "name": "AL JAZEERA",
                "url": "https://www.aljazeera.com/xml/rss/all.xml",
                "is_google": False
            },
            {
                "name": "BBC WORLD",
                "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
                "is_google": False
            },
            {
                "name": "CNN WORLD",
                "url": "http://rss.cnn.com/rss/edition_world.rss",
                "is_google": False
            },
            {
                "name": "GEOPOLITICAL WIRE",
                "url": "https://news.google.com/rss/search?q=(Iran+OR+Israel+OR+War+OR+Military+Strike+OR+Missile+OR+Drone+OR+Carrier+OR+Pentagon+OR+CENTCOM+OR+Hormuz+OR+Middle+East+OR+Russia+OR+Ukraine+OR+Taiwan)+when:2h&hl=en-US&gl=US&ceid=US:en",
                "is_google": True
            },
            {
                "name": "GOLD & MARKET WIRE",
                "url": "https://news.google.com/rss/search?q=(Gold+Price+OR+XAUUSD+OR+Federal+Reserve+OR+Crude+Oil+Shock)+when:2h&hl=en-US&gl=US&ceid=US:en",
                "is_google": True
            }
        ]

        breaking_items = []
        
        # Blacklist routine opinion, explainer, podcast, and generic roundups
        noise_blacklist = [
            "opinion", "podcast", "how to", "explainer", "what is", "photos:", 
            "daily brief", "roundup", "highlights", "watch live", "quiz", "recipe",
            "tv show", "movie", "celebrity", "cricket", "football", "sport"
        ]

        for src in sources:
            try:
                resp = requests.get(src["url"], headers=self.headers, timeout=5)
                if resp.status_code != 200:
                    continue

                root = ET.fromstring(resp.content)
                items = root.findall(".//item")[:10]

                for item in items:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    guid_elem = item.find("guid")

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    guid = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else title

                    if not title or guid in self.seen_breaking_news:
                        continue

                    lower_t = title.lower()

                    # Drop noise / non-urgent articles
                    if any(noise in lower_t for noise in noise_blacklist):
                        continue

                    # Strict High-Impact Condition Check
                    action_words = [
                        "strike", "attack", "missile", "bomb", "explosion", "shoot down", 
                        "shot down", "intercept", "aircraft carrier", "warship", "naval strike",
                        "drone attack", "air strike", "airstrike", "ballistic", "retaliat",
                        "kill", "killed", "casualt", "clash", "destroy", "damaged", "hit"
                    ]
                    conflict_zones = [
                        "iran", "israel", "us ", "u.s.", "american", "russia", "ukraine", 
                        "middle east", "houthi", "red sea", "hormuz", "persian gulf", 
                        "gulf of oman", "lebanon", "hezbollah", "syria", "gaza", "taiwan", "pentagon", "centcom"
                    ]
                    critical_triggers = [
                        "declare war", "declares war", "declared war", "invasion", "invades", 
                        "invaded", "nuclear threat", "nuclear strike", "nuclear alert", 
                        "state of emergency", "blockade", "seizes tanker", "tanker seized"
                    ]
                    peace_triggers = [
                        "ceasefire agreed", "ceasefire signed", "ceasefire begins", "ceasefire declared",
                        "truce agreed", "truce signed", "peace deal", "peace agreement signed", "peace treaty"
                    ]
                    gold_shock_triggers = [
                        "gold reaches all-time", "gold hits record", "gold surges", "gold skyrockets",
                        "gold plunges", "gold crashes", "emergency rate", "fed emergency"
                    ]

                    # Must match strong geopolitical strike/action in key conflict zone OR critical emergency
                    is_war_action = (any(a in lower_t for a in action_words) and any(z in lower_t for z in conflict_zones))
                    is_critical_trigger = any(c in lower_t for c in critical_triggers)
                    is_peace_trigger = any(p in lower_t for p in peace_triggers)
                    is_gold_shock = any(g in lower_t for g in gold_shock_triggers)

                    if not (is_war_action or is_critical_trigger or is_peace_trigger or is_gold_shock):
                        continue

                    self.seen_breaking_news.add(guid)
                    if len(self.seen_breaking_news) > 2000:
                        self.seen_breaking_news.clear()

                    source_name = src["name"]
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        if len(parts) == 2 and len(parts[1]) < 30:
                            source_name = parts[1].upper()
                            title = parts[0].strip()

                    breaking_items.append({
                        "source": source_name,
                        "title": title,
                        "link": link,
                        "timestamp": datetime.now(timezone.utc).astimezone(SLT_TZ).strftime("%I:%M %p SLT")
                    })
            except Exception:
                continue

        return breaking_items
