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


from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["downloader_bot"]
premium_col = db["premium_users"]

def add_premium(user_id: int):
    if not premium_col.find_one({"_id": user_id}):
        premium_col.insert_one({"_id": user_id})

def remove_premium(user_id: int):
    premium_col.delete_one({"_id": user_id})

def is_premium(user_id: int) -> bool:
    return premium_col.find_one({"_id": user_id}) is not None

def list_premium_users():
    return [doc["_id"] for doc in premium_col.find()]