import os
import asyncio
import time
import datetime
import traceback
from mega import Mega
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]


def progress_bar(percentage: float) -> str:
    total_blocks = 10
    filled_blocks = int(percentage // 10)
    remainder = percentage % 10
    partial_block = 1 if remainder >= 5 else 0  # Show partial block if over 5%
    empty_blocks = total_blocks - filled_blocks - partial_block
    bar = "■" * filled_blocks + "▩" * partial_block + "□" * empty_blocks
    return bar[:total_blocks]


async def edit_progress_message(message: Message, prefix: str, percent: float):
    bar = progress_bar(percent)
    text = f"{prefix}: {int(percent)}%\n{bar}"
    try:
        await message.edit(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.edit(text)
    except:
        pass


def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"


def is_google_drive_link(url: str) -> bool:
    return "drive.google.com" in url


def fix_google_drive_url(url: str) -> str:
    if "uc?id=" in url or "export=download" in url:
        return url
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?id={file_id}&export=download"
    return url


def is_mega_link(url: str) -> bool:
    return "mega.nz" in url or "mega.co.nz" in url


def download_with_progress(url, download_dir="/tmp", progress_callback=None):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    if progress_callback:

        def hook(d):
            if d['status'] == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                if total_bytes:
                    percent = downloaded_bytes / total_bytes * 100
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(percent),
                        asyncio.get_event_loop()
                    )

        ydl_opts['progress_hooks'] = [hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info


def download_mega_file(url, download_dir="/tmp"):
    mega = Mega()
    m = mega.login()  # Anonymous login
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }


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


@Client.on_message(filters.private & filters.text)
async def auto_download_handler(bot: Client, message: Message):
    # Check if message is a reply, if yes extract URLs from replied text, else from current text
    if message.reply_to_message and message.reply_to_message.text:
        urls = message.reply_to_message.text.strip().split()
    else:
        urls = message.text.strip().split()

    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await message.reply_text("❌ No valid links found.")

    notice = await message.reply_text(f"Found {len(valid_urls)} link(s). Starting download...")

    for url in valid_urls:
        filepath = None
        try:
            # Fix Google Drive links
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            await notice.delete()
            progress_msg = await message.reply_text(f"Starting download from:\n{url}")

            # Download handlers
            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
            else:
                async def progress_cb(percent):
                    await edit_progress_message(progress_msg, "Downloading", percent)

                filepath, info = await asyncio.to_thread(download_with_progress, url, "/tmp", progress_cb)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = f"Downloaded from:\n{url}"

            await progress_msg.edit("Download complete. Starting upload...")

            def upload_progress(current, total):
                percent = current / total * 100
                asyncio.run_coroutine_threadsafe(
                    edit_progress_message(progress_msg, "Uploading", percent),
                    asyncio.get_event_loop()
                )

            if ext.lower() in VIDEO_EXTENSIONS:
                await bot.send_video(
                    chat_id=message.chat.id,
                    video=filepath,
                    caption=caption,
                    progress=upload_progress
                )
            else:
                await bot.send_document(
                    chat_id=message.chat.id,
                    document=filepath,
                    caption=caption,
                    progress=upload_progress
                )

            await progress_msg.delete()

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
            await message.reply_text(f"❌ Failed to download:\n{url}\n\nError: {e}")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                await auto_cleanup()
            except:
                pass