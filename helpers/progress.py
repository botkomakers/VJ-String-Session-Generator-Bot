import math
import time

async def progress_bar(current, total, message, stage="Downloading"):
    if total == 0:
        return

    percent = current * 100 / total
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    current_mb = current / (1024 * 1024)
    total_mb = total / (1024 * 1024)

    text = f"**{stage}**\n`[{bar}]` `{percent:.2f}%`\n`{current_mb:.2f} MB / {total_mb:.2f} MB`"
    try:
        await message.edit(text)
    except:
        pass
