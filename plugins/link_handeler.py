import os
import time
import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from yt_dlp import YoutubeDL
from pyrogram.enums import ChatAction

VIDEO_EXTENSIONS = [
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv",
    ".mpeg", ".mpg", ".m4v", ".3gp", ".3g2", ".ts", ".mts",
    ".m2ts", ".vob", ".ogv", ".f4v", ".rm", ".rmvb"
]

async def download_with_progress(session, url, file_path, status_message, message):
    async with session.get(url) as response:
        total = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(file_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(1024):
                f.write(chunk)
                downloaded += len(chunk)
                percent = (downloaded / total) * 100
                try:
                    await status_message.edit(
                        f"⬇️ Downloading: {percent:.2f}% ({downloaded / 1024:.2f} KB / {total / 1024:.2f} KB)"
                    )
                except:
                    pass

@Client.on_message(filters.private & filters.text)
async def link_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        return

    status = await message.reply("⏳ Processing link...")

    # Direct video link
    if any(ext in url for ext in VIDEO_EXTENSIONS):
        try:
            file_name = f"direct_{int(time.time())}.mp4"
            async with aiohttp.ClientSession() as session:
                await download_with_progress(session, url, file_name, status, message)
        except Exception as e:
            print(f"Direct download error: {e}")
            return await status.edit("❌ Failed to download the direct file.")

        try:
            await status.edit("⬆️ Uploading to Telegram...")
            await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
            await message.reply_video(file_name, caption="✅ Here is your downloaded video")
        except Exception as e:
            print(f"Upload error: {e}")
            await message.reply("❌ Failed to upload file.")
        finally:
            if os.path.exists(file_name):
                os.remove(file_name)
            await status.delete()
        return

    # General platforms (YouTube, TikTok, etc.)
    try:
        file_name = f"video_{int(time.time())}.mp4"
        ydl_opts = {
            "outtmpl": file_name,
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
            "merge_output_format": "mp4"
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        await status.edit("⬆️ Uploading downloaded video...")
        await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        await message.reply_video(file_path, caption=f"✅ {info.get('title', 'Video')}")
        os.remove(file_path)

    except Exception as e:
        print(f"yt-dlp error: {e}")
        await status.edit("❌ Failed to download video from this link.")