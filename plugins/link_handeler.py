import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import gradio as gr
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
queue = asyncio.Queue()

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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass

async def process_queue(bot: Client):
    while True:
        message = await queue.get()
        await handle_download(bot, message)
        queue.task_done()

async def handle_download(bot: Client, message: Message):
    urls = message.text.strip().split()
    user = message.from_user

    try:
        notice = await message.reply_text("Analyzing link(s)...")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        notice = await message.reply_text("Analyzing link(s)...")

    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await notice.edit("No valid links detected.")

    await notice.edit(f"Found {len(valid_urls)} link(s). Processing...")

    for idx, url in enumerate(valid_urls):
        filepath = None
        try:
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            processing = await message.reply_text(
                f"Queue Position: {idx+1}/{len(valid_urls)}\nDownloading from:\n{url}",
                reply_to_message_id=message.id
            )

            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
            else:
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing)

            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")

            ext = os.path.splitext(filepath)[1]
            caption = (
                "**⚠️ IMPORTANT NOTICE ⚠️**\n\n"
                "This video will be **automatically deleted in 5 minutes** due to copyright policies.\n"
                "Please **forward** it to your **Saved Messages** or any private chat to keep a copy.\n\n"
                f"**Source:** [Click to open]({url})"
            )

            thumb = generate_thumbnail(filepath)

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("Forward to Saved Messages", switch_inline_query=filepath)],
                [InlineKeyboardButton("Open Source Link", url=url)],
                [InlineKeyboardButton("Delete Now", callback_data=f"delete_{message.id}")]
            ])

            upload_msg = await processing.edit("Uploading...")

            if ext.lower() in VIDEO_EXTENSIONS:
                sent = await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    reply_markup=buttons,
                    reply_to_message_id=message.id
                )
            else:
                sent = await message.reply_document(
                    document=filepath,
                    caption=caption,
                    reply_markup=buttons,
                    reply_to_message_id=message.id
                )

            await upload_msg.delete()
            asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

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
            await bot.send_document(LOG_CHANNEL, document=filepath, caption=log_text)

            if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
                alert = (
                    f"⚠️ **Porn link detected**\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Link:** {url}"
                )
                await bot.send_message(ADMIN_ID, alert)

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

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "panel"]))
async def queue_download(bot: Client, message: Message):
    await message.reply_text("Added to queue...")
    await queue.put(message)

@Client.on_message(filters.command("panel") & filters.private)
async def launch_panel(bot: Client, message: Message):
    async def gradio_interface(link):
        try:
            filename, _ = await asyncio.to_thread(download_with_ytdlp, link)
            return f"Downloaded: {filename}"
        except Exception as e:
            return str(e)

    iface = gr.Interface(fn=gradio_interface, inputs="text", outputs="text", title="Downloader Panel")
    iface.launch(share=True)
    await message.reply_text("Web panel launched.")

@Client.on_callback_query()
async def delete_callback(bot, query):
    if query.data.startswith("delete_"):
        try:
            await bot.delete_messages(query.message.chat.id, query.message.id)
            await query.answer("Deleted")
        except:
            await query.answer("Failed to delete", show_alert=True)

# Start queue processor
from pyrogram import Client, idle
import asyncio

app = Client("downloader")

@app.on_message(filters.command("start"))
async def start_msg(bot, message):
    await message.reply_text("Welcome to Downloader Bot! Send a link to begin.")

async def main():
    await app.start()
    asyncio.create_task(process_queue(app))  # আপনার process_queue ফাংশনটি অ্যাসিনক্রোনাস ফাংশন হবে
    await idle()  # Pyrogram এর idle যা বটকে চালু রাখে

asyncio.run(main())