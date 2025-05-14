import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

def download_with_ytdlp(url, download_dir="/tmp", audio_only=False):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if audio_only else [],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if audio_only:
            filename = os.path.splitext(filename)[0] + ".mp3"
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
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
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

link_store = {}

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http")]  
    if not valid_urls:
        return await message.reply("No valid links detected.")

    link_store[message.chat.id] = valid_urls[0]  # Store only first valid URL for simplicity

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Audio", callback_data="dl_audio"),
         InlineKeyboardButton("Video", callback_data="dl_video")]
    ])

    # Send reply message with the link
    link_reply = await message.reply(f"Link detected: {valid_urls[0]}", reply_markup=buttons)
    await link_reply.delete()  # Delete the link reply message after a while

    await message.reply("What do you want to download?", reply_markup=buttons)

@Client.on_callback_query(filters.regex("dl_"))
async def button_handler(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in link_store:
        return await query.answer("Session expired. Please send the link again.", show_alert=True)

    url = link_store.pop(user_id)
    choice = query.data.split("_")[1]

    await query.message.edit_text(f"Processing {choice.title()} download...\n{url}")

    audio_only = (choice == "audio")
    try:
        # Sending initial reply with link before deleting
        link_reply = await query.message.reply(f"Link detected: {url}")

        # Delete the link reply after a while
        await asyncio.sleep(1)
        await link_reply.delete()

        # Downloading
        filepath, info = await asyncio.to_thread(download_with_ytdlp, url, audio_only=audio_only)

        if not os.path.exists(filepath):
            raise Exception("Download failed or file not found.")

        ext = os.path.splitext(filepath)[1]
        caption = f"**Downloaded from:**\n{url}"

        # If it's audio and user wants image with it
        if audio_only:
            thumb = generate_thumbnail(filepath)  # Optional image thumbnail
            await query.message.reply_audio(
                audio=filepath,
                caption=caption,
                thumb=thumb if thumb else None  # Attach image as thumbnail for audio
            )
        elif ext.lower() in VIDEO_EXTENSIONS:
            thumb = generate_thumbnail(filepath)
            await query.message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if thumb else None
            )
        else:
            await query.message.reply_document(
                document=filepath,
                caption=caption
            )

        # Log to admin channel
        user = query.from_user
        file_size = format_bytes(os.path.getsize(filepath))
        log_text = (
            f"**New Download Event**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File Name:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{file_size}`\n"
            f"**Type:** `{'Audio' if audio_only else 'Video'}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        try:
            await bot.send_message(LOG_CHANNEL, log_text)
        except:
            pass

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        traceback.print_exc()
        await query.message.reply_text(f"❌ Failed to download:\n{url}\n\n**{e}**")
    finally:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except:
            pass