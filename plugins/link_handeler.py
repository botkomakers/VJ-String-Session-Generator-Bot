import os
import yt_dlp
from telethon import events
from telethon.tl.custom import Button
from pyrogram import Client

# Function to download video from YouTube
def download_video(url, format_choice):
    ydl_opts = {
        'format': format_choice,
        'outtmpl': './downloads/%(title)s.%(ext)s',  # Download folder
        'progress_hooks': [progress_hook]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Progress hook to track download progress
def progress_hook(d):
    if d['status'] == 'downloading':
        print(f"Downloading... {d['filename']} - {d['_percent_str']} at {d['_speed_str']}")
    elif d['status'] == 'finished':
        print(f"Download finished: {d['filename']}")

# Function to get available formats from YouTube link
def get_video_formats(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        return formats

# Handle /start command
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond('Welcome to the Video Downloader Bot! Send me a YouTube link and I will help you download it.')

# Handle link detection and processing
@client.on(events.NewMessage(pattern='https?://'))
async def handle_links(event):
    url = event.message.text
    if 'youtube.com' in url:
        formats = get_video_formats(url)
        buttons = []
        for fmt in formats:
            button_text = f"{fmt['format_note']} - {fmt['ext']}"
            buttons.append(Button.url(button_text, fmt['url']))

        # Send the formats as buttons
        await event.respond("Select the format you want to download:", buttons=buttons)
    else:
        await event.respond("Unsupported link detected. I can only download videos from YouTube currently.")