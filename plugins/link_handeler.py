import os
import asyncio
import yt_dlp
import subprocess
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm"]

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f}{unit}"
        size /= 1024
    return f"{size:.2f}TB"

def generate_screenshots(file_path: str, count: int = 3):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        duration = float(result.stdout)
        intervals = [int(duration * (i + 1) / (count + 1)) for i in range(count)]
        shots = []

        for i, sec in enumerate(intervals):
            output_path = f"/tmp/ss_{i}.jpg"
            subprocess.run([
                "ffmpeg", "-ss", str(sec), "-i", file_path,
                "-frames:v", "1", "-q:v", "2", output_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if os.path.exists(output_path):
                shots.append(output_path)

        return shots
    except:
        return []

def download_with_yt(url: str, update_msg: Message):
    download_dir = "/tmp"

    def hook(d):
        if d['status'] == 'downloading':
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded * 100 / total)
            try:
                asyncio.run_coroutine_threadsafe(
                    update_msg.edit(f"Downloading... {percent}%"),
                    asyncio.get_event_loop()
                )
            except:
                pass

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "noplaylist": True,
        "progress_hooks": [hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        return file_path, info

@Client.on_message(filters.command("leech") & (filters.group | filters.private))
async def leech_handler(bot: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/leech {url} -ss {count}`", quote=True)

    url = args[1]
    ss_count = 3
    if "-ss" in args:
        try:
            idx = args.index("-ss")
            ss_count = int(args[idx + 1])
        except:
            pass

    status = await message.reply("Starting download...")

    try:
        filepath, info = await asyncio.to_thread(download_with_yt, url, status)
        if not os.path.exists(filepath):
            return await status.edit("Download failed.")

        await status.edit("Generating screenshots...")
        screenshots = generate_screenshots(filepath, ss_count)

        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        user_id = message.from_user.id

        media_group = [InputMediaPhoto(media=img) for img in screenshots[:10]]
        first_msg = None
        if media_group:
            log_msg = await bot.send_media_group(chat_id=LOG_CHANNEL, media=media_group)
            first_msg = log_msg[0] if log_msg else None

            try:
                for ss in screenshots:
                    await bot.send_photo(user_id, ss)
            except:
                pass

            log_button = InlineKeyboardMarkup([[
                InlineKeyboardButton("🖼 View Screenshots", url=first_msg.link if first_msg else "https://t.me")
            ]])

            await message.reply(
                "Your requested screenshots have been sent to your DM.\n"
                "Click the button below to view them in the log channel.",
                reply_markup=log_button
            )

        await status.delete()

    except Exception as e:
        await status.edit(f"❌ Failed: `{e}`")

    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            for f in os.listdir("/tmp"):
                if f.startswith("ss_") and f.endswith(".jpg"):
                    os.remove(os.path.join("/tmp", f))
        except:
            pass