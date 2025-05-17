import os, uuid, aiohttp, asyncio, traceback, datetime, time, yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
url_cache = {}

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
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > max_age:
            try: os.remove(file_path)
            except: pass

def is_google_drive_link(url): return "drive.google.com" in url
def fix_google_drive_url(url):
    if "uc?id=" in url or "export=download" in url: return url
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?id={file_id}&export=download"
    return url

def is_mega_link(url): return "mega.nz" in url or "mega.co.nz" in url
def get_cookie_file(url):
    if "instagram.com" in url: return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url: return "cookies/youtube.txt"
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

def download_with_ytdlp(url, download_dir="/tmp", message=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(downloaded, total, message, "Downloading"), loop)
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }
    cookie_file = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def ask_download_type(bot: Client, message: Message):
    url = message.text.strip().split()[0]
    if not url.lower().startswith("http"):
        return await message.reply("সঠিক লিংক দিন।")
    uid = str(uuid.uuid4())[:8]
    url_cache[uid] = url
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 ভিডিও", callback_data=f"video|{uid}"),
         InlineKeyboardButton("🎧 অডিও", callback_data=f"audio|{uid}")]
    ])
    await message.reply_text("আপনি কী ডাউনলোড করতে চান?", reply_markup=buttons)

@Client.on_callback_query()
async def handle_download_request(bot, query):
    data = query.data
    if "|" not in data: return
    action, uid = data.split("|", 1)
    url = url_cache.get(uid)
    if not url:
        return await query.message.edit_text("❌ লিংকটির মেয়াদ শেষ হয়েছে।")
    await query.answer()
    try:
        msg = await query.message.reply("ডাউনলোড শুরু হচ্ছে...")
        if is_google_drive_link(url): url = fix_google_drive_url(url)
        if is_mega_link(url):
            filepath, info = await asyncio.to_thread(download_mega_file, url)
            filepath = os.path.join("/tmp", filepath)
        else:
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", msg)

        if not os.path.exists(filepath): raise Exception("ফাইল ডাউনলোড ব্যর্থ।")
        ext = os.path.splitext(filepath)[1]
        caption = (
            "**⚠️ ফাইলটি ৫ মিনিট পরে ডিলিট হয়ে যাবে!**\n"
            "আপনার সেভড মেসেজে বা অন্যত্র সেভ করুন।\n\n"
            f"[Source Link]({url})"
        )
        upload_msg = await msg.edit("আপলোড হচ্ছে...")
        thumb = generate_thumbnail(filepath) or "default_thumb.jpg"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Source", url=url)],
            [InlineKeyboardButton("❌ ডিলিট করুন", callback_data="delete_now")]
        ])
        if action == "audio":
            audio_path = filepath.replace(ext, ".mp3")
            os.system(f'ffmpeg -i "{filepath}" -vn -ab 128k -ar 44100 -y "{audio_path}"')
            sent = await query.message.reply_audio(
                audio=audio_path,
                caption=caption,
                thumb=thumb if os.path.exists(thumb) else None,
                reply_markup=buttons
            )
            os.remove(audio_path)
        else:
            if ext.lower() in VIDEO_EXTENSIONS:
                sent = await query.message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb if os.path.exists(thumb) else None,
                    supports_streaming=True,
                    reply_markup=buttons
                )
            else:
                sent = await query.message.reply_document(
                    document=filepath,
                    caption=caption,
                    reply_markup=buttons
                )
        await upload_msg.delete()
        asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))
        user = query.from_user
        file_size = format_bytes(os.path.getsize(filepath))
        log_text = (
            f"**New Download Event**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File Name:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{file_size}`\n"
            f"**Type:** `{'Audio' if action == 'audio' else 'Video'}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        if action == "audio":
            await bot.send_audio(LOG_CHANNEL, audio=filepath, caption=log_text)
        elif ext.lower() in VIDEO_EXTENSIONS:
            await bot.send_video(LOG_CHANNEL, video=filepath, caption=log_text)
        else:
            await bot.send_document(LOG_CHANNEL, document=filepath, caption=log_text)

        if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
            await bot.send_message(ADMIN_ID, f"⚠️ Porn link detected\nUser: {user.mention} (`{user.id}`)\nLink: {url}")
    except Exception as e:
        traceback.print_exc()
        await query.message.reply(f"❌ ডাউনলোড ব্যর্থ:\n{e}")
    finally:
        try:
            if os.path.exists(filepath): os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"): os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except: pass

@Client.on_callback_query(filters.regex("delete_now"))
async def handle_callback(bot, query):
    try:
        await bot.delete_messages(query.message.chat.id, query.message.id)
        await query.answer("Deleted", show_alert=False)
    except:
        await query.answer("Failed to delete", show_alert=True)

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_messages(chat_id, message_id)
    except: pass