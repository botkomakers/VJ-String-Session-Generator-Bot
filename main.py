import os
import time
import yt_dlp
import requests
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN

VIDEO_SITES = ["youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "instagram.com", "vimeo.com"]
VIDEO_EXTS = [".mp4", ".mkv", ".mov", ".webm", ".avi"]

def is_direct_link(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in VIDEO_EXTS)

def is_social_link(url: str) -> bool:
    return any(site in url.lower() for site in VIDEO_SITES)

class Bot(Client):
    def __init__(self):
        super().__init__(
            "vj string session bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=150,
            sleep_threshold=10
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.username = '@' + me.username
        print(f"Bot Started Successfully as {self.username} | Powered By @VJ_Botz")
        self.add_handler(MessageHandler(self.link_handler, filters.private & filters.text))

    async def stop(self, *args):
        await super().stop()
        print("Bot Stopped. Bye!")

    async def link_handler(self, client: Client, message: Message):
        url = message.text.strip()
        if not url.startswith("http"):
            return

        if is_direct_link(url):
            await self.handle_direct_download(message, url)
        elif is_social_link(url):
            await self.handle_social_download(message, url)
        else:
            await message.reply("❌ Unsupported link or not a video.")

    async def handle_direct_download(self, message: Message, url: str):
        status = await message.reply("⏳ Downloading file...")

        file_name = f"downloads/direct_{int(time.time())}.mp4"
        os.makedirs("downloads", exist_ok=True)

        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(file_name, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            print(f"Direct Download Error: {e}")
            return await status.edit("❌ Failed to download the direct video.")

        try:
            await status.edit("⬆️ Uploading file...")
            await message.reply_video(video=file_name, caption="✅ Direct link video uploaded!")
        except Exception as e:
            print(f"Upload Error: {e}")
            await message.reply("❌ Upload failed.")
        finally:
            if os.path.exists(file_name):
                os.remove(file_name)
            await status.delete()

    async def handle_social_download(self, message: Message, url: str):
        status = await message.reply("⏳ Downloading from site...")

        file_path = ""
        try:
            os.makedirs("downloads", exist_ok=True)
            output_template = f"downloads/social_{int(time.time())}.%(ext)s"
            ydl_opts = {
                "outtmpl": output_template,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "quiet": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                if not file_path.endswith(".mp4"):
                    file_path = file_path.rsplit(".", 1)[0] + ".mp4"

            await status.edit("⬆️ Uploading...")
            await message.reply_video(video=file_path, caption=f"✅ Downloaded from {info.get('webpage_url')}")
        except Exception as e:
            print(f"yt_dlp Download Error: {e}")
            await status.edit("❌ Failed to download from the link.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            await status.delete()

Bot().run()