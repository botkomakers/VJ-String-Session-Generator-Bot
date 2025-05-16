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
from mega import Mega
from tqdm import tqdm
import threading

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

def download_with_ytdlp(url, download_dir="/tmp"):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

def download_mega_file(url, download_dir="/tmp"):
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }

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
        if os.path.exists(output_thumb):
            return output_thumb
        else:
            return None
    except Exception:
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
                except Exception:
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

def is_terabox_link(url):
    return "terabox.com" in url or "teraboxapp.com" in url

async def download_terabox_file(url, download_dir="/tmp"):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                text = await resp.text()

        import re
        from urllib.parse import unquote

        match = re.search(r'"downloadUrl":"(.*?)"', text)
        if not match:
            raise Exception("❌ ভিডিও লিংক খুঁজে পাওয়া যায়নি।")

        video_url = unquote(match.group(1).replace('\\u002F', '/'))

        filename = os.path.join(download_dir, f"terabox_{int(time.time())}.mp4")

        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as resp:
                total_size = int(resp.headers.get('Content-Length', 0))
                with open(filename, "wb") as f:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                        async for chunk in resp.content.iter_chunked(1024):
                            f.write(chunk)
                            pbar.update(len(chunk))

        return filename, {
            "title": os.path.basename(filename),
            "ext": "mp4"
        }

    except Exception as e:
        raise Exception(f"Terabox ডাউনলোড ব্যর্থ: {e}")

def multithreaded_download(url, filename, num_threads=4):
    import requests

    response = requests.head(url)
    file_size = int(response.headers.get('Content-Length', 0))
    part_size = file_size // num_threads

    def download_part(start, end, part_num):
        headers = {'Range': f'bytes={start}-{end}'}
        r = requests.get(url, headers=headers, stream=True)
        with open(f"{filename}.part{part_num}", 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

    threads = []
    for i in range(num_threads):
        start = part_size * i
        end = start + part_size - 1 if i < num_threads - 1 else file_size - 1
        t = threading.Thread(target=download_part, args=(start, end, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    with open(filename, 'wb') as outfile:
        for i in range(num_threads):
            with open(f"{filename}.part{i}", 'rb') as infile:
                outfile.write(infile.read())
            os.remove(f"{filename}.part{i}")

    return filename

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def auto_download_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    filepath = None
    try:
        notice = await message.reply_text("🔍 লিংক বিশ্লেষণ করা হচ্ছে...")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        notice = await message.reply_text("🔍 লিংক বিশ্লেষণ করা হচ্ছে...")

    valid_urls = [url for url in urls if url.lower().startswith("http")]
    if not valid_urls:
        return await notice.edit("❌ কোনো বৈধ লিংক পাওয়া যায়নি।")

    await notice.edit(f"✅ {len(valid_urls)} টি লিংক পাওয়া গেছে। ডাউনলোড শুরু হচ্ছে...")

    for url in valid_urls:
        try:
            if is_google_drive_link(url):
                url = fix_google_drive_url(url)

            await notice.delete()
            processing = await message.reply_text(f"⬇️ ডাউনলোড শুরু:\n`{url}`", reply_to_message_id=message.id)

            if is_mega_link(url):
                filepath, info = await asyncio.to_thread(download_mega_file, url)
                filepath = os.path.join("/tmp", filepath)
            elif is_terabox_link(url):
                filepath, info = await download_terabox_file(url)
            else:
                filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

            if not os.path.exists(filepath):
                raise Exception("ডাউনলোড ব্যর্থ হয়েছে বা ফাইল খুঁজে পাওয়া যায়নি।")

            ext = os.path.splitext(filepath)[1]
            caption = f"✅ **ডাউনলোড সম্পন্ন**\n🔗 {url}"

            await processing.edit("📤 আপলোড শুরু হচ্ছে...")

            if ext.lower() in VIDEO_EXTENSIONS:
                thumb = generate_thumbnail(filepath)
                await message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if thumb else None,
                    reply_to_message_id=message.id
                )
            else:
                await message.reply_document(
                    document=filepath,
                    caption=caption,
                    reply_to_message_id=message.id
                )

            await processing.delete()

            user = message.from_user
            file_size = format_bytes(os.path.getsize(filepath))
            log_text = (
                f"**📥 নতুন ডাউনলোড**\n\n"
                f"👤 **User:** {user.mention} (`{user.id}`)\n"
                f"🔗 **Link:** `{url}`\n"
                f"📄 **File Name:** `{os.path.basename(filepath)}`\n"
                f"📦 **Size:** `{file_size}`\n"
                f"🌀 **Type:** `{'Video' if ext.lower() in VIDEO_EXTENSIONS else 'Document'}`\n"
                f"⏰ **Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            try:
                await bot.send_message(LOG_CHANNEL, log_text)
            except Exception:
                pass

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ ডাউনলোড ব্যর্থ:\n{url}\n\n**{e}**", reply_to_message_id=message.id)

        finally:
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except Exception:
                pass