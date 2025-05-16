from os import environ
import os


LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", -1002589776901))

COOKIE_FILE = "cookies.txt"  # path to cookies file

ADMINS = int(os.environ.get("ADMINS", 7862181538))

ADMIN_ID = 7862181538          # Replace with your admin user ID



# Telegram Account Api Id And Api Hash
API_ID = int(environ.get("API_ID", "20591811"))
API_HASH = environ.get("API_HASH", "")
DOWNLOAD_DIR = "downloads"
# Your Main Bot Token 
BOT_TOKEN = environ.get("BOT_TOKEN", "6631772048:AAF4AoHOssXJqYMee6oJ_e2C9onB555GipE")

# Owner ID For Broadcasting 
OWNER_ID = int(environ.get("OWNER_ID", "7862181538")) # Owner Id or Admin Id

# Give Your Force Subscribe Channel Id Below And Make Bot Admin With Full Right.
F_SUB = environ.get("F_SUB", "")

# Mongodb Database Uri For User Data Store 
MONGO_DB_URI = environ.get("MONGO_DB_URI", "mongodb+srv://siamkfah48:siamkfah48@cluster0.fbodc0r.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# Port To Run Web Application 
PORT = int(environ.get('PORT', 8080))


import os

class temp:
    DOWNLOAD_DIR = "./downloads"






