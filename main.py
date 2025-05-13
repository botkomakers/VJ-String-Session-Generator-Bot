import os
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN

VIDEO_SITES = ["youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "instagram.com", "vimeo.com"]

def is_video_link(url: str) -> bool:
    return any(domain in url.lower() for domain in VIDEO_SITES)

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

        # Add handler correctly
        self.add_handler(MessageHandler(self.auto_video_downloader, filters.private & filters.text))

    async def stop(self, *args):
        await super().stop()
        print("Bot Stopped. Bye!")

    async def auto_video_downloader(self, client: Client, message: Message):
        url = message.text.strip()
        if not url.startswith("http") or not is_video_link(url):
            return

        status = await message.reply("⏳ Fetching video info...")

        try:
            timestamp = int(time.time())
            os.makedirs("downloads", exist_ok=True)
            output_template = f"downloads/video_{timestamp}.%(ext)s"
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

            await status.edit("⬆️ Uploading video to Telegram...")
            await message.reply_video(
                video=file_path,
                caption=f"✅ Downloaded from {info.get('webpage_url')}"
            )

        except Exception as e:
            print(f"Download Error: {e}")
            await status.edit("❌ Failed to download the video.")
            return

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            await status.delete()

Bot().run()