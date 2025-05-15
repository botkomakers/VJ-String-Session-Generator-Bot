import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import math
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
MAX_PART_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes


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


def split_file(filepath, part_size=MAX_PART_SIZE):
    """Split file into parts of <= part_size bytes."""
    file_size = os.path.getsize(filepath)
    if file_size <= part_size:
        return [filepath]
    
    parts = []
    total_parts = math.ceil(file_size / part_size)
    base_name, ext = os.path.splitext(filepath)
    
    with open(filepath, "rb") as f:
        for i in range(total_parts):
            part_path = f"{base_name}_part{i+1}{ext}"
            with open(part_path, "wb") as pf:
                chunk = f.read(part_size)
                pf.write(chunk)
            parts.append(part_path)
    return parts


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

            # Split file if bigger than MAX_PART_SIZE
            parts = split_file(filepath, MAX_PART_SIZE)

            await processing.delete()  

            for idx, part_path in enumerate(parts):
                uploading = await message.reply_text(f"Uploading part {idx+1} of {len(parts)}...")
                ext = os.path.splitext(part_path)[1]  
                caption = f"**Downloaded from:**\n{url}\n**Part:** {idx+1} of {len(parts)}"  

                if ext.lower() in VIDEO_EXTENSIONS:  
                    thumb = generate_thumbnail(part_path)  
                    await message.reply_video(  
                        video=part_path,  
                        caption=caption,  
                        thumb=thumb if thumb else None  
                    )  
                else:  
                    await message.reply_document(  
                        document=part_path,  
                        caption=caption  
                    )  

                await uploading.delete()  
                # Remove uploaded part
                os.remove(part_path)

            # Remove original file after all parts uploaded
            if os.path.exists(filepath):
                os.remove(filepath)

            await auto_cleanup()  

            # Log to admin channel  
            user = message.from_user  
            file_size = format_bytes(os.path.getsize(filepath) if os.path.exists(filepath) else 0)  
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