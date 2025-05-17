import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".aac", ".opus", ".wav", ".flac"]

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
    except:
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
                except:
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

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies/youtube.txt"
    return None

def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }

def download_with_ytdlp(url, download_dir="/tmp", message=None, format_code=None):
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
        "format": format_code or "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook],
        "postprocessors": [],
    }

    if format_code and format_code.startswith("bestaudio"):
        # Add postprocessor to extract audio only if requested format is audio only
        ydl_opts["postprocessors"].append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        })

    cookie_file = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # If audio extracted, extension changes to mp3
        if ydl_opts["postprocessors"]:
            filename = os.path.splitext(filename)[0] + ".mp3"
        return filename, info

async def extract_audio_from_video(video_path, output_path="/tmp/audio.mp3"):
    import subprocess
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-ab", "192k", "-ar", "44100", "-y", output_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        if os.path.exists(output_path):
            return output_path
        return None
    except:
        return None

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    if message.from_user.is_bot:
        return

    if message.reply_to_message:
        return

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

            # Check if URL is audio-only source by yt-dlp info extraction (try quickly)
            # If audio only, don't show buttons (direct download)
            def is_audio_only_url(u):
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "format": "bestaudio/best",
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(u, download=False)
                        if info.get('formats'):
                            for f in info['formats']:
                                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                                    return True
                    return False
                except:
                    return False

            audio_only_link = False
            try:
                audio_only_link = await asyncio.to_thread(is_audio_only_url, url)
            except:
                audio_only_link = False

            if audio_only_link:
                # Directly download audio only, no buttons needed
                processing = await message.reply_text(f"Downloading audio from:\n{url}", reply_to_message_id=message.id)
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, "bestaudio/best")
                if not os.path.exists(filepath):
                    raise Exception("Download failed or file not found.")

                ext = os.path.splitext(filepath)[1]
                caption = (
                    "**⚠️ This file will be automatically deleted in 5 minutes!**\n\n"
                    "Please **save this file** by forwarding it to your **Saved Messages** or any private chat.\n\n"
                    f"[Source Link]({url})"
                )

                upload_msg = await processing.edit("Uploading...")

                thumb = generate_thumbnail(filepath)
                if not thumb:
                    # Use default audio thumbnail
                    thumb = "default_audio_thumb.jpg"  # You must have this file or adjust accordingly

                sent = await message.reply_audio(
                    audio=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    reply_to_message_id=message.id,
                )
                await upload_msg.delete()
                asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

                user = message.from_user
                file_size = format_bytes(os.path.getsize(filepath))
                log_text = (
                    f"**New Download Event**\n\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Link:** `{url}`\n"
                    f"**File Name:** `{os.path.basename(filepath)}`\n"
                    f"**Size:** `{file_size}`\n"
                    f"**Type:** `Audio`\n"
                    f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )

                await bot.send_audio(
                    LOG_CHANNEL,
                    audio=filepath,
                    caption=log_text,
                    thumb=thumb if thumb else None,
                )

                if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
                    alert = (
                        f"⚠️ **Porn link detected**\n"
                        f"**User:** {user.mention} (`{user.id}`)\n"
                        f"**Link:** {url}"
                    )
                    await bot.send_message(ADMIN_ID, alert)
                continue

            # Show buttons to choose video or audio
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Download Video", callback_data=f"dl_video|{url}|{message.id}"),
                        InlineKeyboardButton("Download Audio", callback_data=f"dl_audio|{url}|{message.id}")
                    ]
                ]
            )
            await message.reply_text(
                f"Choose download format for:\n{url}",
                reply_markup=keyboard,
                reply_to_message_id=message.id
            )

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Failed to process link:\n{url}\n\n**{e}**")
        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass

async def process_download(bot: Client, url: str, message: Message, download_type: str):
    filepath = None
    try:
        if is_google_drive_link(url):
            url = fix_google_drive_url(url)

        processing = await message.reply_text(f"Downloading {download_type} from:\n{url}", reply_to_message_id=message.id)

        if is_mega_link(url):
            filepath, info = await asyncio.to_thread(download_mega_file, url)
            filepath = os.path.join("/tmp", filepath)
        else:
            if download_type == "audio":
                # Download bestaudio format and extract if needed
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, "bestaudio/best")
                # If extension not audio, extract audio from video
                ext = os.path.splitext(filepath)[1].lower()
                if ext not in AUDIO_EXTENSIONS:
                    audio_path = await extract_audio_from_video(filepath)
                    if audio_path:
                        # replace filepath with audio extracted path
                        try:
                            os.remove(filepath)
                        except:
                            pass
                        filepath = audio_path
            else:
                # video download
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, None)

        if not os.path.exists(filepath):
            raise Exception("Download failed or file not found.")

        ext = os.path.splitext(filepath)[1].lower()
        caption = (
            "**⚠️ This file will be automatically deleted in 5 minutes!**\n\n"
            "Please **save this file** by forwarding it to your **Saved Messages** or any private chat.\n\n"
            f"[Source Link]({url})"
        )

        upload_msg = await processing.edit("Uploading...")

        thumb = generate_thumbnail(filepath)
        if download_type == "audio":
            if not thumb:
                # Use default audio thumbnail
                thumb = "default_audio_thumb.jpg"  # Adjust as per your default thumb file

            sent = await message.reply_audio(
                audio=filepath,
                caption=caption,
                thumb=thumb if thumb else None,
                reply_to_message_id=message.id,
            )
        else:
            buttons = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔗 Source Link", url=url)],
                    [InlineKeyboardButton("❌ Delete Now", callback_data=f"delete_{message.id}")]
                ]
            )
            sent = await message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if thumb else None,
                reply_to_message_id=message.id,
                supports_streaming=True,
                reply_markup=buttons
            )

        await upload_msg.delete()
        asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

        user = message.from_user
        file_size = format_bytes(os.path.getsize(filepath))
        log_text = (
            f"**New Download Event**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File Name:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{file_size}`\n"
            f"**Type:** `{download_type.capitalize()}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )

        if download_type == "audio":
            await bot.send_audio(
                LOG_CHANNEL,
                audio=filepath,
                caption=log_text,
                thumb=thumb if thumb else None,
            )
        else:
            await bot.send_video(
                LOG_CHANNEL,
                video=filepath,
                caption=log_text,
                thumb=thumb if thumb else None,
                supports_streaming=True
            )

        if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
            alert = (
                f"⚠️ **Porn link detected**\n"
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Link:** {url}"
            )
            await bot.send_message(ADMIN_ID, alert)

    except FloodWait as e:
        await asyncio.sleep(e.value)
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

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass

@Client.on_callback_query()
async def handle_callback(bot, callback_query):
    data = callback_query.data
    if data.startswith("delete_"):
        try:
            await bot.delete_messages(callback_query.message.chat.id, callback_query.message.id)
            await callback_query.answer("Deleted successfully.", show_alert=False)
        except:
            await callback_query.answer("Failed to delete message.", show_alert=True)
    elif data.startswith("dl_video") or data.startswith("dl_audio"):
        try:
            parts = data.split("|")
            if len(parts) != 3:
                await callback_query.answer("Invalid data.", show_alert=True)
                return
            dl_type, url, orig_msg_id = parts[0][3:], parts[1], int(parts[2])
            orig_msg = await bot.get_messages(callback_query.message.chat.id, orig_msg_id)
            await callback_query.answer(f"Starting {dl_type} download...", show_alert=False)
            await process_download(bot, url, orig_msg, dl_type)
            await callback_query.message.delete()
        except Exception as e:
            await callback_query.answer(f"Error: {e}", show_alert=True)