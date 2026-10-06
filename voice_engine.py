# -*- coding: utf-8 -*-
"""
GoldFlow FX - Discord Live Voice TTS Engine
Converts text into high-quality Natural Human-like AI Voice (English & Sinhala)
Streams live speech into Discord Voice Channels (Trading Rooms).
"""

import os
import time
import asyncio
import tempfile
import edge_tts
from gtts import gTTS
import discord
from colorama import Fore, Style

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

class VoiceEngine:
    VOICE_EN = "en-US-AriaNeural"
    VOICE_SI = "si-LK-SameeraNeural"

    def __init__(self, voice_en=None, voice_si=None):
        if voice_en:
            self.VOICE_EN = voice_en
        if voice_si:
            self.VOICE_SI = voice_si

    async def generate_speech_file(self, text: str, lang: str = "en") -> str:
        """
        Generates an audio file from text using edge-tts with gTTS fallback.
        Returns the absolute path of the generated audio file.
        """
        temp_dir = tempfile.gettempdir()
        file_id = f"goldflow_tts_{int(time.time()*1000)}"
        output_path = os.path.join(temp_dir, f"{file_id}.mp3")

        voice_name = self.VOICE_SI if lang.lower() in ["si", "sinhala"] else self.VOICE_EN

        try:
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return output_path
        except Exception as e:
            print(Fore.YELLOW + f"[!] edge-tts error: {e}. Falling back to gTTS...")

        # Fallback to gTTS
        try:
            gtts_lang = "si" if lang.lower() in ["si", "sinhala"] else "en"
            tts = gTTS(text=text, lang=gtts_lang, slow=False)
            tts.save(output_path)
            return output_path
        except Exception as e:
            print(Fore.RED + f"[!] gTTS fallback error: {e}")
            return None


class DiscordVoiceManager:
    def __init__(self, bot_client, config):
        self.bot = bot_client
        self.config = config
        self.voice_client = None
        self.queue = asyncio.Queue()
        self.worker_task = None
        self.is_running = True
        self.voice_engine = VoiceEngine(
            voice_en=config.get("discord", {}).get("voice_name_en", "en-US-ChristopherNeural"),
            voice_si=config.get("discord", {}).get("voice_name_si", "si-LK-SameeraNeural")
        )

    def start_worker(self):
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._process_queue())

    async def join_channel(self, channel: discord.VoiceChannel):
        """Connects or moves to a Discord Voice Channel"""
        try:
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id != channel.id:
                    await self.voice_client.move_to(channel)
                    print(Fore.GREEN + f"[+] Moved to Voice Channel: {channel.name}")
            else:
                self.voice_client = await channel.connect(timeout=20, reconnect=True)
                print(Fore.GREEN + Style.BRIGHT + f"[+] Connected to Voice Channel: {channel.name} 🎙️🟢")
            self.start_worker()
            return True
        except Exception as e:
            print(Fore.RED + f"[!] Failed to connect to Voice Channel {channel.name}: {e}")
            return False

    async def leave_channel(self):
        """Disconnects from the active Voice Channel"""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                print(Fore.YELLOW + "[*] Disconnected from Voice Channel.")
                return True
        except Exception as e:
            print(Fore.RED + f"[!] Error leaving Voice Channel: {e}")
        return False

    async def queue_speech(self, text_en: str = None, text_si: str = None, lang_pref: str = None):
        """Queues speech announcements in English, Sinhala, or Both"""
        if not self.voice_client or not self.voice_client.is_connected():
            return

        if lang_pref is None:
            lang_pref = self.config.get("discord", {}).get("voice_language", "both").lower()

        items_to_queue = []
        if lang_pref == "en" and text_en:
            items_to_queue.append((text_en, "en"))
        elif lang_pref in ["si", "sinhala"] and text_si:
            items_to_queue.append((text_si, "si"))
        elif lang_pref == "both":
            if text_en:
                items_to_queue.append((text_en, "en"))
            if text_si:
                items_to_queue.append((text_si, "si"))
        else:
            if text_en:
                items_to_queue.append((text_en, "en"))

        for text, lang in items_to_queue:
            await self.queue.put((text, lang))
        self.start_worker()

    async def _process_queue(self):
        """Processes audio items sequentially in the voice channel"""
        while self.is_running:
            try:
                text, lang = await self.queue.get()
                if not self.voice_client or not self.voice_client.is_connected():
                    self.queue.task_done()
                    continue

                audio_file = await self.voice_engine.generate_speech_file(text, lang=lang)
                if audio_file and os.path.exists(audio_file):
                    try:
                        # Wait if something is already playing
                        while self.voice_client and self.voice_client.is_playing():
                            await asyncio.sleep(0.1)

                        if self.voice_client and self.voice_client.is_connected():
                            audio_source = discord.FFmpegPCMAudio(audio_file)
                            self.voice_client.play(audio_source)
                            
                            # Wait until audio finishes playing
                            while self.voice_client and self.voice_client.is_playing():
                                await asyncio.sleep(0.1)

                    except Exception as e:
                        print(Fore.RED + f"[!] Voice playback error: {e}")
                    finally:
                        # Clean up temporary mp3 file
                        try:
                            if os.path.exists(audio_file):
                                os.remove(audio_file)
                        except Exception:
                            pass

                self.queue.task_done()
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(Fore.RED + f"[!] Error in voice worker: {e}")
                await asyncio.sleep(1)
