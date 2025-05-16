import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import hashlib
from typing import List, Tuple, Dict, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMINS, MAX_CONCURRENT_DOWNLOADS
from dataclasses import dataclass
from enum import Enum, auto

# Constants
VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a"]
IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
MAX_DAILY_QUOTA = 2 * 1024 * 1024 * 1024  # 2 GB
PART_SIZE = int(1.7 * 1024 * 1024 * 1024)  # 1.7 GB
TEMP_DIR = "/tmp/ytdl_bot"
THUMBNAIL_PATH = os.path.join(TEMP_DIR, "thumbnail.jpg")
os.makedirs(TEMP_DIR, exist_ok=True)

# Enums
class DownloadQuality(Enum):
    BEST = auto()
    HD_1080 = auto()
    HD_720 = auto()
    SD_480 = auto()
    AUDIO_ONLY = auto()

class DownloadStatus(Enum):
    PENDING = auto()
    DOWNLOADING = auto()
    PROCESSING = auto()
    UPLOADING = auto()
    COMPLETED = auto()
    FAILED = auto()

# Data Classes
@dataclass
class UserQuota:
    user_id: int
    used_bytes: int = 0
    last_reset: datetime.date = datetime.date.today()

@dataclass
class DownloadTask:
    url: str
    message: Message
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    file_path: str = ""
    file_size: int = 0
    quality: DownloadQuality = DownloadQuality.BEST
    parts: List[str] = None
    start_time: float = time.time()
    end_time: float = 0

# Global State
USER_QUOTA: Dict[int, UserQuota] = {}
ACTIVE_DOWNLOADS: Dict[str, DownloadTask] = {}
TASK_QUEUE = asyncio.Queue()
CURRENT_DOWNLOADS = 0

# UI Components
class UI:
    @staticmethod
    async def send_welcome_message(client: Client, message: Message):
        welcome_text = """
🌟 **Welcome to Advanced YouTube Downloader Bot** 🌟

🔹 Download videos from YouTube and other supported sites
🔹 Multiple quality options available
🔹 Automatic splitting for large files
🔹 Quota tracking system

📌 **How to use:**
1. Send a YouTube link
2. Choose your preferred quality
3. Wait for the download to complete

📊 Your daily quota: {quota}
"""
        user_quota = UI.get_user_quota(message.from_user.id)
        quota_text = f"{UI.format_bytes(user_quota.used_bytes)} / {UI.format_bytes(MAX_DAILY_QUOTA)}"
        
        await message.reply(
            text=welcome_text.format(quota=quota_text),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Supported Sites", callback_data="supported_sites")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
            )
        )

    @staticmethod
    async def send_quality_menu(client: Client, message: Message, url: str):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 Best Quality", callback_data=f"quality_{url}_best"),
                InlineKeyboardButton("🎥 1080p", callback_data=f"quality_{url}_1080")
            ],
            [
                InlineKeyboardButton("🎥 720p", callback_data=f"quality_{url}_720"),
                InlineKeyboardButton("🎥 480p", callback_data=f"quality_{url}_480")
            ],
            [
                InlineKeyboardButton("🎵 Audio Only", callback_data=f"quality_{url}_audio"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{url}")
            ]
        ])
        
        await message.reply(
            text=f"🔍 **Select Quality for:**\n{url}",
            reply_markup=keyboard
        )

    @staticmethod
    async def update_progress_message(task: DownloadTask):
        elapsed = time.time() - task.start_time
        progress_text = ""
        
        if task.status == DownloadStatus.DOWNLOADING:
            progress_text = f"⬇️ Downloading... {task.progress:.1f}%"
        elif task.status == DownloadStatus.PROCESSING:
            progress_text = "🔧 Processing video..."
        elif task.status == DownloadStatus.UPLOADING:
            progress_text = f"⬆️ Uploading... {task.progress:.1f}%"
        
        speed = task.file_size / elapsed if elapsed > 0 else 0
        eta = (100 - task.progress) * elapsed / task.progress if task.progress > 0 else 0
        
        text = f"""
📥 **Download Info**
🔗 URL: {task.url}
📊 Status: {task.status.name}
📈 Progress: {progress_text}
📦 File Size: {UI.format_bytes(task.file_size)}
🚀 Speed: {UI.format_bytes(speed)}/s
⏳ ETA: {UI.format_time(eta)}
"""
        
        try:
            await task.message.edit_text(text)
        except:
            pass

    @staticmethod
    async def send_completion_message(task: DownloadTask, client: Client):
        elapsed = time.time() - task.start_time
        text = f"""
✅ **Download Complete!**
🔗 URL: {task.url}
📦 File Size: {UI.format_bytes(task.file_size)}
⏱️ Time Taken: {UI.format_time(elapsed)}
"""
        
        await task.message.reply(text)
        
        # Send to log channel
        user = task.message.from_user
        log_text = f"""
📥 **Download Completed**
👤 User: [{user.first_name}](tg://user?id={user.id})
🔗 URL: {task.url}
📊 Quality: {task.quality.name}
📦 Size: {UI.format_bytes(task.file_size)}
⏱️ Time: {UI.format_time(elapsed)}
"""
        await client.send_message(LOG_CHANNEL, log_text)

    @staticmethod
    async def send_error_message(message: Message, error: str, url: str = None):
        text = f"""
❌ **Download Failed**
{f'🔗 URL: {url}\n' if url else ''}
⚠️ Error: {error}
"""
        await message.reply(text)

    @staticmethod
    def format_bytes(size: float) -> str:
        power = 1024
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        n = 0
        while size > power and n < len(units) - 1:
            size /= power
            n += 1
        return f"{size:.2f} {units[n]}"

    @staticmethod
    def format_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes:.0f}m {seconds:.0f}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours:.0f}h {minutes:.0f}m"

    @staticmethod
    def get_user_quota(user_id: int) -> UserQuota:
        today = datetime.date.today()
        if user_id not in USER_QUOTA or USER_QUOTA[user_id].last_reset < today:
            USER_QUOTA[user_id] = UserQuota(user_id=user_id, last_reset=today)
        return USER_QUOTA[user_id]

# Utility Functions
class Utils:
    @staticmethod
    def generate_thumbnail(video_path: str) -> Optional[str]:
        try:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-ss", "00:00:01.000", 
                 "-vframes", "1", THUMBNAIL_PATH],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return THUMBNAIL_PATH if os.path.exists(THUMBNAIL_PATH) else None
        except:
            return None

    @staticmethod
    def get_file_extension(file_path: str) -> str:
        return os.path.splitext(file_path)[1].lower()

    @staticmethod
    def split_large_file(file_path: str, part_size: int = PART_SIZE) -> List[str]:
        parts = []
        part_num = 1
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(part_size)
                if not chunk:
                    break
                part_path = f"{file_path}.part{part_num:03d}"
                with open(part_path, 'wb') as part_file:
                    part_file.write(chunk)
                parts.append(part_path)
                part_num += 1
        return parts

    @staticmethod
    def clean_temp_files():
        now = time.time()
        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(file_path):
                # Delete files older than 1 hour
                if now - os.path.getmtime(file_path) > 3600:
                    try:
                        os.remove(file_path)
                    except:
                        pass

    @staticmethod
    def ydl_progress_hook(d: dict, task: DownloadTask):
        if d['status'] == 'downloading':
            task.progress = float(d.get('_percent_str', '0%').strip('%'))
            task.status = DownloadStatus.DOWNLOADING
        elif d['status'] == 'finished':
            task.status = DownloadStatus.PROCESSING
            task.progress = 100

    @staticmethod
    def build_ydl_opts(url: str, quality: DownloadQuality = DownloadQuality.BEST) -> dict:
        download_dir = TEMP_DIR
        format_map = {
            DownloadQuality.BEST: "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
            DownloadQuality.HD_1080: "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best",
            DownloadQuality.HD_720: "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
            DownloadQuality.SD_480: "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best",
            DownloadQuality.AUDIO_ONLY: "bestaudio[ext=m4a]"
        }
        
        return {
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
            "format": format_map[quality],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [lambda d: Utils.ydl_progress_hook(d, ACTIVE_DOWNLOADS[url])],
            "postprocessors": [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }] if quality != DownloadQuality.AUDIO_ONLY else []
        }

# Download Manager
class DownloadManager:
    @staticmethod
    async def process_queue():
        global CURRENT_DOWNLOADS
        while True:
            if CURRENT_DOWNLOADS < MAX_CONCURRENT_DOWNLOADS:
                task = await TASK_QUEUE.get()
                CURRENT_DOWNLOADS += 1
                asyncio.create_task(DownloadManager.handle_download(task))
            await asyncio.sleep(1)

    @staticmethod
    async def handle_download(task: DownloadTask):
        try:
            # Check quota
            user_quota = UI.get_user_quota(task.message.from_user.id)
            if user_quota.used_bytes >= MAX_DAILY_QUOTA:
                await UI.send_error_message(
                    task.message,
                    "You have reached your daily quota limit.",
                    task.url
                )
                return

            # Start download
            ACTIVE_DOWNLOADS[task.url] = task
            task.status = DownloadStatus.DOWNLOADING
            
            # Download with yt-dlp
            filepath, info = await DownloadManager.download_with_ytdlp(task)
            
            if not os.path.exists(filepath):
                raise Exception("Download failed or file not found.")
            
            # Update task info
            task.file_path = filepath
            task.file_size = os.path.getsize(filepath)
            
            # Check quota again after knowing file size
            if user_quota.used_bytes + task.file_size > MAX_DAILY_QUOTA:
                await UI.send_error_message(
                    task.message,
                    "This download would exceed your daily quota limit.",
                    task.url
                )
                os.remove(filepath)
                return
            
            # Process file
            task.status = DownloadStatus.PROCESSING
            await UI.update_progress_message(task)
            
            # Split if needed
            task.parts = [filepath]
            if task.file_size > PART_SIZE:
                task.parts = Utils.split_large_file(filepath)
            
            # Upload files
            task.status = DownloadStatus.UPLOADING
            await DownloadManager.upload_files(task)
            
            # Update quota
            user_quota.used_bytes += task.file_size
            
            # Cleanup
            task.status = DownloadStatus.COMPLETED
            task.end_time = time.time()
            await UI.send_completion_message(task, task.message._client)
            
        except Exception as e:
            task.status = DownloadStatus.FAILED
            await UI.send_error_message(task.message, str(e), task.url)
            traceback_text = traceback.format_exc()
            for admin in ADMINS:
                try:
                    await task.message._client.send_message(
                        admin,
                        f"Error on {task.url}:\n\n{traceback_text}"
                    )
                except:
                    pass
        finally:
            DownloadManager.cleanup_task(task)
            global CURRENT_DOWNLOADS
            CURRENT_DOWNLOADS -= 1

    @staticmethod
    async def download_with_ytdlp(task: DownloadTask) -> Tuple[str, dict]:
        ydl_opts = Utils.build_ydl_opts(task.url, task.quality)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, task.url, download=True)
            filename = ydl.prepare_filename(info)
        return filename, info

    @staticmethod
    async def upload_files(task: DownloadTask):
        client = task.message._client
        user = task.message.from_user
        ext = Utils.get_file_extension(task.file_path)
        thumbnail = None
        
        if ext in VIDEO_EXTENSIONS:
            thumbnail = Utils.generate_thumbnail(task.file_path)
        
        for idx, part in enumerate(task.parts):
            part_num = f" (Part {idx+1}/{len(task.parts)})" if len(task.parts) > 1 else ""
            caption = f"📥 {os.path.basename(part)}{part_num}\n🔗 From: {task.url}"
            
            # Update progress
            task.progress = (idx / len(task.parts)) * 100
            await UI.update_progress_message(task)
            
            try:
                if ext in VIDEO_EXTENSIONS:
                    await client.send_video(
                        chat_id=task.message.chat.id,
                        video=part,
                        caption=caption,
                        thumb=thumbnail,
                        progress=lambda current, total: DownloadManager.upload_progress(
                            current, total, task, idx, len(task.parts)
                        )
                    )
                elif ext in AUDIO_EXTENSIONS:
                    await client.send_audio(
                        chat_id=task.message.chat.id,
                        audio=part,
                        caption=caption,
                        progress=lambda current, total: DownloadManager.upload_progress(
                            current, total, task, idx, len(task.parts)
                    )
                else:
                    await client.send_document(
                        chat_id=task.message.chat.id,
                        document=part,
                        caption=caption,
                        progress=lambda current, total: DownloadManager.upload_progress(
                            current, total, task, idx, len(task.parts)
                    )
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue

    @staticmethod
    def upload_progress(current: int, total: int, task: DownloadTask, part_idx: int, total_parts: int):
        part_progress = (current / total) * 100
        overall_progress = (part_idx + (part_progress / 100)) / total_parts * 100
        task.progress = overall_progress
        asyncio.create_task(UI.update_progress_message(task))

    @staticmethod
    def cleanup_task(task: DownloadTask):
        try:
            if task.file_path and os.path.exists(task.file_path):
                os.remove(task.file_path)
            if task.parts:
                for part in task.parts:
                    if os.path.exists(part):
                        os.remove(part)
            if os.path.exists(THUMBNAIL_PATH):
                os.remove(THUMBNAIL_PATH)
            Utils.clean_temp_files()
        except:
            pass
        ACTIVE_DOWNLOADS.pop(task.url, None)

# Bot Handlers
@Client.on_message(filters.command(["start", "help"]))
async def start_handler(client: Client, message: Message):
    await UI.send_welcome_message(client, message)

@Client.on_message(filters.text & ~filters.command(["start", "help", "quota", "status"]))
async def url_handler(client: Client, message: Message):
    urls = message.text.strip().split()
    valid_urls = [url for url in urls if url.lower().startswith(("http://", "https://"))]
    
    if not valid_urls:
        return await message.reply("❌ No valid URLs found in your message.")
    
    for url in valid_urls:
        if url in ACTIVE_DOWNLOADS:
            await message.reply(f"⏳ This URL is already being processed: {url}")
            continue
        
        await UI.send_quality_menu(client, message, url)

@Client.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data.startswith("quality_"):
        _, url, quality = data.split("_")
        quality_map = {
            "best": DownloadQuality.BEST,
            "1080": DownloadQuality.HD_1080,
            "720": DownloadQuality.HD_720,
            "480": DownloadQuality.SD_480,
            "audio": DownloadQuality.AUDIO_ONLY
        }
        
        task = DownloadTask(
            url=url,
            message=callback_query.message,
            quality=quality_map[quality]
        )
        
        await TASK_QUEUE.put(task)
        await callback_query.answer(f"Added to queue. Quality: {quality}")
        
    elif data == "supported_sites":
        await callback_query.answer("All sites supported by yt-dlp", show_alert=True)
    
    elif data == "settings":
        await callback_query.answer("Settings menu coming soon!")
    
    elif data.startswith("cancel_"):
        _, url = data.split("_")
        if url in ACTIVE_DOWNLOADS:
            # Implement cancellation logic
            pass
        await callback_query.answer("Download cancelled")
        await callback_query.message.delete()

# Initialize
async def initialize():
    asyncio.create_task(DownloadManager.process_queue())

# Start the bot
if __name__ == "__main__":
    app = Client("yt_downloader_bot")
    app.run(initialize())