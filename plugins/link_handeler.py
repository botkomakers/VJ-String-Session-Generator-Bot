import os
import time
import mimetypes
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from urllib.parse import unquote

THUMBNAIL_URL = "https://i.ibb.co/21RKmKDG/file-1485.jpg"

def get_filename_from_url(url):
    try:
        filename = unquote(url.split("/")[-1].split("?")[0])
        if "." in filename:
            return filename
    except:
        pass
    return None

def human_readable_size(size):
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def smart_direct_downloader(client, message: Message):
    url = message.text.strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        return

    status = await message.reply_photo(
        photo=THUMBNAIL_URL,
        caption="⏳ Starting download..."
    )

    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))

            filename = get_filename_from_url(url) or f"file_{int(time.time())}"
            content_type = r.headers.get("content-type", "")
            ext = mimetypes.guess_extension(content_type.split(";")[0]) if content_type else None

            if ext and not filename.endswith(ext):
                filename += ext
            elif not os.path.splitext(filename)[1]:
                filename += ".bin"

            downloaded = 0
            last_percent = -1

            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total:
                            percent = int(downloaded * 100 / total)
                            if percent % 5 == 0 and percent != last_percent:
                                await status.edit_caption(
                                    f"⏬ Downloading: {percent}%\n"
                                    f"📦 Size: {human_readable_size(downloaded)} / {human_readable_size(total)}"
                                )
                                last_percent = percent
    except Exception as e:
        print(f"Download Error: {e}")
        return await status.edit_caption("❌ Failed to download the file.")

    try:
        await status.edit_caption("⬆️ Uploading to Telegram...")
        if filename.lower().endswith((".mp4", ".mkv", ".mov", ".webm")):
            await message.reply_video(
                video=filename,
                thumb=THUMBNAIL_URL,
                caption="✅ Here’s your video"
            )
        else:
            await message.reply_document(
                document=filename,
                caption="✅ Here’s your file"
            )
    except Exception as e:
        print(f"Upload Error: {e}")
        await message.reply("❌ Failed to upload the file.")
    finally:
        if os.path.exists(filename):
            os.remove(filename)
        await status.delete()