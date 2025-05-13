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
        caption="⏳ <b>Starting download...</b>",
        parse_mode="html"
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
                                    f"⏬ <b>Downloading:</b> {percent}%\n"
                                    f"📦 <b>Size:</b> {human_readable_size(downloaded)} / {human_readable_size(total)}",
                                    parse_mode="html"
                                )
                                last_percent = percent
    except Exception as e:
        print(f"Download Error: {e}")
        return await status.edit_caption("❌ <b>Failed to download the file.</b>", parse_mode="html")

    try:
        await status.edit_caption("⬆️ <b>Uploading to Telegram...</b>", parse_mode="html")
        if filename.lower().endswith((".mp4", ".mkv", ".mov", ".webm")):
            await message.reply_video(
                video=filename,
                thumb=THUMBNAIL_URL,
                caption="✅ <b>Here’s your video</b>",
                parse_mode="html"
            )
        else:
            await message.reply_document(
                document=filename,
                caption="✅ <b>Here’s your file</b>",
                parse_mode="html"
            )
    except Exception as e:
        print(f"Upload Error: {e}")
        await message.reply("❌ Failed to upload the file.")
    finally:
        if os.path.exists(filename):
            os.remove(filename)
        await status.delete()