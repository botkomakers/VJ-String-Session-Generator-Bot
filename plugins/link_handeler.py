from pyrogram import Client, filters
from pyrogram.types import Message
import requests
import os
import mimetypes
from config import temp

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(bot: Client, message: Message):
    url = message.text.strip()

    if not url.lower().startswith("http"):
        return

    msg = await message.reply_text("Checking the link...")

    try:
        head = requests.head(url, allow_redirects=True)
        content_type = head.headers.get("content-type", "")

        if not content_type.startswith("video/"):
            return await msg.edit("This link does not point to a valid video file.")

        ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".mp4"
        filename = "video" + ext

        await msg.edit("Downloading the video...")

        r = requests.get(url, stream=True)
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        await msg.edit("Uploading to Telegram...")

        await message.reply_video(
            video=filename,
            caption=f"**Downloaded from:** `{url}`"
        )
        await msg.delete()

    except Exception as e:
        await msg.edit(f"Failed to download: `{e}`")

    finally:
        if os.path.exists(filename):
            os.remove(filename)