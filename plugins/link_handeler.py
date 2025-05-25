import os
import asyncio
import time
import datetime
import traceback
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHANNEL, ADMIN_ID
import yt_dlp

VIDEO_EXTS = [".mp4", ".mkv", ".mov", ".avi", ".webm"]
DEFAULT_THUMB = "https://i.ibb.co/Xk4Hbg8h/photo-2025-05-07-15-52-21-7505459490108473348.jpg"

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

def generate_screenshots(video_path, count=3):
    duration_cmd = ["ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    duration = float(subprocess.check_output(duration_cmd).decode().strip())
    interval = duration / (count + 1)
    
    screenshots = []
    for i in range(1, count + 1):
        timestamp = str(datetime.timedelta(seconds=int(i * interval)))
        out_path = f"/tmp/ss_{i}.jpg"
        subprocess.run(["ffmpeg", "-ss", timestamp, "-i", video_path, "-vframes", "1", "-q:v", "2", out_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(out_path):
            screenshots.append(out_path)
    return screenshots

async def download_with_yt(url, msg: Message):
    download_dir = "/tmp"
    loop = asyncio.get_event_loop()

    def hook(d):
        if d['status'] == 'downloading':
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded * 100 / total)
            text = f"Downloading... {percent}%"
            try:
                asyncio.run_coroutine_threadsafe(msg.edit_text(text), loop)
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

@Client.on_message(filters.command("leech") & filters.private)
async def leech_handler(bot: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: `/leech <url> -ss <screenshot_count>`", quote=True)

    text = message.text.split()
    try:
        url = text[1]
        ss_count = 3  # default
        if "-ss" in text:
            idx = text.index("-ss")
            ss_count = int(text[idx + 1])
    except Exception as e:
        return await message.reply("Invalid command format.\nUsage: `/leech <url> -ss <count>`")

    status_msg = await message.reply("Starting download...")

    try:
        filepath, info = await asyncio.to_thread(download_with_yt, url, status_msg)
        ext = os.path.splitext(filepath)[1].lower()
        if not os.path.exists(filepath) or ext not in VIDEO_EXTS:
            return await status_msg.edit("Invalid or unsupported file.")

        await status_msg.edit("Generating screenshots...")
        screenshots = generate_screenshots(filepath, ss_count)

        media_group = []
        for ss in screenshots:
            if os.path.exists(ss):
                await message.reply_photo(photo=ss)

        caption = f"Downloaded from: {url}\n\n**File:** `{os.path.basename(filepath)}`\n**Size:** {format_bytes(os.path.getsize(filepath))}"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Delete", callback_data=f"delete_{message.id}")],
            [InlineKeyboardButton("Source Link", url=url)]
        ])

        await message.reply_video(
            video=filepath,
            caption=caption,
            supports_streaming=True,
            reply_markup=buttons,
            thumb=DEFAULT_THUMB
        )

        await status_msg.delete()

        await bot.send_message(LOG_CHANNEL, f"User: {message.from_user.mention} ({message.from_user.id})\nLeech link: {url}")

        asyncio.create_task(auto_delete(filepath, screenshots, delay=300))

    except Exception as e:
        traceback.print_exc()
        await status_msg.edit(f"Failed: {e}")

async def auto_delete(video, screenshots, delay=300):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(video):
            os.remove(video)
        for s in screenshots:
            if os.path.exists(s):
                os.remove(s)
    except:
        pass

@Client.on_callback_query()
async def delete_cb(bot: Client, cb):
    if cb.data.startswith("delete_"):
        try:
            await cb.message.delete()
            await cb.answer("Deleted.", show_alert=False)
        except:
            await cb.answer("Failed to delete.", show_alert=True)