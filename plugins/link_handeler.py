import re
import os
import aiohttp
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message

video_regex = re.compile(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be|facebook\.com|fb\.watch|tiktok\.com|instagram\.com|twitter\.com|vimeo\.com|[^ ]+)', re.IGNORECASE)

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def download_from_link(client, message: Message):
    url_match = video_regex.search(message.text)
    if not url_match:
        return

    url = url_match.group(0)
    status = await message.reply("🔍 Processing your link...")

    try:
        ydl_opts = {
            "outtmpl": "downloads/%(title).70s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
        }

        os.makedirs("downloads", exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        await message.reply_document(file_path, caption="✅ Here’s your downloaded video")
        os.remove(file_path)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Failed: {e}")
