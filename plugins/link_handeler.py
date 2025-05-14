import os
import asyncio
import time
import datetime
import traceback
import yt_dlp
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".mov", ".flv", ".avi"]

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def get_filename_from_info(info):
    return yt_dlp.utils.sanitize_filename(info.get("title", "video")) + ".mp4"

async def download_with_ytdlp(url, download_dir="/tmp"):
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

@Client.on_message(filters.private & filters.text & ~filters.command("start"))
async def social_link_handler(bot: Client, message: Message):
    urls = [u for u in message.text.strip().split() if u.startswith("http")]
    if not urls:
        return await message.reply("No valid links found.")

    processing = await message.reply("Analyzing link(s)...")

    for url in urls:
        try:
            await processing.edit(f"Downloading from:\n`{url}`")
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url)
            if not os.path.exists(filepath):
                raise Exception("Download failed.")

            caption = f"**Title:** {info.get('title')}\n**Source:** {url}"
            duration = int(info.get("duration", 0))
            width = info.get("width", 0)
            height = info.get("height", 0)

            await processing.edit("Uploading...")

            await message.reply_video(
                video=filepath,
                caption=caption,
                duration=duration if duration else None,
                width=width if width else None,
                height=height if height else None
            )

            # Log to LOG_CHANNEL
            if LOG_CHANNEL:
                file_size = format_bytes(os.path.getsize(filepath))
                user = message.from_user
                log_msg = (
                    f"**New Video Downloaded**\n\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**URL:** `{url}`\n"
                    f"**File:** `{os.path.basename(filepath)}`\n"
                    f"**Size:** `{file_size}`\n"
                    f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                try:
                    await bot.send_message(LOG_CHANNEL, log_msg)
                except Exception:
                    pass

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            traceback.print_exc()
            await message.reply(f"❌ Failed to download:\n`{url}`\n\n**{e}**")
        finally:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

    await processing.delete()