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
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

def download_with_ytdlp(url, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

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

def split_file(file_path, part_size=MAX_FILE_SIZE):
    part_files = []
    base_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        i = 1
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            part_path = f"{file_path}.part{i}"
            with open(part_path, "wb") as pf:
                pf.write(chunk)
            part_files.append(part_path)
            i += 1
    return part_files

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
            await notice.delete()
            processing = await message.reply_text(f"Downloading from:\n{url}")
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = f"**Downloaded from:**\n{url}"

            await processing.delete()
            uploading = await message.reply_text("Uploading...")

            # যদি ফাইল বড় হয়
            if os.path.getsize(filepath) > MAX_FILE_SIZE:
                part_files = await asyncio.to_thread(split_file, filepath)
                for idx, part in enumerate(part_files, 1):
                    part_caption = f"{caption}\n**Part {idx}/{len(part_files)}**"
                    if ext.lower() in VIDEO_EXTENSIONS:
                        await message.reply_video(
                            video=part,
                            caption=part_caption
                        )
                    else:
                        await message.reply_document(
                            document=part,
                            caption=part_caption
                        )
                    os.remove(part)
            else:
                if ext.lower() in VIDEO_EXTENSIONS:
                    thumb = generate_thumbnail(filepath)
                    await message.reply_video(
                        video=filepath,
                        caption=caption,
                        thumb=thumb if thumb else None
                    )
                else:
                    await message.reply_document(
                        document=filepath,
                        caption=caption
                    )

            await uploading.delete()

            # Log to admin channel
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
            await message.reply_text(f"❌ Failed to download:\n{url}\n\n**{e}**")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass