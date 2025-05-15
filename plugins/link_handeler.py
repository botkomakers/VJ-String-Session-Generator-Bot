import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import threading
import hashlib
import mimetypes
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, OWNER_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
MAX_SIZE = 1.9 * 1024 * 1024 * 1024  # 1.9 GB

active_tasks = set()
cache_dir = "/tmp/cache"
os.makedirs(cache_dir, exist_ok=True)

def hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def is_video(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    mime = mimetypes.guess_type(filename)[0]
    return ext in VIDEO_EXTENSIONS or (mime and "video" in mime)

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

def download_with_ytdlp(url, download_dir=cache_dir):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(id)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

async def auto_cleanup(path=cache_dir, max_age=600):
    now = time.time()
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path):
            age = now - os.path.getmtime(file_path)
            if age > max_age:
                try:
                    os.remove(file_path)
                except:
                    pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_links(bot: Client, message: Message):
    urls = [x for x in message.text.strip().split() if x.lower().startswith("http")]
    if not urls:
        return await message.reply_text("No valid links found.")

    for url in urls:
        task_id = hash_url(url)
        if task_id in active_tasks:
            await message.reply_text("This link is already being processed. Please wait...")
            continue

        active_tasks.add(task_id)
        asyncio.create_task(process_url(bot, message, url, task_id))

async def process_url(bot: Client, message: Message, url: str, task_id: str):
    processing_msg = await message.reply_text("Processing your link...")
    filepath = None

    try:
        filepath = await asyncio.to_thread(download_with_ytdlp, url)
        if isinstance(filepath, tuple):
            filepath, info = filepath
        else:
            raise Exception("Download failed.")

        if not os.path.exists(filepath):
            raise Exception("Downloaded file not found.")

        file_size = os.path.getsize(filepath)
        if file_size > MAX_SIZE:
            await processing_msg.edit(f"File too large to send (> 1.9 GB). Size: {format_bytes(file_size)}")
            return

        caption = f"**Downloaded From:** {url}"
        thumb = generate_thumbnail(filepath)

        await processing_msg.edit("Uploading...")

        if is_video(filepath):
            await message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if thumb else None,
                supports_streaming=True
            )
        else:
            await message.reply_document(
                document=filepath,
                caption=caption
            )

        await processing_msg.delete()

        log_text = (
            f"**New Download**\n\n"
            f"**User:** {message.from_user.mention} (`{message.from_user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{format_bytes(file_size)}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await bot.send_message(LOG_CHANNEL, log_text)

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await process_url(bot, message, url, task_id)
    except Exception as e:
        traceback.print_exc()
        await processing_msg.edit(f"❌ Failed to download:\n{url}\n\n**{e}**")
    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except:
            pass
        active_tasks.discard(task_id)