import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMINS
from tqdm import tqdm
import random
import string
import subprocess

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
USER_QUOTA = {}
MAX_DAILY_QUOTA = 2 * 1024 * 1024 * 1024  # 2 GB

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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return None

def build_ydl_opts(url, download_dir="/tmp", quality="best"):
    return {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": f"{quality}[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "progress_hooks": [progress_hook]
    }

def progress_hook(d):
    if d['status'] == 'downloading':
        print(f"[Downloading] {d['_percent_str']} of {d['_total_bytes_str']} at {d['_speed_str']}")
    elif d['status'] == 'finished':
        print("[Download complete]", d['filename'])

def download_with_ytdlp(url, quality="best", download_dir="/tmp"):
    ydl_opts = build_ydl_opts(url, download_dir, quality)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

def generate_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))

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

async def check_internet():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.google.com') as response:
                return response.status == 200
    except:
        return False

async def download_with_progress_bar(url, download_dir="/tmp"):
    file_size = 0
    with tqdm(unit='B', unit_scale=True, miniters=1, desc=url) as t:
        ydl_opts = build_ydl_opts(url, download_dir)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.add_progress_hook(lambda d: t.update(d.get('downloaded_bytes', 0) - file_size))
            info = ydl.extract_info(url, download=True)
            file_size = info['filesize'] if 'filesize' in info else 0
            return ydl.prepare_filename(info), info

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def auto_download_handler(bot: Client, message: Message):
    user = message.from_user
    uid = user.id

    if uid not in USER_QUOTA:
        USER_QUOTA[uid] = 0

    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http")]

    if not valid_urls:
        return await message.reply("No valid links detected.")

    await message.reply(f"Found {len(valid_urls)} link(s). Starting download...")

    if not await check_internet():
        return await message.reply("No internet connection detected. Please try again later.")

    for url in valid_urls:
        filepath = None
        try:
            await asyncio.sleep(1)
            notice = await message.reply(f"Downloading from:\n\n{url}")

            filepath, info = await download_with_progress_bar(url)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            file_size = os.path.getsize(filepath)
            if USER_QUOTA[uid] + file_size > MAX_DAILY_QUOTA:
                await message.reply("You have reached your daily quota limit.")
                os.remove(filepath)
                continue

            ext = os.path.splitext(filepath)[1]
            caption = f"**Downloaded from:**\n{url}"

            uploading = await message.reply("Uploading...")

            thumb = generate_thumbnail(filepath) if ext.lower() in VIDEO_EXTENSIONS else None

            if ext.lower() in VIDEO_EXTENSIONS:
                await message.reply_video(video=filepath, caption=caption, thumb=thumb)
            else:
                await message.reply_document(document=filepath, caption=caption)

            await uploading.delete()

            USER_QUOTA[uid] += file_size

            log_text = (
                f"**New Download Event**\n\n"
                f"**User:** {user.mention} (`{uid}`)\n"
                f"**Link:** `{url}`\n"
                f"**File Name:** `{os.path.basename(filepath)}`\n"
                f"**Size:** `{format_bytes(file_size)}`\n"
                f"**Type:** `{'Video' if ext.lower() in VIDEO_EXTENSIONS else 'Document'}`\n"
                f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )

            await bot.send_message(LOG_CHANNEL, log_text)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback_text = traceback.format_exc()
            await message.reply(f"❌ Failed to download: {url}\n\n**Error:** {e}")
            for admin in ADMINS:
                try:
                    await bot.send_message(admin, f"Error on {url}:\n\n{traceback_text}")
                except:
                    pass
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass

@Client.on_message(filters.private & filters.command("help"))
async def help_command(bot: Client, message: Message):
    help_text = """Welcome to the downloader bot! Here's how you can use it:

- Simply send a valid URL to download.
- The bot will download the file for you.
- You can download up to 2GB of data daily.

Supported file types: video, document, playlist.
"""
    await message.reply(help_text)