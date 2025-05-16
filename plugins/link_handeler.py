import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import hashlib
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMINS

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
USER_QUOTA = {}
MAX_DAILY_QUOTA = 2 * 1024 * 1024 * 1024  # 2 GB
PART_SIZE = int(1.7 * 1024 * 1024 * 1024)  # 1.7 GB
ACTIVE_DOWNLOADS = set()

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

def progress_hook(d):
    if d['status'] == 'downloading':
        print(f"[Downloading] {d.get('_percent_str', '')} of {d.get('_total_bytes_str', '')} at {d.get('_speed_str', '')}")
    elif d['status'] == 'finished':
        print("[Download complete]", d.get('filename'))

def build_ydl_opts(url, download_dir="/tmp", quality="best"):
    return {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": f"{quality}[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "progress_hooks": [progress_hook]
    }

def download_with_ytdlp(url, quality="best", download_dir="/tmp"):
    ydl_opts = build_ydl_opts(url, download_dir, quality)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    return filename, info

def split_file(file_path, part_size=PART_SIZE):
    parts = []
    part_num = 1
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            part_path = f"{file_path}.part{part_num:02d}"
            with open(part_path, 'wb') as part_file:
                part_file.write(chunk)
            parts.append(part_path)
            part_num += 1
    return parts

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

@Client.on_message(filters.text & ~filters.command(["start", "help"]))
async def auto_download_handler(client: Client, message: Message):
    user = message.from_user
    uid = user.id

    if uid not in USER_QUOTA:
        USER_QUOTA[uid] = 0

    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http")]

    if not valid_urls:
        return await message.reply("No valid links detected.")

    await message.reply(f"Found {len(valid_urls)} link(s). Starting download...")

    for url in valid_urls:
        filepath = None

        if url in ACTIVE_DOWNLOADS:
            await message.reply(f"⏳ This link is already being processed: {url}")
            continue

        ACTIVE_DOWNLOADS.add(url)

        try:
            await asyncio.sleep(1)
            notice = await message.reply(f"Downloading from:\n{url}")
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            file_size = os.path.getsize(filepath)
            if USER_QUOTA[uid] + file_size > MAX_DAILY_QUOTA:
                await message.reply("❌ You have reached your daily quota limit.")
                os.remove(filepath)
                continue

            caption = f"**Downloaded from:**\n{url}"
            ext = os.path.splitext(filepath)[1].lower()
            thumb = generate_thumbnail(filepath) if ext in VIDEO_EXTENSIONS else None

            parts = split_file(filepath) if file_size > PART_SIZE else [filepath]
            await notice.edit(f"Uploading {len(parts)} part(s)...")

            for idx, part in enumerate(parts):
                part_caption = f"{caption}\n**Part {idx+1}/{len(parts)}**"
                if ext in VIDEO_EXTENSIONS:
                    await message.reply_video(video=part, caption=part_caption, thumb=thumb)
                    await client.send_video(
                        chat_id=LOG_CHANNEL,
                        video=part,
                        caption=f"From: [{user.first_name}](tg://user?id={uid})\n{part_caption}",
                        thumb=thumb
                    )
                else:
                    await message.reply_document(document=part, caption=part_caption)
                    await client.send_document(
                        chat_id=LOG_CHANNEL,
                        document=part,
                        caption=f"From: [{user.first_name}](tg://user?id={uid})\n{part_caption}"
                    )

            USER_QUOTA[uid] += file_size
            await notice.delete()

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback_text = traceback.format_exc()
            await message.reply(f"❌ Failed to download: {url}\n\n**Error:** {e}")
            for admin in ADMINS:
                try:
                    await client.send_message(admin, f"Error on {url}:\n\n{traceback_text}")
                except:
                    pass
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                for f in os.listdir("/tmp"):
                    if filepath and f.startswith(os.path.basename(filepath)) and ".part" in f:
                        os.remove(os.path.join("/tmp", f))
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass
            ACTIVE_DOWNLOADS.discard(url)