import os
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from yt_dlp import YoutubeDL

VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.webm', '.mov']
AUDIO_EXTENSIONS = ['.mp3', '.aac', '.flac', '.m4a']

@Client.on_message(filters.private & filters.text)
async def link_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        return

    status = await message.reply("⏳ Processing link...")

    # Create inline keyboard with Audio and Video buttons
    buttons = [
        [InlineKeyboardButton("Audio", callback_data=f"audio_{url}")],
        [InlineKeyboardButton("Video", callback_data=f"video_{url}")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    await status.edit("⬇️ Choose your download format:", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^(audio|video)_"))
async def handle_download(client: Client, callback_query):
    action, url = callback_query.data.split("_", 1)

    status = await callback_query.message.reply("⏳ Processing link...")

    # For Audio Download
    if action == "audio":
        try:
            ydl_opts = {
                "outtmpl": f"audio_{int(time.time())}.%(ext)s",
                "format": "bestaudio/best",
                "quiet": True,
                "extractaudio": True,
                "audioquality": 1,
                "postprocessors": [{
                    "key": "FFmpegAudioConvertor",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)

            await status.edit("⬆️ Uploading audio...")
            await callback_query.message.reply_audio(audio=file_path, caption=f"✅ {info.get('title', 'Audio')}")
            os.remove(file_path)

        except Exception as e:
            print(f"Audio error: {e}")
            await status.edit("❌ Failed to download audio from this link.")

    # For Video Download
    elif action == "video":
        try:
            ydl_opts = {
                "outtmpl": f"video_{int(time.time())}.%(ext)s",
                "format": "bestvideo+bestaudio/best",
                "quiet": True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)

            await status.edit("⬆️ Uploading video...")
            await callback_query.message.reply_video(video=file_path, caption=f"✅ {info.get('title', 'Video')}")
            os.remove(file_path)

        except Exception as e:
            print(f"Video error: {e}")
            await status.edit("❌ Failed to download video from this link.")