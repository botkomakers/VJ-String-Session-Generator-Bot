import os
import asyncio
import traceback
import datetime
import time
import yt_dlp
import nest_asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

nest_asyncio.apply()  # Avoid "no running event loop" error

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

progress_update_times = {}

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def download_with_ytdlp(url, download_dir="/tmp", progress_hook=None):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()  # Anonymous login
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }

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

# FloodWait safe helpers
async def safe_edit(message, text):
    try:
        await message.edit(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.edit(text)
    except:
        pass

async def safe_reply(message, text):
    try:
        return await message.reply_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await message.reply_text(text)
    except:
        pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    notice = await safe_reply(message, "Analyzing link(s)...")

    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await safe_edit(notice, "No valid links detected.")

    await safe_edit(notice, f"Found {len(valid_urls)} link(s). Starting download...")

    for url in valid_urls:
        filepath = None
        last_update_time = 0

        def ytdlp_progress_hook(d):
            nonlocal last_update_time
            now = time.time()
            if now - last_update_time < 1:
                return
            last_update_time = now
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '0.0%').strip()
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                text = f"Downloading: {percent} at {speed}, ETA: {eta}"
                asyncio.create_task(safe_edit(processing, text))
            elif d['status'] == 'finished':
                asyncio.create_task(safe_edit(processing, "Download completed, processing file..."))

        try:
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            await notice.delete()
            processing = await safe_reply(message, f"Downloading from:\n{url}")

            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
                await safe_edit(processing, "Download completed.")
            else:
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", ytdlp_progress_hook)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = f"**Downloaded from:**\n{url}"

            await processing.delete()
            uploading = await safe_reply(message, "Uploading... 0%")

            def progress_func(current, total):
                percent = (current / total) * 100
                now = time.time()
                if message.message_id not in progress_update_times:
                    progress_update_times[message.message_id] = 0
                if now - progress_update_times[message.message_id] < 1:
                    return
                progress_update_times[message.message_id] = now
                asyncio.create_task(safe_edit(uploading, f"Uploading... {percent:.1f}%"))

            if ext.lower() in VIDEO_EXTENSIONS:
                thumb = generate_thumbnail(filepath)
                await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    progress=progress_func,
                    progress_args=()
                )
            else:
                await message.reply_document(
                    document=filepath,
                    caption=caption,
                    progress=progress_func,
                    progress_args=()
                )

            await uploading.delete()

            user = message.from_user
            file_size = format_bytes(os.path.getsize(filepath))
            log_text = (
                f"**New Download Event**\n\n"
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Link:** `{url}`\n"
                f"**File Name:** `{os.path.basename(filepath)}`\n"
                f"**Size:** `{file_size}`\n"
                f"**Type:** `{'Video' if ext.lower() in VIDEO_EXTENSIONS else 'Document'}`\n"
                f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            try:
                await bot.send_message(LOG_CHANNEL, log_text)
            except:
                pass

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await safe_reply(message, f"\u274c Failed to download:\n{url}\n\n**{e}**")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass