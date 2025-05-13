# progress.py (ফাইল তৈরি করতে হবে)

import math
import time

async def progress_bar(current, total, message, stage):
    percent = current * 100 / total if total else 0
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    current_mb = current / 1024 / 1024
    total_mb = total / 1024 / 1024
    await message.edit_text(
        f"**{stage}**\n"
        f"[{bar}] {percent:.2f}%\n"
        f"**{current_mb:.2f} MB** of **{total_mb:.2f} MB**"
  )
