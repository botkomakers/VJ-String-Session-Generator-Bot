import os
import asyncio
import yt_dlp
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHANNEL, ADMIN_ID
import datetime

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm"]

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_screenshots(file_path, count=3):
    try:
        duration_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(duration_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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

def download_with_yt(url, msg: Message):
    download_dir = "/tmp"

    def hook(d):
        if d['status'] == 'downloading':
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded * 100 / total)
            text = f"Downloading... {percent}%"
            try:
                asyncio.run_coroutine_threadsafe(msg.edit_text(text), asyncio.get_event_loop())
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
async def leech_handler(bot, message: Message):
    text = message.text.split()
    if len(text) < 2:
        return await message.reply("Usage: /leech {url} -ss {count}")

    url = text[1]
    try:
        ss_count = 3  # default
        if "-ss" in text:
            ss_index = text.index("-ss")
            ss_count = int(text[ss_index + 1])
    except:
        ss_count = 3

    status_msg = await message.reply("Downloading...")

    try:
        filepath, info = await asyncio.to_thread(download_with_yt, url, status_msg)
        if not os.path.exists(filepath):
            return await status_msg.edit("Download failed.")

        await status_msg.edit("Generating screenshots...")
        screenshots = generate_screenshots(filepath, ss_count)

        caption = f"**File:** `{os.path.basename(filepath)}`\n**Size:** `{format_bytes(os.path.getsize(filepath))}`"

        for shot in screenshots:
            await message.reply_photo(photo=shot)

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Download Again", url=url)],
            [InlineKeyboardButton("Delete", callback_data="delete_me")]
        ])

        await message.reply_document(
            document=filepath,
            caption=caption,
            reply_markup=buttons
        )

        await status_msg.delete()

        log_text = (
            f"Leech Complete\nUser: {message.from_user.mention} ({message.from_user.id})\n"
            f"File: {os.path.basename(filepath)}\nSize: {format_bytes(os.path.getsize(filepath))}\n"
            f"URL: {url}\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await bot.send_message(LOG_CHANNEL, log_text)

    except Exception as e:
        await status_msg.edit(f"Failed: {e}")

    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            for f in os.listdir("/tmp"):
                if f.startswith("ss_") and f.endswith(".jpg"):
                    os.remove(os.path.join("/tmp", f))
        except:
            pass

@Client.on_callback_query(filters.regex("delete_me"))
async def delete_callback(bot, query):
    try:
        await query.message.delete()
        await query.answer("Deleted.", show_alert=False)
    except:
        await query.answer("Can't delete.", show_alert=True)