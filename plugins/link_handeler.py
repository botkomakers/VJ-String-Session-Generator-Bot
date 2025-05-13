import os
import time
import asyncio
import requests
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from yt_dlp import YoutubeDL

# ---------- Utility Functions ----------
def sanitize_filename(title: str):
    return ''.join(c if c.isalnum() else '_' for c in title)[:50]

def download_thumbnail(url: str, filename: str):
    try:
        r = requests.get(url)
        if r.ok:
            with open(filename, 'wb') as f:
                f.write(r.content)
            return filename
    except Exception as e:
        print(f"Thumbnail error: {e}")
    return None

async def upload_progress(current, total, status):
    percent = f"{(current / total) * 100:.1f}%"
    try:
        await status.edit(f"⬆️ Uploading...\nProgress: {percent}", parse_mode="markdown")
    except:
        pass

# ---------- General Video Downloader Function ----------
async def download_video(url: str, file_name: str, status: Message, is_audio: bool = False):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': file_name,
        'format': 'bestaudio' if is_audio else 'best',
        'progress_hooks': [lambda d: asyncio.create_task(progress_hook(d, status))],
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        return info
    except Exception as e:
        print(f"Download error: {e}")
        await status.edit("❌ Failed to download the video.")
        return None

# ---------- YouTube Video Downloader ----------
@Client.on_message(filters.command("video") & filters.private)
async def video_command_handler(client, message: Message):
    query = ' '.join(message.command[1:])
    if not query:
        return await message.reply("❌ Usage: /video [YouTube link]", parse_mode="markdown")
    
    # Check if the URL is from a valid platform
    if "youtube.com/watch?v=" not in query and "youtu.be/" not in query:
        return await message.reply("❌ Please provide a valid YouTube video link.")
    
    status = await message.reply("🔍 Extracting video info...")

    ydl_opts = {
        "cookiefile": "youtube_cookies.txt",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as e:
        print(f"Extraction error: {e}")
        return await status.edit("❌ Failed to extract video info.")

    # Extracting video info and generating button options
    title = info.get('title', 'No Title')
    thumbnail = info.get('thumbnail')
    formats = info.get('formats', [])
    duration = info.get('duration', 0)
    views = info.get('view_count', 0)
    upload_date = info.get('upload_date', '')
    date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if upload_date else "Unknown"

    desc = f"""**🎬 Title:** {title}

⏱ Duration: {duration // 60}:{duration % 60:02d} minutes
👁 Views: {views:,}
📅 Uploaded: {date_str}

Select a format to download:"""

    buttons = []
    unique = set()
    for f in formats:
        fmt_id = f.get("format_id")
        fmt_note = f.get("format_note", "")
        ext = f.get("ext", "")
        filesize = f.get("filesize") or f.get("filesize_approx")
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        height = f.get("height", 0)
        if not fmt_id or not ext or not filesize:
            continue
        tag = f"{fmt_note}-{ext}-{filesize}"
        if tag in unique:
            continue
        unique.add(tag)

        size = round(filesize / 1024 / 1024, 2)
        label = ""
        if vcodec != "none" and acodec != "none":
            label = f"{fmt_note.upper() or str(height)+'p'} - {ext.upper()} - {size}MB"
        elif vcodec != "none" and acodec == "none":
            label = f"{fmt_note.upper() or str(height)+'p'} - {ext.upper()} - {size}MB 🔇 No Audio"
        elif vcodec == "none" and acodec != "none":
            label = f"{ext.upper()} - {size}MB 🎵 Audio Only"
        else:
            continue

        buttons.append([
            InlineKeyboardButton(f"🎞 {label}", callback_data=f"yt|{fmt_id}|{query}")
        ])

    buttons.append([
        InlineKeyboardButton("🎵 128kbps MP3", callback_data=f"yt|bestaudio|{query}")
    ])

    if not buttons:
        return await status.edit("❌ No downloadable formats found.")

    thumb_file = sanitize_filename(title) + ".jpg"
    download_thumbnail(thumbnail, thumb_file)
    await status.delete()

    await message.reply_photo(
        photo=thumb_file if os.path.exists(thumb_file) else None,
        caption=desc,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    if os.path.exists(thumb_file):
        os.remove(thumb_file)

@Client.on_callback_query(filters.regex("^yt|"))
async def format_button_handler(client, query: CallbackQuery):
    await query.answer()
    _, format_id, video_url = query.data.split("|")
    status = await query.message.edit("📥 Downloading selected format...")
    is_audio = format_id == "bestaudio"
    file_ext = "mp3" if is_audio else "mp4"
    file_name = f"yt{int(time.time())}.{file_ext}"

    info = await download_video(video_url, file_name, status, is_audio)
    if not info:
        return

    thumb_file = None
    if info.get('thumbnail'):
        thumb_file = sanitize_filename(info['title']) + ".jpg"
        download_thumbnail(info['thumbnail'], thumb_file)

    caption = f"🎬 {info.get('title', 'Untitled')}"

    try:
        if is_audio:
            await query.message.reply_audio(
                audio=file_name,
                caption=caption,
                thumb=thumb_file if thumb_file and os.path.exists(thumb_file) else None,
                progress=lambda c, t: upload_progress(c, t, status)
            )
        else:
            await query.message.reply_video(
                video=file_name,
                caption=caption,
                thumb=thumb_file if thumb_file and os.path.exists(thumb_file) else None,
                progress=lambda c, t: upload_progress(c, t, status)
            )
        await status.delete()
    except Exception as e:
        await query.message.reply("❌ Sending failed.")
        print(e)

    for f in [file_name, thumb_file]:
        if f and os.path.exists(f):
            os.remove(f)

# ---------- Direct Link Video Downloader ----------
@Client.on_message(filters.private)
async def direct_link_video_handler(client, message: Message):
    query = message.text
    if not query or "http" not in query:
        return await message.reply("❌ Please provide a valid video URL.")

    status = await message.reply("🔍 Fetching video info...")

    info = await download_video(query, f"direct_{int(time.time())}.mp4", status)
    if not info:
        return await status.edit("❌ Failed to download the video.")

    title = info.get('title', 'Direct Video')
    caption = f"🎬 {title}"

    try:
        await message.reply_video(
            video=f"direct_{int(time.time())}.mp4",
            caption=caption,
            progress=lambda c, t: upload_progress(c, t, status)
        )
        await status.delete()
    except Exception as e:
        await message.reply("❌ Sending failed.")
        print(e)

    # Cleanup
    for f in [f"direct_{int(time.time())}.mp4"] :
        if f and os.path.exists(f):
            os.remove(f)