import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import math
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
MAX_PART_SIZE = int(1.5 * 1024 * 1024 * 1024)  # 1.5 GB

def is_social_media_url(url: str) -> bool:
    social_domains = [
        "youtube.com", "youtu.be",
        "facebook.com", "fb.watch",
        "instagram.com", "tiktok.com",
        "twitter.com", "vimeo.com",
        "dailymotion.com"
    ]
    return any(domain in url.lower() for domain in social_domains)

def download_with_ytdlp(url, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def split_video_ffmpeg(input_file, part_size_bytes, output_dir="/tmp"):
    total_size = os.path.getsize(input_file)
    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_file
    ]
    duration = float(subprocess.check_output(duration_cmd).strip())
    total_parts = math.ceil(total_size / part_size_bytes)
    duration_per_part = duration / total_parts

    output_paths = []
    for i in range(total_parts):
        start_time = i * duration_per_part
        output_path = os.path.join(output_dir, f"split_part_{i + 1}.mp4")
        cmd = [
            "ffmpeg", "-ss", str(start_time), "-i", input_file,
            "-t", str(duration_per_part), "-c", "copy", output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            output_paths.append(output_path)
    return output_paths

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

async def download_part(session, url, start, end, part_path):
    headers = {
        "Range": f"bytes={start}-{end}",
        "User-Agent": "Mozilla/5.0",
        "Referer": url
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status in (200, 206):
            with open(part_path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        else:
            raise Exception(f"HTTP status {resp.status}")

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

            if is_social_media_url(url):
                processing = await message.reply_text(f"Downloading from:\n{url}")
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url)
                if not os.path.exists(filepath):
                    raise Exception("Download failed or file not found.")

                caption = f"**Downloaded from:**\n{url}"
                thumb = generate_thumbnail(filepath)
                size = os.path.getsize(filepath)

                await processing.edit("Uploading...")

                if size > MAX_PART_SIZE:
                    parts = await asyncio.to_thread(split_video_ffmpeg, filepath, MAX_PART_SIZE)
                    for idx, part in enumerate(parts, start=1):
                        await message.reply_video(
                            video=part,
                            caption=f"{caption}\n**Part {idx}**",
                            thumb=thumb if thumb else None
                        )
                        os.remove(part)
                else:
                    await message.reply_video(
                        video=filepath,
                        caption=caption,
                        thumb=thumb if thumb else None
                    )

                if os.path.exists(filepath):
                    os.remove(filepath)
                if thumb and os.path.exists(thumb):
                    os.remove(thumb)
                await processing.delete()

            else:
                processing = await message.reply_text(f"Fetching file info for direct link:\n{url}")

                async with aiohttp.ClientSession() as session:
                    async with session.head(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status >= 400:
                            raise Exception(f"Unable to access file. HTTP status: {resp.status}")
                        size = int(resp.headers.get("Content-Length", 0))
                        if size == 0:
                            raise Exception("Cannot determine file size.")

                    total_parts = math.ceil(size / MAX_PART_SIZE)
                    await processing.edit(f"File size: {format_bytes(size)}. Splitting into {total_parts} part(s).")

                    for i in range(total_parts):
                        start = i * MAX_PART_SIZE
                        end = min(start + MAX_PART_SIZE - 1, size - 1)
                        part_path = f"/tmp/part_{i+1}.mp4"
                        await download_part(session, url, start, end, part_path)
                        await message.reply_video(part_path, caption=f"**Direct Link Part {i+1} of {total_parts}**")
                        os.remove(part_path)

                await processing.delete()

            # Logging
            user = message.from_user
            log_text = (
                f"**New Download Event**\n\n"
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Link:** `{url}`\n"
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
                await auto_cleanup()
            except:
                pass