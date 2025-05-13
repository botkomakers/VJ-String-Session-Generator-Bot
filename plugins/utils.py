
import math
import time

async def progress_bar(current, total, message, start_text, suffix="file"):
    now = time.time()
    percent = current / total * 100
    speed = current / (now - message.date.timestamp() + 1)
    eta = (total - current) / speed if speed > 0 else 0

    progress = f"[{'=' * int(percent / 10)}{' ' * (10 - int(percent / 10))}]"
    current_mb = round(current / (1024 * 1024), 2)
    total_mb = round(total / (1024 * 1024), 2)
    speed_mb = round(speed / (1024 * 1024), 2)

    text = (
        f"{start_text}\n"
        f"{progress} **{percent:.2f}%**\n"
        f"Transferred: {current_mb}/{total_mb} MB\n"
        f"Speed: {speed_mb} MB/s\n"
        f"ETA: {math.ceil(eta)}s"
    )
    await message.edit(text)