# db.py
from pymongo import MongoClient
from config import MONGO_DB_URI

client = MongoClient(MONGO_DB_URI)
db = client['all_in_one_bot']  # Database name
users_collection = db['users']  # Collection name

def save_user(user_id: int, first_name: str, username: str = None):
    user_data = {
        "_id": user_id,
        "first_name": first_name,
        "username": username,
    }
    try:
        users_collection.update_one(
            {"_id": user_id},
            {"$set": user_data},
            upsert=True
        )
    except Exception as e:
        print(f"Failed to save user {user_id}: {e}")