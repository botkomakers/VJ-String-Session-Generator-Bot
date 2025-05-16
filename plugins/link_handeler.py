import os
import asyncio
import time
import datetime
import subprocess
import traceback
from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
import yt_dlp

from config import LOG_CHANNEL

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
TELEGRAM_MAX_SIZE = 2 * 1024 * 1024 * 1024
SAFETY_MARGIN = 50 * 1024 * 1024
MAX_UPLOAD_SIZE = TELEGRAM_MAX_SIZE - SAFETY_MARGIN

DOWNLOAD_BASE_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_BASE_DIR, exist_ok=True)

MAX_CONCURRENT_TASKS = 3
sem = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

def format_bytes(size: int) -> str:
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_thumbnail(file_path: str, output_thumb: str = None) -> str | None:
    if not output_thumb:
        output_thumb = os.path.join(os.path.dirname(file_path), "thumb.jpg")
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        if os.path.exists(output_thumb):
            return output_thumb
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
    return None

async def auto_cleanup(path: str = DOWNLOAD_BASE_DIR, max_age: int = 900):
    now = time.time()
    try:
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            if os.path.isfile(file_path):
                age = now - os.path.getmtime(file_path)
                if age > max_age:
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
    except Exception as e:
        print(f"Cleanup error: {e}")

async def split_video(filepath: str) -> list[str]:
    chunk_size = MAX_UPLOAD_SIZE
    file_size = os.path.getsize(filepath)
    if file_size <= chunk_size:
        return [filepath]

    base_name, ext = os.path.splitext(filepath)
    output_files = []

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        total_duration = float(result.stdout.strip())
    except Exception:
        total_duration = None

    total_parts = (file_size // chunk_size) + 1
    print(f"Splitting file into {total_parts} parts...")

    if not total_duration:
        return [filepath]

    duration_per_part = total_duration / total_parts

    for i in range(total_parts):
        part_path = f"{base_name}_part{i + 1}{ext}"
        start_time = duration_per_part * i

        cmd = [
            "ffmpeg",
            "-i", filepath,
            "-ss", str(start_time),
            "-t", str(duration_per_part),
            "-c", "copy",
            "-y",
            part_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(part_path):
                output_files.append(part_path)
        except Exception as e:
            print(f"Failed to create part {i + 1}: {e}")
            for f in output_files:
                try:
                    os.remove(f)
                except:
                    pass
            return [filepath]

    return output_files

async def download_with_ytdlp(url: str, download_dir: str) -> tuple[str, dict]:
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36"
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

async def send_progress_message(message: Message, text: str):
    try:
        await message.edit(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.edit(text)
    except Exception:
        pass

@bot.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def handle_message(client, message: Message):
    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith("http")]

    if not valid_urls:
        return await message.reply_text("No valid URLs found in your message!")

    user_dir = os.path.join(DOWNLOAD_BASE_DIR, str(message.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    notice = await message.reply_text(f"Detected {len(valid_urls)} URL(s). Starting downloads...")

    async with sem:
        for url in valid_urls:
            filepath = None
            try:
                await send_progress_message(notice, f"Downloading:\n{url}")

                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, user_dir)

                if not os.path.exists(filepath):
                    raise Exception("Downloaded file not found!")

                file_size = os.path.getsize(filepath)

                if file_size > MAX_UPLOAD_SIZE:
                    await send_progress_message(notice, "File too large, splitting now...")
                    parts = await split_video(filepath)
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass

                    for part_file in parts:
                        part_size = os.path.getsize(part_file)
                        if part_size > MAX_UPLOAD_SIZE:
                            await send_progress_message(notice, f"Part file too large: {os.path.basename(part_file)}")
                            continue

                        ext = os.path.splitext(part_file)[1].lower()
                        caption = f"**Downloaded from:**\n{url}\n(part file)"

                        if ext in VIDEO_EXTENSIONS:
                            thumb = generate_thumbnail(part_file)
                            await message.reply_video(
                                video=part_file,
                                caption=caption,
                                thumb=thumb,
                                supports_streaming=True,
                            )
                        else:
                            await message.reply_document(
                                document=part_file,
                                caption=caption,
                            )
                        try:
                            os.remove(part_file)
                        except Exception:
                            pass
                else:
                    ext = os.path.splitext(filepath)[1].lower()
                    caption = f"**Downloaded from:**\n{url}"

                    await send_progress_message(notice, "Uploading to Telegram...")

                    if ext in VIDEO_EXTENSIONS:
                        thumb = generate_thumbnail(filepath)
                        await message.reply_video(
                            video=filepath,
                            caption=caption,
                            thumb=thumb,
                            supports_streaming=True,
                        )
                    else:
                        await message.reply_document(
                            document=filepath,
                            caption=caption,
                        )

                user = message.from_user
                log_msg = (
                    f"📥 **New Download**\n\n"
                    f"👤 User: {user.mention} (`{user.id}`)\n"
                    f"🔗 Link: `{url}`\n"
                    f"📁 File: `{os.path.basename(filepath)}`\n"
                    f"💾 Size: {format_bytes(file_size)}\n"
                    f"📅 Time: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                try:
                    await client.send_message(LOG_CHANNEL, log_msg)
                except Exception:
                    pass

            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except Exception as e:
                traceback.print_exc()
                await message.reply_text(f"❌ Failed to download:\n{url}\n\n**Error:** {e}")
            finally:
                try:
                    if filepath and os.path.exists(filepath):
                        os.remove(filepath)
                    thumb_path = os.path.join(user_dir, "thumb.jpg")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                    await auto_cleanup(user_dir)
                except Exception:
                    pass

    await notice.delete()

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "Welcome! Send me any video or playlist URL and I'll download it for you.\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - Get help info\n"
    )

@bot.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text(
        "Usage:\n"
        "Just send me video URLs.\n"
        "I will download and send back the video/document.\n"
        "Max file size ~1.95GB (due to Telegram limits).\n"
        "Supports many sites via yt-dlp.\n"
        "For issues contact admin."
    )