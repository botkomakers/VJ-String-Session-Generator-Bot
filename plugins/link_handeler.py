import os
import aiohttp
import asyncio
import traceback
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from collections import defaultdict, deque
from config import LOG_CHANNEL
from db import save_user

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus"]
user_queues = defaultdict(deque)
active_tasks = set()
MAX_QUEUE_LENGTH = 5

# User selection for format storage (user_id -> info dict)
user_selection = {}

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

def get_formats_info(url):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get("formats", [])
        # Filter formats for video and audio with filesize info
        video_formats = []
        audio_formats = []
        for f in formats:
            if f.get('filesize') is None and f.get('filesize_approx'):
                filesize = f['filesize_approx']
            else:
                filesize = f.get('filesize', 0)
            ext = f.get("ext", "").lower()
            # Video with video+audio
            if f.get("vcodec") != "none" and f.get("acodec") != "none":
                video_formats.append({
                    "format_id": f["format_id"],
                    "ext": ext,
                    "resolution": f.get("format_note") or f.get("height"),
                    "filesize": filesize,
                    "format_note": f.get("format_note", "")
                })
            # Audio only
            elif f.get("vcodec") == "none" and f.get("acodec") != "none":
                audio_formats.append({
                    "format_id": f["format_id"],
                    "ext": ext,
                    "abr": f.get("abr"),
                    "filesize": filesize,
                })
        return info, video_formats, audio_formats

async def download_format(url, format_id, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": format_id,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

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

    # First, get video and audio formats available
    try:
        info, video_formats, audio_formats = await asyncio.to_thread(get_formats_info, url)
    except Exception as e:
        return await message.reply_text(f"❌ Failed to fetch video info:\n{e}")

    if not video_formats and not audio_formats:
        return await message.reply_text("❌ No downloadable formats found.")

    # Save info and formats to user_selection for callback usage
    user_selection[user_id] = {
        "url": url,
        "info": info,
        "video_formats": video_formats,
        "audio_formats": audio_formats
    }

    # Build buttons for video formats (show resolution and size)
    buttons = []
    for vf in video_formats:
        size_text = format_bytes(vf["filesize"]) if vf["filesize"] else "Unknown size"
        label = f"Video {vf.get('resolution') or vf['format_note']} ({vf['ext']}) {size_text}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"download_vid:{vf['format_id']}")])

    # Add audio format buttons
    for af in audio_formats:
        size_text = format_bytes(af["filesize"]) if af["filesize"] else "Unknown size"
        label = f"Audio {af.get('abr', '')}kbps ({af['ext']}) {size_text}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"download_aud:{af['format_id']}")])

    await message.reply_text(
        "Select the format to download:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query()
async def format_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if user_id not in user_selection:
        return await callback_query.answer("Session expired or no selection found.", show_alert=True)

    sel = user_selection[user_id]
    url = sel["url"]

    if data.startswith("download_vid:") or data.startswith("download_aud:"):
        format_id = data.split(":", 1)[1]

        # Add to queue
        if len(user_queues[user_id]) >= MAX_QUEUE_LENGTH:
            await callback_query.answer("⚠️ Your queue is full. Please wait.", show_alert=True)
            return

        user_queues[user_id].append((callback_query.message, url, format_id))
        await callback_query.answer("Added to download queue.")
        await callback_query.message.edit("⏳ Added to queue. Please wait...")

        if user_id not in active_tasks:
            active_tasks.add(user_id)
            await process_user_queue(client, user_id)
    else:
        await callback_query.answer()

async def process_user_queue(bot: Client, user_id: int):
    while user_queues[user_id]:
        message, url, format_id = user_queues[user_id].popleft()
        processing = await message.reply_text("⏳ Processing your download...", quote=True)
        filepath = None

        try:
            filepath, info = await asyncio.to_thread(download_format, url, format_id)

            if not os.path.exists(filepath):
                raise Exception("Download failed")

            ext = os.path.splitext(filepath)[1].lower()
            thumb = generate_thumbnail(filepath)

            caption = f"✅ **Downloaded:** {info.get('title')}"

            if ext in VIDEO_EXTENSIONS:
                sent_msg = await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None
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
    user_selection.pop(user_id, None)