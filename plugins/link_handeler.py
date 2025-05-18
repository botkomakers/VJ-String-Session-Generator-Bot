# filename: downloader.py

import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".webm", ".aac", ".ogg"]
DEFAULT_THUMB = "https://i.ibb.co/Xk4Hbg8h/photo-2025-05-07-15-52-21-7505459490108473348.jpg"

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def make_progress_bar(current, total, length=20):
    percent = current / total
    filled = int(length * percent)
    return f"{int(percent * 100)}%\n{'■'*filled + '▩' + '□'*(length-filled-1)}"

async def progress_callback(current, total, message, action="Downloading"):
    try:
        bar = make_progress_bar(current, total)
        await message.edit_text(f"{action}: {bar}")
    except: pass

async def auto_cleanup(path="/tmp", max_age=300):
    now = time.time()
    for f in os.listdir(path):
        f_path = os.path.join(path, f)
        if os.path.isfile(f_path) and time.time() - os.path.getmtime(f_path) > max_age:
            try: os.remove(f_path)
            except: pass

def generate_thumbnail(file_path, output="/tmp/thumb.jpg"):
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output if os.path.exists(output) else None
    except: return None

def is_google_drive_link(url): return "drive.google.com" in url
def fix_google_drive_url(url):
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?id={file_id}&export=download"
    return url

def is_mega_link(url): return "mega.nz" in url or "mega.co.nz" in url
def is_torrent_or_magnet(url): return url.startswith("magnet:") or url.endswith(".torrent")
def is_terabox_link(url): return "terabox" in url

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies/youtube.txt"
    return None

def download_with_ytdlp(url, download_dir="/tmp", message=None, audio_only=False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(progress_callback(downloaded, total, message), loop)

    opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }

    cookie_file = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if audio_only and not filename.endswith(".mp3"):
            audio_file = filename.rsplit(".", 1)[0] + ".mp3"
            os.system(f"ffmpeg -i '{filename}' -vn -ab 128k -ar 44100 -y '{audio_file}'")
            os.remove(filename)
            filename = audio_file
        return filename, info

def download_torrent_or_magnet(url, download_dir="/tmp"):
    import libtorrent as lt
    import time as t
    ses = lt.session()
    ses.listen_on(6881, 6891)

    if url.startswith("magnet:"):
        h = lt.add_magnet_uri(ses, url, {'save_path': download_dir})
    else:
        info = lt.torrent_info(url)
        h = ses.add_torrent({'ti': info, 'save_path': download_dir})

    while not h.has_metadata(): t.sleep(1)
    while h.status().state != lt.torrent_status.seeding:
        s = h.status()
        print(f"Downloading: {s.progress*100:.2f}%")
        t.sleep(1)

    files = h.get_torrent_info().files()
    return os.path.join(download_dir, files[0].path)

def download_terabox_file(url, download_dir="/tmp"):
    import terabox
    tbox = terabox.TeraBox()
    info = tbox.get_info(url)
    downloaded = tbox.download(url, download_dir)
    return downloaded, {"title": info["name"], "ext": os.path.splitext(info["name"])[1].lstrip(".")}

@Client.on_message(filters.private & ~filters.command("start"))
async def handle_link(bot, message):
    if message.from_user.is_bot or message.reply_to_message:
        return

    urls = message.text.strip().split()
    valid_urls = [u for u in urls if u.lower().startswith(("http", "magnet:")) or u.lower().endswith(".torrent")]
    if not valid_urls:
        return await message.reply("No valid links detected.")

    url = valid_urls[0]
    if is_google_drive_link(url) or is_mega_link(url) or is_torrent_or_magnet(url) or is_terabox_link(url):
        return await start_download(bot, message, url, "video")

    if any(url.lower().endswith(ext) for ext in AUDIO_EXTENSIONS):
        return await start_download(bot, message, url, "audio")

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("Video", callback_data=f"video|{message.id}"),
        InlineKeyboardButton("Audio", callback_data=f"audio|{message.id}")
    ]])
    await message.reply("Do you want to download as Video or Audio?", reply_markup=buttons)

@Client.on_callback_query()
async def handle_callback(bot, cb: CallbackQuery):
    if "|" in cb.data:
        mode, msg_id = cb.data.split("|")
        msg_id = int(msg_id)
        message = await bot.get_messages(cb.message.chat.id, msg_id)
        if message:
            url = message.text.strip().split()[0]
            await cb.message.delete()
            await start_download(bot, message, url, mode)

async def start_download(bot, message, url, mode):
    filepath = None
    try:
        processing = await message.reply(f"Downloading {mode.title()}...\n{url}")
        if is_google_drive_link(url):
            url = fix_google_drive_url(url)

        if is_mega_link(url):
            from mega import Mega
            file = await asyncio.to_thread(Mega().login().download_url, url, "/tmp")
            filepath = file.name

        elif is_torrent_or_magnet(url):
            filepath = await asyncio.to_thread(download_torrent_or_magnet, url)

        elif is_terabox_link(url):
            filepath, _ = await asyncio.to_thread(download_terabox_file, url)

        else:
            filepath, _ = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", processing, audio_only=(mode == "audio"))

        if not os.path.exists(filepath):
            raise Exception("Download failed.")

        ext = os.path.splitext(filepath)[1]
        thumb = generate_thumbnail(filepath)
        if not thumb and ext.lower() in AUDIO_EXTENSIONS:
            thumb = DEFAULT_THUMB

        caption = "⚠️ This file will be deleted in 5 minutes. Forward it to save."
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Source Link", url=url)],
            [InlineKeyboardButton("❌ Delete Now", callback_data=f"delete_{message.id}")]
        ])

        if ext.lower() in VIDEO_EXTENSIONS:
            sent = await message.reply_video(video=filepath, caption=caption, thumb=thumb, supports_streaming=True, reply_markup=buttons)
        else:
            sent = await message.reply_document(document=filepath, caption=caption, thumb=thumb, reply_markup=buttons)

        await processing.delete()
        asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

        await bot.send_message(LOG_CHANNEL, f"User: {message.from_user.mention} ({message.from_user.id})\nFile: {os.path.basename(filepath)}\nSize: {format_bytes(os.path.getsize(filepath))}")

        if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
            await bot.send_message(ADMIN_ID, f"⚠️ Porn content detected from {message.from_user.mention} ({message.from_user.id})\nLink: {url}")

    except Exception as e:
        traceback.print_exc()
        await message.reply(f"❌ Download failed:\n{e}")
    finally:
        try:
            if filepath and os.path.exists(filepath): os.remove(filepath)
            await auto_cleanup()
        except: pass

async def auto_delete_message(bot, chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_messages(chat_id, msg_id)
    except: pass