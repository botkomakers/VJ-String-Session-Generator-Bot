import telebot
import yt_dlp
from telebot import types
import os

# Telegram bot token from config.py
from config import BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)

# Function to download any video link (YouTube, Facebook, TikTok, etc.)
def download_video(url):
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'noplaylist': True,
        'progress_hooks': [progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = 'downloads/' + info_dict['title'] + '.' + info_dict['ext']
        return file_path

# Progress hook to show download progress
def progress_hook(d):
    if d['status'] == 'downloading':
        percent = d['_percent_str']
        speed = d['_speed_str']
        eta = d['_eta_str']
        print(f"Download Progress: {percent} at {speed} ETA: {eta}")

# Function to handle all social media video links
@bot.message_handler(regexp=r'^(https?://)(\S+)$')
def handle_video(message):
    url = message.text
    bot.reply_to(message, "Processing your video download, please wait...")

    try:
        # Download the video
        file_path = download_video(url)

        # Send the downloaded file to user
        with open(file_path, 'rb') as file:
            bot.send_document(message.chat.id, file, caption="Here is your downloaded video.")

        # Clean up: remove the downloaded file after sending
        os.remove(file_path)

    except Exception as e:
        bot.reply_to(message, f"Failed to download the video. Error: {e}")

# Main loop to start the bot
if __name__ == '__main__':
    bot.polling()