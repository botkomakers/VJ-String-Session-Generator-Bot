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

def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    return None

def download_with_ytdlp(url, download_dir="/tmp", message=None):
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

    cookie_file = get_cookie_file(url)

    ydl_opts = {  
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),  
        "format": "best[ext=mp4]/best",  
        "quiet": True,  
        "no_warnings": True,  
        "noplaylist": True,  
        "progress_hooks": [hook]
    }

    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
        info = ydl.extract_info(url, download=True)  
        filename = ydl.prepare_filename(info)  
        return filename, info

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
            if is_google_drive_link(url):  
                url = fix_google_drive_url(url)  

            await notice.delete()  
            processing = await message.reply_text(f"Downloading from:\n{url}", reply_to_message_id=message.id)  

            if is_mega_link(url):  
                filepath, info = await asyncio.to_thread(download_mega_file, url)  
                filepath = os.path.join("/tmp", filepath)  
            else:  
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing)  

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

            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔗 Source Link", url=url)
                ],
                [
                    InlineKeyboardButton("❌ Delete Now", callback_data=f"delete_{message.id}")
                ]
            ])

            if ext.lower() in VIDEO_EXTENSIONS:  
                sent = await message.reply_video(  
                    video=filepath,  
                    caption=caption,  
                    thumb=thumb if thumb else None,  
                    reply_to_message_id=message.id,  
                    supports_streaming=True,
                    reply_markup=buttons
                )  
            else:  
                sent = await message.reply_document(  
                    document=filepath,  
                    caption=caption,  
                    reply_to_message_id=message.id,
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
                f"**Type:** `{'Video' if ext.lower() in VIDEO_EXTENSIONS else 'Document'}`\n"  
                f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"  
            )  

            if ext.lower() in VIDEO_EXTENSIONS:  
                await bot.send_video(  
                    LOG_CHANNEL,  
                    video=filepath,  
                    caption=log_text,  
                    thumb=thumb if thumb else None,  
                    supports_streaming=True  
                )  
            else:  
                await bot.send_document(LOG_CHANNEL, document=filepath, caption=log_text)  

            if any(x in url.lower() for x in ["porn", "sex", "xxx"]):  
                alert = (  
                    f"⚠️ **Porn link detected**\n"  
                    f"**User:** {user.mention} (`{user.id}`)\n"  
                    f"**Link:** {url}"  
                )  
                await bot.send_message(ADMIN_ID, alert)  

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