import os
import time
import asyncio
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from yt_dlp import YoutubeDL

VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.webm', '.mov']

@Client.on_message(filters.private & filters.text)
async def link_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        return

    status = await message.reply("⏳ Processing link...")

    # Direct video link download
    if any(ext in url for ext in VIDEO_EXTENSIONS):
        try:
            file_name = f"file_{int(time.time())}.mp4"
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(file_name, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            print(f"Download error: {e}")
            return await status.edit("❌ Failed to download the direct file.")

        try:
            await status.edit("⬆️ Uploading file to Telegram...")
            await message.reply_document(file_name, caption="✅ Here's your file")
        except Exception as e:
            print(f"Upload error: {e}")
            await message.reply("❌ Failed to upload file.")
        finally:
            if os.path.exists(file_name):
                os.remove(file_name)
            await status.delete()
        return

    # For YouTube, Facebook, TikTok etc.
    try:
        ydl_opts = {
            "outtmpl": f"video_{int(time.time())}.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        await status.edit("⬆️ Uploading downloaded video...")
        await message.reply_video(video=file_path, caption=f"✅ {info.get('title', 'Video')}")
        os.remove(file_path)

    except Exception as e:
        print(f"yt-dlp error: {e}")
        await status.edit("❌ Failed to download video from this link.")