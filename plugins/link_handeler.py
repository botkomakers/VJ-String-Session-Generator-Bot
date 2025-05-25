import os
import asyncio
import yt_dlp
import subprocess
import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from config import LOG_CHANNEL, ADMIN_ID

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

@Client.on_message(filters.command("leech") & (filters.private | filters.group))
async def leech_handler(bot, message: Message):
    text = message.text.split()
    if len(text) < 2:
        return await message.reply("Usage: /leech {url} -ss {count}")

    url = text[1]
    try:
        ss_count = 3
        if "-ss" in text:
            ss_index = text.index("-ss")
            ss_count = int(text[ss_index + 1])
    except:
        ss_count = 3

    status_msg = await message.reply("Downloading...")

    filepath = None
    try:
        filepath, info = await asyncio.to_thread(download_with_yt, url, status_msg)
        if not os.path.exists(filepath):
            return await status_msg.edit("Download failed.")

        await status_msg.edit("Generating screenshots...")
        screenshots = generate_screenshots(filepath, ss_count)

        # Send screenshots to user's DM
        try:
            for shot in screenshots:
                await bot.send_photo(chat_id=message.from_user.id, photo=shot)
        except:
            pass

        # Send screenshots to log channel
        media_group = [InputMediaPhoto(media=img) for img in screenshots[:3]]
        media_msg_ids = []

        if media_group:
            sent_msgs = await bot.send_media_group(chat_id=LOG_CHANNEL, media=media_group)
            media_msg_ids = [msg.message_id for msg in sent_msgs]

        screenshot_link = f"https://t.me/{(await bot.get_chat(LOG_CHANNEL)).username}/{media_msg_ids[0]}" if media_msg_ids else None

        caption = f"**File:** `{os.path.basename(filepath)}`\n**Size:** `{format_bytes(os.path.getsize(filepath))}`"

        buttons = [
            [InlineKeyboardButton("🔐 Source Link", url=url)],
            [InlineKeyboardButton("🗑 Delete", callback_data="delete_me")]
        ]

        if screenshot_link:
            buttons.append([
                InlineKeyboardButton("🖼 View Screenshots", url=screenshot_link)
            ])

        await message.reply_document(
            document=filepath,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        await status_msg.delete()

        log_caption = (
            f"{info.get('title')}\n"
            f"Size: {format_bytes(os.path.getsize(filepath))}\n"
            f"Elapsed: 1m\n"
            f"Mode: #Leech | #Aria2\n"
            f"Total Files: 1\n"
            f"By: @{message.from_user.username or message.from_user.id}\n"
            f"\nFile(s) have been Sent.\nAccess via Links..."
        )

        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=log_caption
        )

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