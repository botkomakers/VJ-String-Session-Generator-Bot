from pymongo import MongoClient
from config import MONGO_DB_URI

client = MongoClient(MONGO_DB_URI)
db = client["video_downloader"]
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