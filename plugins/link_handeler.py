import os
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.progress import progress_bar
import mimetypes
import re
from time import time

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_link_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        return await message.reply("Please send a valid direct download link.")

    processing = await message.reply("**Fetching the file...**")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200 or resp.content_type.startswith("text"):
                    return await processing.edit("**Failed to fetch the file. Not a direct downloadable video link.**")

                total = int(resp.headers.get("Content-Length", 0))
                content_type = resp.headers.get("Content-Type", "")
                ext = mimetypes.guess_extension(content_type.split(";")[0]) or ""

                if not ext or ext in [".html", ".htm", ".txt"]:
                    ext = ".mp4"  # fallback

                filename = f"video_{int(time())}{ext}"
                path = f"./downloads/{filename}"

                os.makedirs("downloads", exist_ok=True)

                f = await aiofiles.open(path, mode='wb')
                downloaded = 0
                chunk_size = 1024 * 64
                start = time()

                async for chunk in resp.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    if time() - start > 2:
                        start = time()
                        await progress_bar(downloaded, total, processing, "Downloading")

                await f.close()

    except Exception as e:
        return await processing.edit(f"**Error while downloading:** `{e}`")

    await processing.edit("**Uploading to Telegram...**")

    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=path,
            caption=f"**Downloaded from:** `{url}`",
            progress=progress_bar,
            progress_args=(processing, "Uploading")
        )
    except Exception as e:
        await processing.edit(f"**Upload failed:** `{e}`")
    finally:
        if os.path.exists(path):
            os.remove(path)