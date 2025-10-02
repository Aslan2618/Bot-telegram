#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

# ---- سیستم لاگ ----
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---- وب‌سرور Flask برای روشن ماندن ----
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ ربات تلگرام فعال است!"

@app.route('/status')
def status():
    return {"status": "running"}

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ---- دریافت توکن و آیدی مدیر از Environment Variable ----
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    logger.error("❌ BOT_TOKEN تعریف نشده. در Render → Environment Variable باید اضافه کنی.")
    raise SystemExit("BOT_TOKEN not set")

if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except:
        logger.error("❌ ADMIN_ID باید عددی باشه")
        raise SystemExit("ADMIN_ID must be integer")
else:
    ADMIN_ID = None
    logger.warning("⚠️ ADMIN_ID تنظیم نشده. گزارش‌ها به کسی ارسال نمی‌شن.")

# ---- آمار ----
daily_stats = {
    "deleted_messages": 0,
    "warned_users": 0,
    "banned_users": 0,
    "total_messages_checked": 0
}
user_warnings = defaultdict(int)

# ---- لیست کلمات ----
persian_bad_words = ["کیر","کونی","جنده","کسکش","بیشرف","حرومزاده"]
english_bad_words = ["fuck","shit","bitch","asshole","bastard","pussy"]
allowed_words = ["سگمنت","دکتر","کیست","یکی"]

# ---- توابع ----
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[.\s\-_*]+', '', text)
    return text

def contains_profanity(text: str) -> bool:
    if not text:
        return False
    normalized = normalize_text(text)
    for bad in persian_bad_words + english_bad_words:
        if normalize_text(bad) in normalized:
            return True
    return False

async def send_admin_report(context, message: str):
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🤖 گزارش ربات:\n{message}")
        except Exception as e:
            logger.error(f"خطا در ارسال گزارش به مدیر: {e}")

# ---- دستورات ----
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! ربات مدیریت گروه فعال است ✅")

async def check_bad_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name or "کاربر"
    chat_id = update.message.chat_id

    daily_stats["total_messages_checked"] += 1

    if contains_profanity(text):
        user_warnings[user_id] += 1
        daily_stats["deleted_messages"] += 1
        try:
            await update.message.delete()
        except:
            pass

        warn_msg = f"⚠️ {user_name} لطفاً از کلمات نامناسب استفاده نکنید! اخطار #{user_warnings[user_id]}"
        sent = await context.bot.send_message(chat_id=chat_id, text=warn_msg)
        await asyncio.sleep(5)
        try:
            await sent.delete()
        except:
            pass

        if user_warnings[user_id] >= 4:
            daily_stats["banned_users"] += 1
            try:
                restrict_until = datetime.now() + timedelta(days=1)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=restrict_until
                )
                await context.bot.send_message(chat_id=chat_id, text=f"🚫 {user_name} به مدت ۱ روز محدود شد.")
                user_warnings[user_id] = 0
            except Exception as e:
                logger.error(f"خطا در محدود کردن کاربر: {e}")

# ---- خطاها ----
async def error_handler(update, context):
    logger.error(f"خطا: {context.error}")

# ---- اجرای اصلی ----
def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_bad_words))
    application.add_error_handler(error_handler)
    logger.info("🤖 ربات شروع شد...")
    application.run_polling()

if __name__ == "__main__":
    main()
