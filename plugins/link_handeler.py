import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import FloodWait
from collections import defaultdict, deque
from config import LOG_CHANNEL
from db import save_user

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
user_queues = defaultdict(deque)
active_tasks = set()
MAX_QUEUE_LENGTH = 5

FORMAT_OPTIONS = {
    "mp4": "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
    "mp3": "bestaudio[ext=m4a]/bestaudio/best",
    "best": "best"
}

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
        subprocess.run([
            "ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

def download_with_ytdlp(url, format_key="mp4", download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": FORMAT_OPTIONS.get(format_key, "best"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

async def auto_cleanup(path="/tmp", max_age=300):
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
async def handle_link(bot: Client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()
    save_user(user_id, message.from_user.first_name, message.from_user.username)

    if len(user_queues[user_id]) >= MAX_QUEUE_LENGTH:
        await message.reply_text("⚠️ Your queue is full (Max 5 tasks). Please wait or use /cancel.")
        return

    user_queues[user_id].append((message, url))
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("MP4", callback_data=f"format:mp4|{user_id}"),
            InlineKeyboardButton("MP3", callback_data=f"format:mp3|{user_id}"),
            InlineKeyboardButton("Best", callback_data=f"format:best|{user_id}")
        ]
    ])
    await message.reply_text("Select a format to download:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^format:(mp4|mp3|best)\|(\d+)$"))
async def process_format(bot: Client, query: CallbackQuery):
    format_key, uid = query.data.split(":")[1].split("|")
    user_id = int(uid)

    if query.from_user.id != user_id:
        await query.answer("This is not for you.", show_alert=True)
        return

    if user_id in active_tasks:
        await query.message.reply_text("⏳ Added to queue. Processing previous task...")
        return

    active_tasks.add(user_id)
    await query.message.edit_text("▶️ Download starting in background...")
    await process_user_queue(bot, user_id, format_key)

async def process_user_queue(bot: Client, user_id: int, format_key="mp4"):
    while user_queues[user_id]:
        message, url = user_queues[user_id].popleft()
        reply = await message.reply_text("Processing your video...")
        filepath = None

        try:
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url, format_key)
            if not os.path.exists(filepath):
                raise Exception("Download failed")

            ext = os.path.splitext(filepath)[1]
            thumb = generate_thumbnail(filepath)

            caption = f"✅ **Downloaded:** {info.get('title')}\n**Requested by:** {message.from_user.mention}"

            sent = await message.reply_document(
                document=filepath,
                caption=caption,
                thumb=thumb if thumb else None
            )

            forwarded = await sent.copy(chat_id=LOG_CHANNEL)
            log_text = (
                f"**User:** [{message.from_user.first_name}](tg://user?id={user_id}) (`{user_id}`)\n"
                f"**Link:** `{url}`\n"
                f"**File:** `{os.path.basename(filepath)}`\n"
                f"**Size:** `{format_bytes(os.path.getsize(filepath))}`"
            )
            await bot.send_message(LOG_CHANNEL, log_text, reply_to_message_id=forwarded.id)

        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Failed to download:\n{url}\n\n**Error:** {e}")
        finally:
            await reply.delete()
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()

    active_tasks.remove(user_id)

@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_user_queue(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_queues:
        user_queues[user_id].clear()
        await message.reply_text("✅ Your queue has been cleared.")
    else:
        await message.reply_text("Your queue is already empty.")