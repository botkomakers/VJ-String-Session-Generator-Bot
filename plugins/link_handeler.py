import os
import asyncio
import traceback
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message
from collections import defaultdict, deque
from config import LOG_CHANNEL
from db import save_user

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus"]
user_queues = defaultdict(deque)
active_tasks = set()
MAX_QUEUE_LENGTH = 5

def download_with_ytdlp(url, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "postprocessors": [{
            'key': 'FFmpegVideoConvertor',
            'preferredformat': 'mp4',  # <-- এখানে বানান ঠিক
        }],
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

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        import subprocess
        subprocess.run([
            "ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_thumb if os.path.exists(output_thumb) else None
    except Exception:
        return None

async def auto_cleanup(path="/tmp", max_age=300):
    now = time.time()
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path):
            age = now - os.path.getmtime(file_path)
            if age > max_age:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]))
async def queue_video_download(bot: Client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()

    if message.reply_to_message and message.reply_to_message.text:
        url = message.reply_to_message.text.strip()

    if not any(url.startswith(prefix) for prefix in ["http://", "https://"]):
        return await message.reply_text("❌ Invalid link.")

    save_user(user_id, message.from_user.first_name, message.from_user.username)

    if len(user_queues[user_id]) >= MAX_QUEUE_LENGTH:
        return await message.reply_text("⚠️ Queue full. Please wait...")

    user_queues[user_id].append((message, url))

    if user_id in active_tasks:
        await message.reply_text("⏳ Added to queue. Please wait...")
        return

    active_tasks.add(user_id)
    await process_user_queue(bot, user_id)

async def process_user_queue(bot: Client, user_id: int):
    while user_queues[user_id]:
        message, url = user_queues[user_id].popleft()
        processing = await message.reply_text("⏳ Processing your video...", quote=True)
        filepath = None

        try:
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("Download failed")

            ext = os.path.splitext(filepath)[1].lower()
            thumb = generate_thumbnail(filepath)

            caption = f"✅ **Downloaded:** {info.get('title', 'No Title')}"

            if ext in VIDEO_EXTENSIONS:
                sent_msg = await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    supports_streaming=True
                )
            elif ext in AUDIO_EXTENSIONS:
                sent_msg = await message.reply_audio(
                    audio=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    title=info.get('title'),
                    performer=info.get('uploader')
                )
            else:
                sent_msg = await message.reply_document(
                    document=filepath,
                    caption=caption
                )

            forwarded = await sent_msg.copy(chat_id=LOG_CHANNEL)
            log_text = (
                f"**User:** [{message.from_user.first_name}](tg://user?id={user_id}) (`{user_id}`)\n"
                f"**Link:** `{url}`\n"
                f"**Filename:** `{os.path.basename(filepath)}`\n"
                f"**Size:** `{format_bytes(os.path.getsize(filepath))}`\n"
            )
            await bot.send_message(LOG_CHANNEL, log_text, reply_to_message_id=forwarded.id)

        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Failed to download:\n`{url}`\n\n**{e}**")
        finally:
            if processing:
                await processing.delete()
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()

    active_tasks.remove(user_id)