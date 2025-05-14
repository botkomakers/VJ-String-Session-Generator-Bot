import os
import yt_dlp
import time
import asyncio
import traceback
import datetime
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
COOKIES_PATH = "cookies.txt"
THUMB_PATH = "/tmp/thumb.jpg"
DOWNLOAD_DIR = "/tmp"

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_thumbnail(video_path):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:02", "-vframes", "1", THUMB_PATH],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return THUMB_PATH if os.path.exists(THUMB_PATH) else None
    except:
        return None

def get_ytdlp_options():
    return {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).200s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cookies": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        "geo_bypass": True,
        "extractor_args": {"generic": ["impersonate=chrome"]},
    }

def download_with_ytdlp(url):
    try:
        ydl_opts = get_ytdlp_options()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info
    except Exception as e:
        raise Exception(f"yt-dlp error: {e}")

async def auto_cleanup(path=DOWNLOAD_DIR, max_age=600):
    now = time.time()
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path) and (now - os.path.getmtime(file_path)) > max_age:
            try:
                os.remove(file_path)
            except:
                pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    urls = [url for url in message.text.strip().split() if url.lower().startswith("http")]
    if not urls:
        return await message.reply("❌ No valid link found.")

    status = await message.reply(f"🔗 Detected {len(urls)} link(s). Starting...")

    for url in urls:
        try:
            await status.edit(f"⏬ Downloading from:\n`{url}`")
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = f"✅ **Downloaded from:** {url}"

            await status.edit("⬆️ Uploading...")
            thumb = generate_thumbnail(filepath) if ext in VIDEO_EXTENSIONS else None

            if ext.lower() in VIDEO_EXTENSIONS:
                await message.reply_video(video=filepath, caption=caption, thumb=thumb)
            else:
                await message.reply_document(document=filepath, caption=caption)

            # Logging
            file_size = format_bytes(os.path.getsize(filepath))
            user = message.from_user
            log_msg = (
                f"**Download Log**\n\n"
                f"👤 User: {user.mention} (`{user.id}`)\n"
                f"🔗 Link: `{url}`\n"
                f"📁 File: `{os.path.basename(filepath)}`\n"
                f"📦 Size: `{file_size}`\n"
                f"📌 Type: `{'Video' if ext in VIDEO_EXTENSIONS else 'File'}`\n"
                f"🕰️ Time: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            if LOG_CHANNEL:
                await bot.send_message(LOG_CHANNEL, log_msg)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            await message.reply(f"❌ Failed to process `{url}`\n\n**Reason:** {e}")
            traceback.print_exc()
        finally:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists(THUMB_PATH):
                    os.remove(THUMB_PATH)
                await auto_cleanup()
            except:
                pass