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

def has_been_notified(user_id: int) -> bool:
    return users_collection.find_one({"_id": user_id, "notified": True}) is not None

def set_notified(user_id: int):
    try:
        users_collection.update_one(
            {"_id": user_id},
            {"$set": {"notified": True}}
        )
    except Exception as e:
        print(f"Failed to update notified status for user {user_id}: {e}")