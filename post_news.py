# -*- coding: utf-8 -*-
"""
GoldFlow FX - Custom News & Analysis Discord Publisher
Allows manually composing, editing, and uploading custom news, geopolitical alerts, 
economic updates, and chart screenshots directly to your Discord channel.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from colorama import init, Fore, Style

init(autoreset=True)

CONFIG_PATH = "config.json"
SLT_TZ = timezone(timedelta(hours=5, minutes=30))

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(Fore.RED + "[!] config.json not found!")
        return None
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def send_to_discord(title, content, category="general", image_path_or_url="", link=""):
    config = load_config()
    if not config:
        return False

    disc_conf = config.get("discord", {})
    webhook_url = disc_conf.get("webhook_url", "").strip()

    if not webhook_url or not webhook_url.startswith("http"):
        print(Fore.RED + "\n[!] Error: Discord Webhook URL is not set in config.json!")
        print(Fore.YELLOW + "    Please add your Discord Webhook URL to config.json first.")
        return False

    bot_name = disc_conf.get("bot_name", "GoldFlow FX News & Orderflow Bot")
    avatar_url = disc_conf.get("avatar_url", "https://i.imgur.com/4M34hi2.png")
    now_slt = datetime.now(timezone.utc).astimezone(SLT_TZ).strftime("%I:%M %p SLT")

    # Category Colors & Headers
    if category == "war":
        header = "🚨 BREAKING GEOPOLITICAL & WAR NEWS"
        color = 0xE74C3C  # Red
    elif category == "fundamental":
        header = "⚡ ECONOMIC & FUNDAMENTAL NEWS"
        color = 0x3498DB  # Blue
    elif category == "gold":
        header = "🏆 GOLD (XAUUSD) MARKET UPDATE"
        color = 0xF1C40F  # Gold
    else:
        header = "📢 MARKET ANNOUNCEMENT / UPDATE"
        color = 0x9B59B6  # Purple

    # Build description
    desc_lines = [
        f"**{header}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📰 **{title}**\n"
    ]
    if content:
        desc_lines.append(f"{content}\n")

    desc_lines.append(f"⏰ **Time:** `{now_slt}`")
    if link:
        desc_lines.append(f"🔗 [Read Full Source / Link]({link})")

    full_description = "\n".join(desc_lines)

    embed = {
        "author": {
            "name": bot_name,
            "icon_url": avatar_url
        },
        "description": full_description[:4000],
        "color": color,
        "footer": {
            "text": "🎯 Developer: Sandun Madusanka (Trader / Fundamental Trader)"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Handle Image Upload (Local File vs URL)
    image_file = None
    files = {}

    if image_path_or_url:
        cleaned_path = image_path_or_url.strip("\"' ")
        if cleaned_path.startswith("http://") or cleaned_path.startswith("https://"):
            # Image URL
            embed["image"] = {"url": cleaned_path}
        elif os.path.exists(cleaned_path):
            # Local Image File
            filename = os.path.basename(cleaned_path)
            try:
                image_file = open(cleaned_path, "rb")
                files = {
                    "file": (filename, image_file, "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "image/png")
                }
                embed["image"] = {"url": f"attachment://{filename}"}
            except Exception as e:
                print(Fore.YELLOW + f"[!] Could not open image file: {e}")
        else:
            print(Fore.YELLOW + f"[!] Image path not found: {cleaned_path} (Skipping image)")

    payload = {
        "username": bot_name,
        "avatar_url": avatar_url,
        "embeds": [embed]
    }

    try:
        if files:
            resp = requests.post(
                webhook_url,
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=10
            )
        else:
            resp = requests.post(webhook_url, json=payload, timeout=8)

        if image_file:
            image_file.close()

        if resp.status_code in [200, 204]:
            print(Fore.GREEN + Style.BRIGHT + "\n[+] Successfully published to Discord Channel! ✅")
            return True
        else:
            print(Fore.RED + f"[!] Discord returned status code {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        if image_file:
            image_file.close()
        print(Fore.RED + f"[!] Failed to send to Discord: {e}")
        return False

def interactive_composer():
    os.system("cls" if os.name == "nt" else "clear")
    print(Fore.YELLOW + "=" * 65)
    print(Fore.YELLOW + Style.BRIGHT + "   ✍️  GOLDFLOW FX - CUSTOM DISCORD NEWS & IMAGE POSTER")
    print(Fore.CYAN + "   [Post Custom News, Analysis & Chart Screenshots to Discord]")
    print(Fore.YELLOW + "=" * 65 + "\n")

    print(Fore.WHITE + "Select News Category:")
    print(Fore.RED + "  1) 🚨 Breaking Geopolitical & War News")
    print(Fore.CYAN + "  2) ⚡ Fundamental / Economic Calendar News")
    print(Fore.YELLOW + "  3) 🏆 Gold (XAUUSD) Analysis / Market Update")
    print(Fore.MAGENTA + "  4) 📢 Custom Announcement / General Update\n")

    cat_choice = input(Fore.GREEN + "Enter choice (1-4) [Default 1]: ").strip()
    category_map = {
        "1": "war",
        "2": "fundamental",
        "3": "gold",
        "4": "general"
    }
    category = category_map.get(cat_choice, "war")

    print("\n" + Fore.YELLOW + "-" * 65)
    title = input(Fore.WHITE + Style.BRIGHT + "📰 Headline / Title (Required): ").strip()
    if not title:
        print(Fore.RED + "[!] Title cannot be empty. Cancelled.")
        return

    print("\n" + Fore.WHITE + "📝 Message Body / Description (Optional - Press Enter to skip):")
    content = input(Fore.CYAN + "👉 ").strip()

    print("\n" + Fore.WHITE + "🖼️  Image / Chart Screenshot (Optional):")
    print(Fore.WHITE + "   (Drag & Drop an image file here, paste file path, or paste an image URL)")
    image_input = input(Fore.CYAN + "👉 Image: ").strip()

    print("\n" + Fore.WHITE + "🔗 Article Link / Source URL (Optional):")
    link = input(Fore.CYAN + "👉 Link: ").strip()

    print("\n" + Fore.YELLOW + "=" * 65)
    print(Fore.GREEN + Style.BRIGHT + "[*] READY TO SEND TO DISCORD:")
    print(Fore.WHITE + f"• Category: {category.upper()}")
    print(Fore.WHITE + f"• Title   : {title}")
    if content:
        print(Fore.WHITE + f"• Content : {content}")
    if image_input:
        print(Fore.WHITE + f"• Image   : {image_input}")
    if link:
        print(Fore.WHITE + f"• Link    : {link}")
    print(Fore.YELLOW + "=" * 65)

    confirm = input(Fore.GREEN + "\nSend this message to Discord channel now? (Y/n): ").strip().lower()
    if confirm in ["", "y", "yes"]:
        print(Fore.YELLOW + "\n[*] Uploading and broadcasting to Discord...")
        send_to_discord(title, content, category, image_input, link)
    else:
        print(Fore.YELLOW + "\n[!] Post cancelled.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode: python post_news.py "Title" "Content" "category" "image_path"
        cmd_title = sys.argv[1]
        cmd_content = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_cat = sys.argv[3] if len(sys.argv) > 3 else "war"
        cmd_img = sys.argv[4] if len(sys.argv) > 4 else ""
        send_to_discord(cmd_title, cmd_content, cmd_cat, cmd_img)
    else:
        interactive_composer()
