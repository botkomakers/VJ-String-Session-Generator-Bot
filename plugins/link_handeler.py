import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL
from functools import wraps

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
DOWNLOAD_QUEUE = {}
THROTTLE_LIMIT = {}  # user_id: timestamp
MAX_FILE_SIZE_MB = 2048  # 2GB
QUEUE_LIMIT = 3  # Max 3 tasks per user
RATE_LIMIT_SECONDS = 15

# Decorator to limit user request rate
def rate_limited(func):
    @wraps(func)
    async def wrapper(client, message: Message):
        user_id = message.from_user.id
        now = time.time()
        if user_id in THROTTLE_LIMIT and now - THROTTLE_LIMIT[user_id] < RATE_LIMIT_SECONDS:
            return await message.reply_text("Please wait a few seconds before sending another request.")
        THROTTLE_LIMIT[user_id] = now
        await func(client, message)
    return wrapper

def download_with_ytdlp(url, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_thumbnail(file_path, output_thumb="/tmp/thumbs/thumb.jpg"):
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

def generate_preview_clip(file_path, output_clip="/tmp/thumbs/preview.mp4"):
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-ss", "00:00:01", "-t", "00:00:05", output_clip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_clip if os.path.exists(output_clip) else None
    except:
        return None

async def auto_cleanup(path="/tmp", max_age=600):
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

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]))
@rate_limited
async def auto_download_handler(bot: Client, message: Message):
    user_id = message.from_user.id
    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await message.reply_text("No valid links detected.")

    if user_id in DOWNLOAD_QUEUE and len(DOWNLOAD_QUEUE[user_id]) >= QUEUE_LIMIT:
        return await message.reply_text("You have too many pending tasks. Please wait.")

    DOWNLOAD_QUEUE.setdefault(user_id, []).append(message)

    for url in valid_urls:
        filepath = None
        try:
            notice = await message.reply_text(f"Starting download for: {url}")
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                await message.reply_text(f"File too large to upload (> {MAX_FILE_SIZE_MB}MB). Skipping...")
                os.remove(filepath)
                continue

            ext = os.path.splitext(filepath)[1]
            caption = f"**Downloaded from:**\n{url}"
            thumb = generate_thumbnail(filepath)
            preview = generate_preview_clip(filepath)
            if preview:
                await message.reply_video(preview, caption="Preview Clip")

            uploading = await message.reply_text("Uploading...")

            if ext.lower() in VIDEO_EXTENSIONS:
                await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None
                )
            else:
                await message.reply_document(
                    document=filepath,
                    caption=caption
                )

            await uploading.delete()

            # Log event
            user = message.from_user
            log_text = (
                f"**New Download Event**\n\n"
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Link:** `{url}`\n"
                f"**File Name:** `{os.path.basename(filepath)}`\n"
                f"**Size:** `{format_bytes(os.path.getsize(filepath))}`\n"
                f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            try:
                await bot.send_message(LOG_CHANNEL, log_text)
            except:
                pass

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Failed to download:\n{url}\n\n**{e}**")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumbs/thumb.jpg"):
                    os.remove("/tmp/thumbs/thumb.jpg")
                if os.path.exists("/tmp/thumbs/preview.mp4"):
                    os.remove("/tmp/thumbs/preview.mp4")
                await auto_cleanup()
            except:
                pass

    if message in DOWNLOAD_QUEUE.get(user_id, []):
        DOWNLOAD_QUEUE[user_id].remove(message)

@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_handler(_, message: Message):
    user_id = message.from_user.id
    if user_id in DOWNLOAD_QUEUE and DOWNLOAD_QUEUE[user_id]:
        DOWNLOAD_QUEUE[user_id].clear()
        await message.reply_text("Your download queue has been cancelled.")
    else:
        await message.reply_text("You have no active tasks to cancel.")