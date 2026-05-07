import time
import requests
import json
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import telebot
from telebot import types
import threading
import traceback
import random
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ===========================
# 📌 إعدادات حساب iVASMS
# ===========================
IVASMS_CONFIG = {
    "email": "svdmggr@hi2.in",   # امسح واكتب بريدك الحقيقي
    "password": "FirstNameAhmed1#", # امسح واكتب باسوردك الحقيقي
    "login_url": "https://www.ivasms.com/login",
    "messages_url": "https://www.ivasms.com/portal/sms/received",
    "session": None,
    "logged_in": False
}

# ===========================
# 🔧 إعدادات البوت
# ===========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN not found in .env file")

CHAT_IDS = [
    "-1002261379064",  # ايدي القروب
]

ADMIN_IDS = [6264668799]  # ايدي المطور

REFRESH_INTERVAL = 5
SENT_MESSAGES_FILE = "sent_messages.json"
DB_PATH = "bot.db"

# ===========================
# 🌍 رموز الدول
# ===========================
COUNTRY_CODES = {
    "20": ("Egypt", "🇪🇬", "EG"),
    "44": ("United Kingdom", "🇬🇧", "UK"),
    "1": ("USA/Canada", "🇺🇸", "US"),
    "49": ("Germany", "🇩🇪", "DE"),
    "33": ("France", "🇫🇷", "FR"),
    "34": ("Spain", "🇪🇸", "ES"),
    "39": ("Italy", "🇮🇹", "IT"),
    "7": ("Russia", "🇷🇺", "RU"),
    "91": ("India", "🇮🇳", "IN"),
    "92": ("Pakistan", "🇵🇰", "PK"),
    "966": ("Saudi Arabia", "🇸🇦", "SA"),
    "971": ("UAE", "🇦🇪", "AE"),
    "964": ("Iraq", "🇮🇶", "IQ"),
    "965": ("Kuwait", "🇰🇼", "KW"),
    "20": ("Egypt", "🇪🇬", "EG"),
    "212": ("Morocco", "🇲🇦", "MA"),
    "216": ("Tunisia", "🇹🇳", "TN"),
    "90": ("Turkey", "🇹🇷", "TR"),
    "966": ("Saudi", "🇸🇦", "SA"),
    "971": ("UAE", "🇦🇪", "AE"),
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
        first_name TEXT,
        last_name TEXT,
        assigned_number TEXT,
        is_banned INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS otp_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT,
        otp TEXT,
        full_message TEXT,
        timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS combos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country_code TEXT,
        numbers TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_user(user_id, username="", first_name="", last_name="", assigned_number=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO users (user_id, username, first_name, last_name, assigned_number, is_banned) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT is_banned FROM users WHERE user_id=?), 0))",
              (user_id, username, first_name, last_name, assigned_number, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def assign_number_to_user(user_id, number):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET assigned_number=? WHERE user_id=?", (number, user_id))
    conn.commit()
    conn.close()

def get_user_by_number(number):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE assigned_number=?", (number,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def log_otp(number, otp, full_message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO otp_logs (number, otp, full_message, timestamp) VALUES (?, ?, ?, ?)",
              (number, otp, full_message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def release_number(old_number):
    if not old_number:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET assigned_number=NULL WHERE assigned_number=?", (old_number,))
    conn.commit()
    conn.close()

# ===========================
# 🔑 تسجيل الدخول لـ iVASMS
# ===========================
def login_to_ivasms():
    """تسجيل الدخول إلى iVASMS"""
    try:
        session = requests.Session()
        
        # جلب صفحة الدخول لاستخراج CSRF token
        response = session.get(IVASMS_CONFIG["login_url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # استخراج CSRF token
        csrf_token = None
        token_input = soup.find('input', {'name': '_token'})
        if token_input:
            csrf_token = token_input.get('value')
        
        if not csrf_token:
            print("❌ لم يتم العثور على CSRF token")
            return False
        
        # إرسال بيانات الدخول
        login_data = {
            'email': IVASMS_CONFIG["email"],
            'password': IVASMS_CONFIG["password"],
            '_token': csrf_token
        }
        
        login_response = session.post(IVASMS_CONFIG["login_url"], data=login_data)
        
        # التحقق من نجاح الدخول
        if "dashboard" in login_response.url or login_response.status_code == 200:
            IVASMS_CONFIG["session"] = session
            IVASMS_CONFIG["logged_in"] = True
            print("✅ تسجيل الدخول إلى iVASMS ناجح")
            return True
        else:
            print(f"❌ فشل تسجيل الدخول: {login_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ خطأ في تسجيل الدخول: {e}")
        return False

# ===========================
# 📥 جلب الرسائل من iVASMS
# ===========================
def fetch_ivasms_messages():
    """جلب أحدث الرسائل"""
    if not IVASMS_CONFIG["logged_in"]:
        if not login_to_ivasms():
            return []
    
    try:
        session = IVASMS_CONFIG["session"]
        response = session.get(IVASMS_CONFIG["messages_url"])
        
        if response.status_code != 200:
            IVASMS_CONFIG["logged_in"] = False
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        messages = []
        
        # البحث عن جدول الرسائل
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows[1:]:  # تخطي رأس الجدول
                cols = row.find_all('td')
                if len(cols) >= 3:
                    date = cols[0].text.strip()
                    number = cols[1].text.strip()
                    sms_text = cols[2].text.strip()
                    
                    # تنظيف رقم الهاتف
                    number = re.sub(r'\D', '', number)
                    
                    if number and sms_text:
                        messages.append({
                            "date": date,
                            "number": number,
                            "sms": sms_text
                        })
        
        return messages
        
    except Exception as e:
        print(f"❌ خطأ في جلب الرسائل: {e}")
        return []

# ===========================
# 📝 معالجة الرسائل
# ===========================
def clean_number(number):
    return re.sub(r'\D', '', str(number))

def extract_otp(message):
    """استخراج رمز OTP من الرسالة"""
    patterns = [
        r'(?:code|verification|otp|pin)[:\s]*(\d{4,8})',
        r'(\d{5,6})',
        r'\b(\d{4,8})\b'
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return "N/A"

def get_country_info(number):
    """تحديد الدولة من الرقم"""
    number = str(number)
    for code, (name, flag, short) in COUNTRY_CODES.items():
        if number.startswith(code):
            return name, flag, short
    return "Unknown", "🌍", "UN"

def format_message(number, sms):
    """تنسيق الرسالة للإرسال"""
    country_name, flag, _ = get_country_info(number)
    otp = extract_otp(sms)
    masked_number = number[:4] + "****" + number[-3:] if len(number) > 8 else number
    
    text = (
        f"📱 <b>New OTP Received</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>Country:</b> {flag} {country_name}\n"
        f"📞 <b>Number:</b> <code>{masked_number}</code>\n"
        f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Full Message:</b>\n<code>{sms[:200]}</code>"
    )
    return text, otp

# ===========================
# 🤖 البوت
# ===========================
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not get_user(user_id):
        save_user(user_id, message.from_user.username or "", message.from_user.first_name or "", message.from_user.last_name or "")
    
    welcome_text = (
        "✨ <b>Welcome to iVASMS OTP Bot</b> ✨\n\n"
        "🤖 <b>I will forward all OTP messages received on your iVASMS numbers</b>\n\n"
        "📌 <b>Features:</b>\n"
        "• Automatic OTP detection\n"
        "• One-click copy OTP\n"
        "• Real-time forwarding\n\n"
        "✅ Bot is active and monitoring..."
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Join Channel", url="https://t.me/ramoss87"))
    
    bot.send_message(chat_id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def handle_copy(call):
    otp = call.data.split("_")[1]
    bot.answer_callback_query(call.id, f"✅ Copied: {otp}", show_alert=True)

# ===========================
# 📤 إرسال الرسائل
# ===========================
def send_to_telegram(formatted_text, otp, chat_id):
    """إرسال رسالة للتليجرام"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 Copy OTP", callback_data=f"copy_{otp}"))
    
    try:
        bot.send_message(chat_id, formatted_text, parse_mode="HTML", reply_markup=markup)
        return True
    except Exception as e:
        print(f"❌ فشل الإرسال لـ {chat_id}: {e}")
        return False

# ===========================
# 🚀 الحلقة الرئيسية
# ===========================
def load_sent_messages():
    if os.path.exists(SENT_MESSAGES_FILE):
        try:
            with open(SENT_MESSAGES_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent_messages(sent_set):
    with open(SENT_MESSAGES_FILE, 'w') as f:
        json.dump(list(sent_set), f)

def main_loop():
    print("🔄 Main loop started...")
    sent_messages = load_sent_messages()
    
    while True:
        try:
            messages = fetch_ivasms_messages()
            
            for msg in messages:
                msg_hash = f"{msg['date']}_{msg['number']}_{msg['sms'][:50]}"
                
                if msg_hash not in sent_messages:
                    formatted, otp = format_message(msg['number'], msg['sms'])
                    
                    # إرسال للقنوات
                    for chat_id in CHAT_IDS:
                        send_to_telegram(formatted, otp, chat_id)
                    
                    # إرسال للمستخدم المخصص
                    user_id = get_user_by_number(msg['number'])
                    if user_id:
                        send_to_telegram(formatted, otp, user_id)
                    
                    log_otp(msg['number'], otp, msg['sms'])
                    sent_messages.add(msg_hash)
                    print(f"✅ New OTP: {msg['number'][:6]}*** -> {otp}")
            
            if len(sent_messages) > 1000:
                sent_messages = set(list(sent_messages)[-500:])
            
            save_sent_messages(sent_messages)
            
        except Exception as e:
            print(f"❌ Main loop error: {e}")
            traceback.print_exc()
        
        time.sleep(REFRESH_INTERVAL)

def run_bot():
    print("🤖 Bot started...")
    bot.infinity_polling()

# ===========================
# ▶️ تشغيل البوت
# ===========================
if __name__ == "__main__":
    print("="*40)
    print("🚀 iVASMS OTP Bot by RAMOS")
    print("="*40)
    
    # بدء تشغيل البوت في خيط منفصل
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # بدء الحلقة الرئيسية
    main_loop()
