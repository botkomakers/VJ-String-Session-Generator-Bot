import aiohttp
import asyncio

async def download_with_progress(url, filename, message):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            with open(filename, "wb") as f:
                downloaded = 0
                chunk_size = 1024 * 1024
                while True:
                    chunk = await resp.content.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded % (50 * 1024 * 1024) == 0:
                        await message.edit(f"📥 Downloaded: {round(downloaded / (1024**2), 2)} MB of {round(total / (1024**2), 2)} MB")