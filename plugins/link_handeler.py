import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

DB_FILE = os.path.join(os.path.dirname(__file__), "download_recovery.db")

# Track ongoing downloads {user_id: asyncio.Task}
ongoing_downloads = {}

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
        print("Database initialized.")
    except Exception as e:
        print(f"DB init error: {e}")

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
    percent = current / total if total else 0
    filled_length = int(length * percent)
    bar = '■' * filled_length + '▩' + '□' * max(length - filled_length - 1, 0)
    return f"{int(percent * 100)}%\n{bar}"

def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("Help ❓", callback_data="help")],
    ]
    return InlineKeyboardMarkup(buttons)

def start_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("Help ❓", callback_data="help")],
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("Resume Incomplete Downloads ♻️", callback_data="resume")])
    return InlineKeyboardMarkup(buttons)

def cancel_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Cancel Download ❌", callback_data="cancel_download")]]
    )

def retry_keyboard(url):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Retry 🔄", callback_data=f"retry|{url}")]]
    )

def video_action_keyboard(file_id, chat_id, message_id):
    # Button to share the video link & delete source message
    share_url = f"https://t.me/{chat_id}?start=video_{message_id}"
    buttons = [
        [
            InlineKeyboardButton("Share Video 🔗", switch_inline_query=f"video_{message_id}"),
            InlineKeyboardButton("Delete Source ❌", callback_data=f"delete_source|{chat_id}|{message_id}")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

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

def download_with_ytdlp(url, download_dir="/tmp", message=None, user_id=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message and user_id in ongoing_downloads:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                # Update progress in the event loop
                asyncio.run_coroutine_threadsafe(
                    progress_callback(downloaded, total, message, "Downloading"),
                    loop
                )
        elif d['status'] == 'finished':
            pass

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

async def progress_callback(current, total, message: Message, action="Downloading"):
    try:
        progress_text = make_progress_bar(current, total)
        text = f"{action}: {progress_text}"
        await message.edit_text(text, reply_markup=cancel_keyboard())
    except Exception:
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

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except Exception:
        pass

async def auto_download_handler(bot: Client, message: Message, url=None):
    user_id = message.from_user.id
    urls = [url] if url else message.text.strip().split()
    valid_urls = [u for u in urls if u.lower().startswith("http")]
    if not valid_urls:
        await message.reply_text("No valid links detected.", reply_markup=main_menu_keyboard())
        return

    for url in valid_urls:
        if user_id not in ongoing_downloads:
            # User cancelled download
            return

        filepath = None
        try:
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            processing = await message.reply_text(f"Downloading from:\n{url}", reply_markup=cancel_keyboard())

            with sqlite3.connect(DB_FILE) as db:
                db.execute("INSERT INTO downloads (user_id, url, status, filepath, timestamp) VALUES (?, ?, ?, ?, ?)", (
                    user_id, url, "downloading", "", datetime.datetime.now().isoformat()
                ))
                db.commit()

            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
            else:
                ongoing_downloads[user_id] = asyncio.current_task()
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, user_id)
                ongoing_downloads.pop(user_id, None)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = (
                "**\u26a0\ufe0f IMPORTANT NOTICE \u26a0\ufe0f**\n\n"
                "This video will be **automatically deleted in 5 minutes** due to copyright policies.\n"
                "Please **forward** it to your **Saved Messages** or any private chat to keep a copy.\n\n"
                f"**Source:** [Click to open]({url})"
            )

            upload_msg = await processing.edit_text("Uploading...")
            thumb = generate_thumbnail(filepath)

            if ext.lower() in VIDEO_EXTENSIONS:
                sent = await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    reply_to_message_id=message.id,
                    supports_streaming=True,
                    reply_markup=video_action_keyboard(message.chat.username or "", message.chat.id, message.message_id)
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
                    "done", filepath, user_id, url
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

            if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
                alert = (
                    f"\u26a0\ufe0f **Porn link detected**\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Link:** {url}"
                )
                await bot.send_message(ADMIN_ID, alert)

        except asyncio.CancelledError:
            await message.reply_text("Download canceled by user.", reply_markup=main_menu_keyboard())
            ongoing_downloads.pop(user_id, None)
            return

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue

        except Exception as e:
            traceback.print_exc()
            await message.reply_text(
                f"\u274c Failed to download:\n{url}\n\n**{e}**",
                reply_markup=retry_keyboard(url)
            )

        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except Exception:
                pass

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def text_handler(bot: Client, message: Message):
    user_id = message.from_user.id
    ongoing_downloads[user_id] = None
    await auto_download_handler(bot, message)

@Client.on_callback_query()
async def callback_handler(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "help":
        await query.message.edit_text(
            "Send me a direct video or file link (YouTube, Google Drive, MEGA, etc.) and I will download & upload it.\n\n"
            "Videos are deleted after 5 minutes.\n"
            "Admins can resume incomplete downloads via the button.\n"
            "Use /start to return to main menu.",
            reply_markup=start_keyboard(user_id)
        )
        await query.answer()

    elif data == "resume":
        if user_id == ADMIN_ID:
            await query.answer("Resuming incomplete downloads...", show_alert=True)
            # Implement resume_incomplete_downloads function if needed
            await query.message.edit_text("Resume started.", reply_markup=start_keyboard(user_id))
        else:
            await query.answer("You are not authorized to do this.", show_alert=True)

    elif data == "cancel_download":
        task = ongoing_downloads.get(user_id)
        if task and not task.done():
            task.cancel()
            await query.answer("Download canceled.")
            await query.message.edit_text("Download canceled by user.", reply_markup=start_keyboard(user_id))
            ongoing_downloads.pop(user_id, None)
        else:
            await query.answer("No active download to cancel.", show_alert=True)

    elif data.startswith("retry|"):
        retry_url = data.split("|", 1)[1]
        await query.answer("Retrying download...")
        await auto_download_handler(bot, query.message, retry_url)

    elif data.startswith("delete_source|"):
        # Format: delete_source|chat_id|message_id
        try:
            _, chat_id_str, message_id_str = data.split("|")
            chat_id = int(chat_id_str)
            message_id = int(message_id_str)
            await bot.delete_messages(chat_id, message_id)
            await query.answer("Source message deleted.")
        except Exception as e:
            await query.answer(f"Failed to delete source: {e}", show_alert=True)

if __name__ == "__main__":
    # Replace these with your own values or load from config.py
    API_ID = 1234567
    API_HASH = "your_api_hash"
    BOT_TOKEN = "your_bot_token"

    app = Client("downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    app.run()