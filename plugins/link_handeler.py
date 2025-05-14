import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

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
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

def extract_audio_from_video(video_path, output_audio_path):
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame", output_audio_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_audio_path if os.path.exists(output_audio_path) else None
    except:
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
                except:
                    pass

def download_with_ytdlp(url, format_type="video", download_dir="/tmp"):
    if format_type == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }],
            "quiet": True,
            "no_warnings": True
        }
    else:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == "audio":
            filename = os.path.splitext(filename)[0] + ".mp3"
        return filename, info

@Client.on_message(filters.private & filters.text)
async def ask_format(bot: Client, message: Message):
    if not message.text.lower().startswith("http"):
        return await message.reply_text("Please send a valid media link.")
    
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Audio", callback_data=f"download|audio|{message.text}"),
                InlineKeyboardButton("Video", callback_data=f"download|video|{message.text}")
            ]
        ]
    )
    await message.reply_text(
        "What do you want to download?",
        reply_markup=keyboard
    )

@Client.on_callback_query(filters.regex(r"^download\|(audio|video)\|(.+)"))
async def handle_download(bot: Client, query: CallbackQuery):
    await query.answer()
    format_type, url = query.data.split("|")[1:]
    user = query.from_user

    processing = await query.message.reply_text("Processing your request...")

    try:
        filepath, info = await asyncio.to_thread(download_with_ytdlp, url, format_type)

        if not os.path.exists(filepath):
            raise Exception("Download failed.")

        ext = os.path.splitext(filepath)[1]
        caption = f"**Downloaded from:**\n{url}"

        if format_type == "video":
            thumb = generate_thumbnail(filepath)
            await query.message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if thumb else None
            )
        else:
            await query.message.reply_audio(
                audio=filepath,
                caption=caption
            )

        # Log
        file_size = format_bytes(os.path.getsize(filepath))
        log_text = (
            f"**New Download Event**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File Name:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{file_size}`\n"
            f"**Type:** `{format_type.capitalize()}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        try:
            await bot.send_message(LOG_CHANNEL, log_text)
        except:
            pass

    except Exception as e:
        traceback.print_exc()
        await query.message.reply_text(f"❌ Download failed:\n{e}")
    finally:
        await processing.delete()
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except:
            pass