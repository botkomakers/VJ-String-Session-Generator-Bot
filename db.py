from pymongo import MongoClient
from datetime import datetime, timedelta

# MongoDB কনফিগারেশন
client = MongoClient("mongodb+srv://siamkfah48:siamkfah48@cluster0.fbodc0r.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # আপনার MongoDB URI এখানে দিন
db = client['video_downloader']

# রেট লিমিটের জন্য MongoDB কনফিগারেশন
rate_limit_collection = db['rate_limit']  # রেট লিমিট তথ্য সংরক্ষণ

# রেট লিমিট চেক করার ফাংশন
def check_rate_limit(user_id: int, limit: int = 1, window: int = 60):
    """
    রেট লিমিট চেক করে। যদি ইউজার নির্ধারিত লিমিটের বেশি রিকোয়েস্ট করে, তাহলে True ফেরত দেয়।
    :param user_id: ইউজারের আইডি
    :param limit: এক মিনিটে কত রিকোয়েস্ট অনুমোদিত (ডিফল্ট ১)
    :param window: এক মিনিটের সময়সীমা (ডিফল্ট ৬০ সেকেন্ড)
    :return: যদি রেট লিমিট পাস হয় তাহলে True, নয়তো False
    """
    current_time = datetime.utcnow()  # বর্তমান সময়

    # MongoDB তে ইউজারের রেট লিমিট তথ্য খোঁজা
    user_data = rate_limit_collection.find_one({"user_id": user_id})

    if not user_data:
        # ইউজার যদি নতুন হয়, রেট লিমিট কাউন্ট শুরু করুন
        rate_limit_collection.insert_one({
            "user_id": user_id,
            "last_request_time": current_time,
            "request_count": 1,
            "expires_at": current_time + timedelta(seconds=window)
        })
        return False  # নতুন ইউজারের জন্য রেট লিমিট থাকবে না

    # চেক করুন যে, রেট লিমিট পাস হয়েছে কি না
    time_difference = current_time - user_data['last_request_time']
    if time_difference < timedelta(seconds=window):
        if user_data['request_count'] >= limit:
            return True  # রেট লিমিট পাস করেছে
        else:
            # রিকোয়েস্ট কাউন্ট বাড়ান
            rate_limit_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"request_count": 1}},
                upsert=True
            )
            return False  # রেট লিমিট পাস হয়নি
    else:
        # যদি নির্ধারিত সময় পার হয়ে যায়, রিকোয়েস্ট কাউন্ট রিসেট করুন
        rate_limit_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_request_time": current_time, "request_count": 1}},
            upsert=True
        )
        return False  # সময় পার হয়ে গেছে, রেট লিমিট পুনরায় শুরু হবে