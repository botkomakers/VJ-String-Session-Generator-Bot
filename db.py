from pymongo import MongoClient
from config import MONGO_DB_URI

client = MongoClient(MONGO_DB_URI)
db = client["universal_video_bot"]
users = db["users"]

def save_user(user_id, name, username):
    users.update_one(
        {"_id": user_id},
        {"$set": {"name": name, "username": username}},
        upsert=True
    )

def has_been_notified(user_id):
    user = users.find_one({"_id": user_id})
    return user and user.get("notified", False)

def set_notified(user_id):
    users.update_one({"_id": user_id}, {"$set": {"notified": True}})



def delete_user(user_id):
    result = users.delete_one({"_id": user_id})
    return result.deleted_count > 0


import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY
)""")
conn.commit()

def add_premium(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def remove_premium(user_id: int):
    cursor.execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_premium():
    cursor.execute("SELECT user_id FROM premium_users")
    return [row[0] for row in cursor.fetchall()]

def is_premium(user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM premium_users WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None