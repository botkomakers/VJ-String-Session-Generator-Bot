import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

# Use absolute path for DB file for consistency
DB_FILE = os.path.join(os.path.dirname(__file__), "download_recovery.db")


def init_db():
    try:
        with sqlite3.connect(DB_FILE) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS downloads (
                user_id INTEGER,
                url TEXT,
                status TEXT,
                filepath TEXT,
                timestamp TEXT
            )''')
            db.commit()
        print("Database and 'downloads' table initialized.")
    except Exception as e:
        print(f"Error initializing DB: {e}")


init_db()


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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        return None


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
    except Exception:
        # Ignore edit errors (usually FloodWait or message deleted)
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
                except Exception:
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


def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }


def download_with_ytdlp(url, download_dir="/tmp", message=None):
    # Use event loop in the current thread for yt-dlp hooks
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(downloaded, total, message, "Downloading"),
                    loop
                )

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info


@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    try:
        notice = await message.reply_text("Analyzing link(s)...")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        notice = await message.reply_text("Analyzing link(s)...")

    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await notice.edit("No valid links detected.")

    await notice.edit(f"Found {len(valid_urls)} link(s). Starting download...")

    for url in valid_urls:
        filepath = None
        try:
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            await notice.delete()
            processing = await message.reply_text(f"Downloading from:\n{url}", reply_to_message_id=message.id)

            with sqlite3.connect(DB_FILE) as db:
                db.execute("INSERT INTO downloads (user_id, url, status, filepath, timestamp) VALUES (?, ?, ?, ?, ?)", (
                    message.from_user.id, url, "downloading", "", datetime.datetime.now().isoformat()
                ))
                db.commit()

            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
            else:
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = (
                "**\u26a0\ufe0f IMPORTANT NOTICE \u26a0\ufe0f**\n\n"
                "This video will be **automatically deleted in 5 minutes** due to copyright policies.\n"
                "Please **forward** it to your **Saved Messages** or any private chat to keep a copy.\n\n"
                f"**Source:** [Click to open]({url})"
            )

            upload_msg = await processing.edit("Uploading...")
            thumb = generate_thumbnail(filepath)

            if ext.lower() in VIDEO_EXTENSIONS:
                sent = await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    reply_to_message_id=message.id,
                    supports_streaming=True
                )
            else:
                sent = await message.reply_document(
                    document=filepath,
                    caption=caption,
                    reply_to_message_id=message.id
                )

            await upload_msg.delete()
            asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

            with sqlite3.connect(DB_FILE) as db:
                db.execute("UPDATE downloads SET status = ?, filepath = ? WHERE user_id = ? AND url = ?", (
                    "done", filepath, message.from_user.id, url
                ))
                db.commit()

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

            if ext.lower() in VIDEO_EXTENSIONS:
                await bot.send_video(LOG_CHANNEL, video=filepath, caption=log_text, thumb=thumb, supports_streaming=True)
            else:
                await bot.send_document(LOG_CHANNEL, document=filepath, caption=log_text)

            # Check for porn-related keywords in URL and alert admin
            if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
                alert = (
                    f"\u26a0\ufe0f **Porn link detected**\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Link:** {url}"
                )
                await bot.send_message(ADMIN_ID, alert)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"\u274c Failed to download:\n{url}\n\n**{e}**")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except Exception:
                pass


async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except Exception:
        pass


async def resume_incomplete_downloads(bot: Client):
    with sqlite3.connect(DB_FILE) as db:
        cursor = db.execute("SELECT user_id, url FROM downloads WHERE status = 'downloading'")
        rows = cursor.fetchall()
        for user_id, url in rows:
            try:
                dummy = await bot.send_message(user_id, f"Bot restarted. Resuming previous download:\n{url}")
                await auto_download_handler(bot, dummy)
            except Exception:
                pass


@Client.on_message(filters.command("start") & filters.private)
async def start_handler(bot: Client, message: Message):
    await message.reply_text("Send me a link to start downloading.")


@Client.on_message(filters.command("resume") & filters.user(ADMIN_ID))
async def resume_command(bot: Client, message: Message):
    await resume_incomplete_downloads(bot)