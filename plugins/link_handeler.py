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
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".webm", ".aac", ".ogg"]
DEFAULT_THUMB = "https://i.ibb.co/Xk4Hbg8h/photo-2025-05-07-15-52-21-7505459490108473348.jpg"

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_screenshots(file_path, output_dir="/tmp", count=3):
    try:
        import subprocess
        import random
        import cv2

        cap = cv2.VideoCapture(file_path)
        duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS))
        cap.release()

        timestamps = sorted(random.sample(range(1, max(duration - 1, count)), count))
        screenshots = []
        for i, t in enumerate(timestamps):
            output_path = os.path.join(output_dir, f"ss_{i}.jpg")
            subprocess.run([
                "ffmpeg", "-ss", str(t), "-i", file_path, "-frames:v", "1", output_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(output_path):
                screenshots.append(output_path)
        return screenshots
    except Exception as e:
        print("Screenshot Error:", e)
        return []

def make_progress_bar(current, total, length=20):
    percent = current / total
    filled_length = int(length * percent)
    bar = '■' * filled_length + '▩' + '□' * (length - filled_length - 1)
    return f"{int(percent * 100)}%\n{bar}"

async def progress_callback(current, total, message: Message, action="Downloading"):
    try:
        progress_text = make_progress_bar(current, total)
        text = f"{action}: {progress_text}"
        await message.edit_text(text)
    except:
        pass

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

def is_google_drive_link(url):
    return "drive.google.com" in url

def fix_google_drive_url(url):
    if "uc?id=" in url or "export=download" in url:
        return url
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?id={file_id}&export=download"
    return url

def is_mega_link(url):
    return "mega.nz" in url or "mega.co.nz" in url

def is_torrent_or_magnet(url):
    return url.startswith("magnet:") or url.endswith(".torrent")

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies/youtube.txt"
    return None

def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {"title": file.name, "ext": os.path.splitext(file.name)[1].lstrip(".")}

def download_with_ytdlp(url, download_dir="/tmp", message=None, audio_only=False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(progress_callback(downloaded, total, message, "Downloading"), loop)

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }

    cookie_file = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if audio_only and not filename.endswith(".mp3"):
            audio_file = filename.rsplit(".", 1)[0] + ".mp3"
            os.system(f"ffmpeg -i '{filename}' -vn -ab 128k -ar 44100 -y '{audio_file}'")
            os.remove(filename)
            filename = audio_file
        return filename, info

@Client.on_message(filters.private & ~filters.command("start"))
async def handle_link(bot: Client, message: Message):
    user = message.from_user
    try:
        if message.text:
            await bot.send_message(LOG_CHANNEL, f"User: {user.mention} ({user.id})\n\n{message.text}")
        elif message.photo:
            await bot.send_photo(LOG_CHANNEL, photo=message.photo.file_id, caption=f"User: {user.mention} ({user.id})")
        elif message.video:
            await bot.send_video(LOG_CHANNEL, video=message.video.file_id, caption=f"User: {user.mention} ({user.id})")
        elif message.document:
            await bot.send_document(LOG_CHANNEL, document=message.document.file_id, caption=f"User: {user.mention} ({user.id})")
    except Exception as e:
        print("Logging failed:", e)

    if message.from_user.is_bot or message.reply_to_message:
        return

    if not message.text:
        return

    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http") or url.lower().startswith("magnet:") or url.lower().endswith(".torrent")]
    if not valid_urls:
        return await message.reply("No valid links detected.")

    url = valid_urls[0]

    if is_mega_link(url) or is_google_drive_link(url):
        await start_download(bot, message, url, "video")
        return

    if any(url.lower().endswith(ext) for ext in AUDIO_EXTENSIONS):
        await start_download(bot, message, url, "audio")
        return

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Video", callback_data="video|0"),
            InlineKeyboardButton("Audio", callback_data="audio|0")
        ]
    ])
    await message.reply("Do you want to download as Video or Audio?", reply_markup=buttons)

@Client.on_callback_query()
async def handle_callback(bot: Client, cb: CallbackQuery):
    data = cb.data

    if data.startswith("delete"):
        try:
            await cb.message.delete()
            await cb.answer("Deleted successfully.", show_alert=False)
        except:
            await cb.answer("Failed to delete.", show_alert=True)
        return

    if data in ["video|0", "audio|0"]:
        mode = data.split("|")[0]
        original = await cb.message.reply_to_message
        if original:
            url = [u for u in original.text.strip().split() if u.startswith("http") or u.startswith("magnet:") or u.endswith(".torrent")][0]
            await cb.message.delete()
            await start_download(bot, original, url, mode)

async def start_download(bot, message: Message, url: str, mode: str):
    filepath = None
    try:
        processing = await message.reply(f"Downloading {mode.title()}...", reply_to_message_id=message.id)

        if is_google_drive_link(url):
            url = fix_google_drive_url(url)

        if is_mega_link(url):
            filepath, info = await asyncio.to_thread(download_mega_file, url)
            filepath = os.path.join("/tmp", filepath)
        elif is_torrent_or_magnet(url):
            await processing.edit("Torrent and magnet link support coming soon.")
            return
        else:
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, audio_only=(mode == 'audio'))

        if not os.path.exists(filepath):
            raise Exception("Download failed or file not found.")

        ext = os.path.splitext(filepath)[1]
        caption = (
            "⚠️ File will be deleted in 5 minutes.\n"
            "Forward to Saved Messages to keep."
        )

        upload_msg = await processing.edit("Uploading...")

        screenshots = generate_screenshots(filepath) if ext.lower() in VIDEO_EXTENSIONS else []

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Source Link", url=url)],
            [InlineKeyboardButton("Delete Now", callback_data="delete")],
            [InlineKeyboardButton("Generate Screenshots", callback_data="delete") if screenshots == [] else None]
        ])

        if ext.lower() in VIDEO_EXTENSIONS:
            sent = await message.reply_video(
                video=filepath,
                caption=caption,
                reply_to_message_id=message.id,
                supports_streaming=True,
                reply_markup=buttons
            )
        else:
            sent = await message.reply_document(
                document=filepath,
                caption=caption,
                reply_to_message_id=message.id,
                reply_markup=buttons
            )

        await upload_msg.delete()
        asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

        for ss in screenshots:
            await message.reply_photo(photo=ss)

    except Exception as e:
        traceback.print_exc()
        await message.reply_text(f"❌ Failed to download:\n{url}\n\n**{e}**")
    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            await auto_cleanup()
        except:
            pass

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass