import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL

MAX_PART_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB

def is_social_media_url(url: str) -> bool:
    social_domains = [
        "youtube.com", "youtu.be", "facebook.com", "fb.watch",
        "instagram.com", "tiktok.com", "twitter.com",
        "vimeo.com", "dailymotion.com"
    ]
    return any(domain in url.lower() for domain in social_domains)

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

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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
        try:
            await notice.delete()

            if is_social_media_url(url):
                processing = await message.reply_text(f"Downloading from:\n{url}")
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url)
                if not os.path.exists(filepath):
                    raise Exception("Download failed or file not found.")

                thumb = generate_thumbnail(filepath)
                size = os.path.getsize(filepath)

                if size > MAX_PART_SIZE:
                    raise Exception("Video too large. Please send a smaller resolution link.")

                await message.reply_video(
                    video=filepath,
                    caption=f"**Downloaded from:**\n{url}",
                    thumb=thumb if thumb else None
                )

                os.remove(filepath)
                if thumb and os.path.exists(thumb):
                    os.remove(thumb)
                await processing.delete()

            else:
                processing = await message.reply_text(f"Fetching file info for direct link:\n{url}")
                filename = "/tmp/downloaded_video.mkv"
                converted = "/tmp/converted_video.mp4"

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status >= 400:
                            raise Exception(f"Unable to access file. HTTP status: {resp.status}")
                        with open(filename, "wb") as f:
                            while True:
                                chunk = await resp.content.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)

                await processing.edit("Converting to MP4 for Telegram compatibility...")

                cmd = [
                    "ffmpeg", "-i", filename,
                    "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23",
                    "-movflags", "+faststart",
                    converted
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if not os.path.exists(converted):
                    raise Exception("Conversion failed.")

                await message.reply_video(
                    video=converted,
                    caption=f"**Downloaded from:**\n{url}"
                )

                os.remove(filename)
                os.remove(converted)
                await processing.delete()

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