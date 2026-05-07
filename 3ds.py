import time
import requests
import json
import re
import os
from datetime import datetime
import sqlite3
import telebot
from telebot import types
import threading
import traceback
from dotenv import load_dotenv

load_dotenv()

# ===========================
# 📌 إعدادات iVASMS (بدون CSRF)
# ===========================
IVASMS_CONFIG = {
    "email": "svdmggr@hi2.in",
    "password": "FirstNameAhmed1#",
    "api_url": "https://www.ivasms.com/api/login",
    "sms_url": "https://www.ivasms.com/api/get-sms",
    "token": None
}

# ===========================
# 🔧 إعدادات البوت
# ===========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN not found")

CHAT_IDS = ["-1002261379064"]
ADMIN_IDS = [6264668799]
REFRESH_INTERVAL = 5
DB_PATH = "bot.db"

# ===========================
# 🌍 رموز الدول
# ===========================
COUNTRY_CODES = {
    "20": ("Egypt", "🇪🇬"),
    "44": ("UK", "🇬🇧"),
    "1": ("USA", "🇺🇸"),
    "964": ("Iraq", "🇮🇶"),
    "966": ("Saudi", "🇸🇦"),
    "971": ("UAE", "🇦🇪"),
}

# ===========================
# 🗄️ قاعدة البيانات
# ===========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        assigned_number TEXT,
        is_banned INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS otp_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT,
        otp TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def save_user(user_id, username=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO users (user_id, username, is_banned) VALUES (?, ?, 0)", (user_id, username))
    conn.commit()
    conn.close()

def get_user_by_number(number):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE assigned_number=?", (number,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def assign_number_to_user(user_id, number):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET assigned_number=? WHERE user_id=?", (number, user_id))
    conn.commit()
    conn.close()

def log_otp(number, otp):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO otp_logs (number, otp, timestamp) VALUES (?, ?, ?)",
              (number, otp, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ===========================
# 🔑 تسجيل الدخول باستخدام API
# ===========================
def login_to_ivasms():
    """تسجيل الدخول عبر API"""
    try:
        print("🔄 محاولة تسجيل الدخول عبر API...")
        
        # استخدام API login
        response = requests.post(IVASMS_CONFIG["api_url"], json={
            "email": IVASMS_CONFIG["email"],
            "password": IVASMS_CONFIG["password"]
        }, headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            IVASMS_CONFIG["token"] = data.get("token") or data.get("access_token")
            if IVASMS_CONFIG["token"]:
                print("✅ تم تسجيل الدخول بنجاح")
                return True
        
        print(f"❌ فشل API login: {response.status_code}")
        return False
        
    except Exception as e:
        print(f"❌ خطأ في login: {e}")
        return False

# ===========================
# 📥 جلب الرسائل
# ===========================
def fetch_messages():
    """جلب الرسائل باستخدام API"""
    if not IVASMS_CONFIG["token"]:
        if not login_to_ivasms():
            return []
    
    try:
        headers = {
            "Authorization": f"Bearer {IVASMS_CONFIG['token']}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(IVASMS_CONFIG["sms_url"], headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            messages = []
            
            # حسب هيكل الـ API
            sms_list = data.get("data", []) or data.get("messages", []) or data.get("sms", [])
            
            for sms in sms_list:
                number = sms.get("number") or sms.get("from") or sms.get("sender")
                text = sms.get("message") or sms.get("text") or sms.get("body")
                date = sms.get("date") or sms.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if number and text:
                    messages.append({
                        "date": date,
                        "number": re.sub(r'\D', '', str(number)),
                        "sms": text
                    })
            
            return messages
            
        elif response.status_code == 401:
            print("⚠️ Token منتهي، إعادة تسجيل الدخول...")
            IVASMS_CONFIG["token"] = None
            return []
        else:
            print(f"❌ فشل جلب الرسائل: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ خطأ في fetch: {e}")
        return []

# ===========================
# 📝 معالجة OTP
# ===========================
def extract_otp(text):
    patterns = [r'\b(\d{4,8})\b', r'code[:\s]*(\d{4,8})', r'otp[:\s]*(\d{4,8})']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "N/A"

def get_country_flag(number):
    for code, (name, flag) in COUNTRY_CODES.items():
        if number.startswith(code):
            return f"{flag} {name}"
    return "🌍 Unknown"

def format_message(number, sms):
    otp = extract_otp(sms)
    masked = number[:4] + "****" + number[-4:] if len(number) > 8 else number
    country = get_country_flag(number)
    
    return f"""📱 <b>OTP Received</b>
━━━━━━━━━━━━━━
📍 {country}
📞 <code>{masked}</code>
🔑 <b>OTP:</b> <code>{otp}</code>
━━━━━━━━━━━━━━
📝 <i>{sms[:150]}</i>""", otp

# ===========================
# 🤖 البوت
# ===========================
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    save_user(message.from_user.id, message.from_user.username or "")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Channel", url="https://t.me/ramoss87"))
    
    bot.send_message(message.chat.id, 
        "✨ <b>iVASMS OTP Bot Active</b>\n\n✅ Monitoring numbers...\n📋 OTPs will appear here",
        parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def copy_otp(call):
    otp = call.data.split("_")[1]
    bot.answer_callback_query(call.id, f"✅ Copied: {otp}", show_alert=True)

def send_otp(formatted, otp, chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 Copy OTP", callback_data=f"copy_{otp}"))
    try:
        bot.send_message(chat_id, formatted, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"❌ Send error: {e}")

# ===========================
# 🚀 Main Loop
# ===========================
sent_cache = set()

def main_loop():
    print("🔄 Main loop started...")
    while True:
        try:
            messages = fetch_messages()
            
            for msg in messages:
                msg_id = f"{msg['number']}_{msg['sms'][:30]}"
                
                if msg_id not in sent_cache:
                    formatted, otp = format_message(msg['number'], msg['sms'])
                    
                    for chat_id in CHAT_IDS:
                        send_otp(formatted, otp, chat_id)
                    
                    user = get_user_by_number(msg['number'])
                    if user:
                        send_otp(formatted, otp, user)
                    
                    log_otp(msg['number'], otp)
                    sent_cache.add(msg_id)
                    print(f"✅ OTP from {msg['number'][:6]}***")
            
            if len(sent_cache) > 500:
                sent_cache = set(list(sent_cache)[-200:])
                
        except Exception as e:
            print(f"❌ Loop error: {e}")
        
        time.sleep(REFRESH_INTERVAL)

def run_bot():
    print("🤖 Bot started...")
    bot.infinity_polling()

if __name__ == "__main__":
    print("="*40)
    print("🚀 Starting iVASMS Bot...")
    print("="*40)
    
    threading.Thread(target=run_bot, daemon=True).start()
    main_loop()
