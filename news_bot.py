# -*- coding: utf-8 -*-
import time
import json
import os
import requests
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from colorama import init, Fore, Style
from tabulate import tabulate
import discord
from discord.ext import commands
from discord import app_commands
from news_scraper import ForexNewsScraper
from orderflow_analyzer import OrderflowMSNRAnalyzer
from voice_engine import DiscordVoiceManager

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
        
        # Discord Voice State
        self.voice_manager = None
        self.discord_loop = None
        
        self.executor = ThreadPoolExecutor(max_workers=50)
        
        # Start Discord Interactive Bot if enabled
        if self.config.get("discord", {}).get("enabled", True):
            threading.Thread(target=self.start_discord_bot, daemon=True).start()

        # Start Telegram Subscriber Listener if enabled
        if self.config.get("telegram", {}).get("enabled", False):
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
                "discord": {
                    "enabled": True,
                    "bot_token": "",
                    "webhook_url": "",
                    "voice_enabled": True,
                    "voice_channel_id": "",
                    "auto_join_voice": True,
                    "voice_language": "both",
                    "voice_name_en": "en-US-ChristopherNeural",
                    "voice_name_si": "si-LK-SameeraNeural",
                    "bot_name": "GoldFlow FX News & Orderflow Bot",
                    "avatar_url": "https://cdn.discordapp.com/avatars/1554164087225716882/b9f281dece62a511617dc918c5154d13.png"
                },
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
                "trading": {
                    "target_currencies": ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"],
                    "min_impact": "High",
                    "enable_breaking_war_news": True,
                    "enable_daily_orderflow_analysis": True,
                    "daily_analysis_utc_hour": 21,
                    "daily_analysis_utc_minute": 0,
                    "enable_daily_news_schedule": True,
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

    def announce_voice(self, text_en: str = None, text_si: str = None):
        """Asynchronously queues live Voice TTS speech to the Discord Voice Channel"""
        if not self.config.get("discord", {}).get("voice_enabled", True):
            return
        if self.voice_manager and self.discord_loop and self.discord_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.voice_manager.queue_speech(text_en, text_si),
                self.discord_loop
            )

    def start_discord_bot(self):
        """Starts Discord Client with full Interactive Slash Commands, Prefix Commands, and Live Voice Room TTS"""
        token = self.config.get("discord", {}).get("bot_token", "").strip()
        if not token:
            print(Fore.YELLOW + "[*] Discord bot_token is not set in config.json. Webhook broadcasting active (Add bot_token to enable /commands and Voice Channel TTS).")
            return

        intents = discord.Intents.default()
        try:
            intents.message_content = True
        except Exception:
            pass

        client = commands.Bot(command_prefix=["!", "/"], intents=intents, help_command=None)
        self.voice_manager = DiscordVoiceManager(client, self.config)

        def build_embed(title, html_content, color=0x3498DB):
            clean_desc = self.html_to_discord(html_content)
            bot_name = self.config.get("discord", {}).get("bot_name", "GoldFlow FX News & Orderflow Bot")
            avatar_url = self.config.get("discord", {}).get("avatar_url", "https://cdn.discordapp.com/avatars/1554164087225716882/b9f281dece62a511617dc918c5154d13.png")
            embed = discord.Embed(
                title=title,
                description=clean_desc[:4000],
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=bot_name, icon_url=avatar_url)
            embed.set_footer(text="🎯 Developer: Sandun Madusanka (Trader / Fundamental Trader)")
            return embed

        @client.event
        async def on_ready():
            print(Fore.GREEN + Style.BRIGHT + f"\n[+] Discord Bot Connected as {client.user} (ID: {client.user.id}) 🟢")
            try:
                synced = await client.tree.sync()
                print(Fore.GREEN + f"[+] Synced {len(synced)} Discord Application Slash Commands successfully.")
            except Exception as e:
                print(Fore.YELLOW + f"[!] Discord Slash Sync Notice: {e}")

            # Auto-join configured Discord Voice Channel
            vc_id = self.config.get("discord", {}).get("voice_channel_id")
            if vc_id and self.config.get("discord", {}).get("auto_join_voice", True):
                try:
                    chan = client.get_channel(int(vc_id))
                    if not chan:
                        chan = await client.fetch_channel(int(vc_id))
                    if chan and isinstance(chan, discord.VoiceChannel):
                        await self.voice_manager.join_channel(chan)
                except Exception as e:
                    print(Fore.YELLOW + f"[!] Discord Auto-join voice warning: {e}")

        # --- Slash Commands (/today, /week, /holiday, /gold, /analysis, /join, /leave, /speak, /help) ---
        @client.tree.command(name="today", description="Today's High-Impact News & US Bank Holiday schedule")
        async def slash_today(interaction: discord.Interaction):
            await interaction.response.defer()
            msg = self.scraper.get_daily_schedule_message()
            embed = build_embed("📅 TODAY'S HIGH-IMPACT NEWS SCHEDULE", msg, color=0x3498DB)
            await interaction.followup.send(embed=embed)

        @client.tree.command(name="week", description="Full Weekly High-Impact Calendar Schedule")
        async def slash_week(interaction: discord.Interaction):
            await interaction.response.defer()
            msg = self.scraper.get_weekly_schedule_message()
            embed = build_embed("📅 WEEKLY HIGH-IMPACT NEWS CALENDAR", msg, color=0x3498DB)
            await interaction.followup.send(embed=embed)

        @client.tree.command(name="holiday", description="US Bank Holiday & Market Early Close Times")
        async def slash_holiday(interaction: discord.Interaction):
            await interaction.response.defer()
            msg = self.scraper.get_us_bank_holiday_message()
            embed = build_embed("🏦 US BANK HOLIDAY & MARKET SCHEDULE", msg, color=0xF1C40F)
            await interaction.followup.send(embed=embed)

        @client.tree.command(name="gold", description="Gold (XAUUSD) & USD upcoming high-impact dates")
        async def slash_gold(interaction: discord.Interaction):
            await interaction.response.defer()
            gold_sched = self.scraper.get_weekly_schedule_message(currencies=["USD"])
            embed = build_embed("🏆 GOLD (XAUUSD) & USD UPCOMING DATES", gold_sched, color=0xF1C40F)
            await interaction.followup.send(embed=embed)

        @client.tree.command(name="analysis", description="Generate live Daily MSNR & Orderflow Report")
        async def slash_analysis(interaction: discord.Interaction):
            await interaction.response.defer()
            sh_rep, en_rep = self.orderflow_analyzer.generate_daily_reports()
            if sh_rep and en_rep:
                embed_sh = build_embed("📊 DAILY MSNR / ORDERFLOW REPORT (SINHALA)", sh_rep, color=0xF1C40F)
                embed_en = build_embed("📊 DAILY MSNR / ORDERFLOW REPORT (ENGLISH)", en_rep, color=0x3498DB)
                await interaction.followup.send(embeds=[embed_sh, embed_en])
            else:
                await interaction.followup.send("⚠️ Could not generate daily report at this moment.")

        @client.tree.command(name="join", description="Join your current Discord Voice Channel (Live Voice Trading Room)")
        async def slash_join(interaction: discord.Interaction):
            if interaction.user.voice and interaction.user.voice.channel:
                channel = interaction.user.voice.channel
                await self.voice_manager.join_channel(channel)
                await interaction.response.send_message(f"🎙️ Connected to **{channel.name}**! Live Voice Announcements are now active.")
            else:
                await interaction.response.send_message("⚠️ Please connect to a Voice Channel first before using `/join`.", ephemeral=True)

        @client.tree.command(name="leave", description="Disconnect bot from Discord Voice Channel")
        async def slash_leave(interaction: discord.Interaction):
            await self.voice_manager.leave_channel()
            await interaction.response.send_message("👋 Disconnected from Voice Channel.")

        @client.tree.command(name="speak", description="Speak custom text in the Voice Channel (Test Voice TTS)")
        @app_commands.describe(text="The message to speak", lang="Language: en (English), si (Sinhala), both (Sinhala + English)")
        async def slash_speak(interaction: discord.Interaction, text: str, lang: str = "en"):
            if not self.voice_manager.voice_client or not self.voice_manager.voice_client.is_connected():
                await interaction.response.send_message("⚠️ Bot is not in any Voice Channel. Please join a voice channel and type `/join` first.", ephemeral=True)
                return
            await interaction.response.send_message(f"🗣️ Speaking in `{lang}`: *{text}*")
            await self.voice_manager.queue_speech(text if lang in ['en', 'both'] else None, text if lang in ['si', 'both'] else None, lang_pref=lang)

        @client.tree.command(name="help", description="Show all bot commands and usage guide")
        async def slash_help(interaction: discord.Interaction):
            help_text = (
                "**🤖 GoldFlow FX Discord Bot Commands:**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📅 `/today` or `!today` - *Today's High-Impact News & Holiday Schedule*\n"
                "🗓️ `/week` or `!week` - *Full Weekly High-Impact Calendar Schedule*\n"
                "🏦 `/holiday` or `!holiday` - *US Bank Holiday & Market Early Close Times*\n"
                "🏆 `/gold` or `!gold` - *Gold (XAUUSD) & USD Specific Events*\n"
                "📊 `/analysis` or `!analysis` - *Instant Live MSNR & Orderflow Report*\n"
                "🎙️ `/join` or `!join` - *Connect Bot to your Voice Channel*\n"
                "🔇 `/leave` or `!leave` - *Disconnect Bot from Voice Channel*\n"
                "🗣️ `/speak [text]` - *Speak test message in Voice Channel*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 *Works with both Slash Commands (`/`) and Prefix (`!`)*"
            )
            embed = build_embed("🤖 GOLDFLOW FX BOT COMMANDS", help_text, color=0x2ECC71)
            await interaction.response.send_message(embed=embed)

        # --- Prefix Commands (!today, !week, !holiday, !gold, !analysis, !join, !leave, !speak, !help) ---
        @client.command(name="today", aliases=["schedule", "news"])
        async def cmd_today(ctx):
            msg = self.scraper.get_daily_schedule_message()
            embed = build_embed("📅 TODAY'S HIGH-IMPACT NEWS SCHEDULE", msg, color=0x3498DB)
            await ctx.send(embed=embed)

        @client.command(name="week", aliases=["calendar"])
        async def cmd_week(ctx):
            msg = self.scraper.get_weekly_schedule_message()
            embed = build_embed("📅 WEEKLY HIGH-IMPACT NEWS CALENDAR", msg, color=0x3498DB)
            await ctx.send(embed=embed)

        @client.command(name="holiday", aliases=["holidays", "us_holiday"])
        async def cmd_holiday(ctx):
            msg = self.scraper.get_us_bank_holiday_message()
            embed = build_embed("🏦 US BANK HOLIDAY & MARKET SCHEDULE", msg, color=0xF1C40F)
            await ctx.send(embed=embed)

        @client.command(name="gold", aliases=["xau"])
        async def cmd_gold(ctx):
            gold_sched = self.scraper.get_weekly_schedule_message(currencies=["USD"])
            embed = build_embed("🏆 GOLD (XAUUSD) & USD UPCOMING DATES", gold_sched, color=0xF1C40F)
            await ctx.send(embed=embed)

        @client.command(name="analysis", aliases=["msnr"])
        async def cmd_analysis(ctx):
            status_msg = await ctx.send("⏳ Generating fresh Daily MSNR & Orderflow Report...")
            sh_rep, en_rep = self.orderflow_analyzer.generate_daily_reports()
            if sh_rep and en_rep:
                embed_sh = build_embed("📊 DAILY MSNR / ORDERFLOW REPORT (SINHALA)", sh_rep, color=0xF1C40F)
                embed_en = build_embed("📊 DAILY MSNR / ORDERFLOW REPORT (ENGLISH)", en_rep, color=0x3498DB)
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                await ctx.send(embeds=[embed_sh, embed_en])
            else:
                await status_msg.edit(content="⚠️ Could not generate daily report at this moment.")

        @client.command(name="join")
        async def cmd_join(ctx):
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
                await self.voice_manager.join_channel(channel)
                await ctx.send(f"🎙️ Connected to **{channel.name}**! Live Voice Announcements active.")
            else:
                await ctx.send("⚠️ Please connect to a Voice Channel first before using `!join`.")

        @client.command(name="leave")
        async def cmd_leave(ctx):
            await self.voice_manager.leave_channel()
            await ctx.send("👋 Disconnected from Voice Channel.")

        @client.command(name="speak")
        async def cmd_speak(ctx, *, text: str = ""):
            if not text:
                await ctx.send("⚠️ Usage: `!speak <your text>`")
                return
            if not self.voice_manager.voice_client or not self.voice_manager.voice_client.is_connected():
                await ctx.send("⚠️ Bot is not in a Voice Channel. Type `!join` first.")
                return
            await ctx.send(f"🗣️ Speaking: *{text}*")
            await self.voice_manager.queue_speech(text, text, lang_pref="both")

        @client.command(name="help", aliases=["start", "commands"])
        async def cmd_help(ctx):
            help_text = (
                "**🤖 GoldFlow FX Discord Bot Commands:**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📅 `!today` or `/today` - *Today's High-Impact News & Holiday Schedule*\n"
                "🗓️ `!week` or `/week` - *Full Weekly High-Impact Calendar Schedule*\n"
                "🏦 `!holiday` or `/holiday` - *US Bank Holiday & Market Early Close Times*\n"
                "🏆 `!gold` or `/gold` - *Gold (XAUUSD) & USD Specific Events*\n"
                "📊 `!analysis` or `/analysis` - *Instant Live MSNR & Orderflow Report*\n"
                "🎙️ `!join` or `/join` - *Connect Bot to your Voice Channel*\n"
                "🔇 `!leave` or `/leave` - *Disconnect Bot from Voice Channel*\n"
                "🗣️ `!speak [text]` - *Speak test message in Voice Channel*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💡 *Works with both Slash Commands (`/`) and Prefix (`!`)*"
            )
            embed = build_embed("🤖 GOLDFLOW FX BOT COMMANDS", help_text, color=0x2ECC71)
            await ctx.send(embed=embed)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.discord_loop = loop
        try:
            loop.run_until_complete(client.start(token))
        except Exception as e:
            print(Fore.RED + f"[!] Discord Bot error: {e}")

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

                    # Live Voice Announcement (English Female Voice)
                    voice_en = f"Breaking geopolitical news alert from {source}: {title}"
                    self.announce_voice(voice_en)

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
        avatar_url = disc_conf.get("avatar_url", "https://cdn.discordapp.com/avatars/1554164087225716882/b9f281dece62a511617dc918c5154d13.png")

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
            
            # Voice announcement for daily schedule (English Female Voice)
            voice_en = "Good morning traders! Today's high impact economic news schedule has been published."
            self.announce_voice(voice_en)
            
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
        print(Fore.WHITE + f"[*] Discord Broadcast   : {'ENABLED 🟢' if self.config.get('discord', {}).get('enabled') else 'DISABLED ⚪'}")
        print(Fore.WHITE + f"[*] Discord Bot Commands: {'ONLINE 🟢' if self.config.get('discord', {}).get('bot_token') else 'WEBHOOK ONLY ⚪ (Add bot_token for /commands)'}")
        print(Fore.WHITE + f"[*] Discord Live Voice  : {'ENABLED 🎙️🟢' if self.config.get('discord', {}).get('voice_enabled') else 'DISABLED ⚪'}")
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

                    # 1. Pre-News Warning Alert for Currency / Gold (Text + Voice)
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

                            # Live Discord Voice TTS Announcement (Fundamental News Alert)
                            fc_phrase = f" Forecast is {forecast}." if forecast and forecast != "-" else ""
                            voice_en = f"Attention traders! High impact {country} news: {title}, releasing in {pre_m} minutes.{fc_phrase}"
                            self.announce_voice(voice_en)

                    # 2. News Release Instant Result Trigger for Specific Currency (Text + Voice)
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

                        # Live Discord Voice TTS Announcement (Fundamental Actual Result)
                        clean_dev = analysis['deviation'].replace('🟢', '').replace('🔴', '').replace('⚪', '').strip()
                        voice_en = f"{country} economic news released: {title}. Actual is {actual}, Forecast was {forecast}. Deviation is {clean_dev}."
                        self.announce_voice(voice_en)

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
                    print(Fore.WHITE + f"\n[*] Monitoring All Currencies & War News...")
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
