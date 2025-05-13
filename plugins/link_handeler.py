import os
import aiohttp
import aiofiles
import mimetypes
from urllib.parse import unquote
from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.utils import progress_bar
from config import temp

@Client.on_message(filters.text & ~filters.forwarded)
async def direct_link_handler(client: Client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        return

    if not any(url.lower().endswith(ext) for ext in [".mp4", ".mkv", ".mov", ".avi", ".webm"]):
        return

    try:
        msg = await message.reply("**Processing your link...**")

        filename = url.split("/")[-1].split("?")[0]
        filename = filename if "." in filename else "video.mp4"
        filename = unquote(filename)  # Decode %20 etc.
        os.makedirs(temp.DOWNLOAD_DIR, exist_ok=True)
        filepath = f"{temp.DOWNLOAD_DIR}/{filename}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await msg.edit("**Failed to download file. Invalid or expired link.**")

                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB

                async with aiofiles.open(filepath, mode='wb') as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        await progress_bar(
                            current=downloaded,
                            total=total,
                            message=msg,
                            start_text="**Downloading...**",
                            suffix="video"
                        )

        mime_type, _ = mimetypes.guess_type(filepath)
        mime_type = mime_type or "video/mp4"

        await msg.edit("**Uploading to Telegram...**")

        await message.reply_video(
            video=filepath,
            caption=f"**Downloaded from:** `{url}`",
            supports_streaming=True
        )
        await msg.delete()

    except Exception as e:
        await msg.edit(f"**Error:** `{str(e)}`")

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)