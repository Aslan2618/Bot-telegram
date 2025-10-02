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

# راه‌اندازی سیستم لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---- وب‌سرور برای نگه داشتن ربات همیشه فعال ----
app = Flask('')

@app.route('/')
def home():
    return "✅ ربات تلگرام فعال است!"

@app.route('/status')
def status():
    return {"status": "running", "bot": "telegram_moderation_bot"}

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# دریافت توکن از متغیر محیط
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ توکن ربات یافت نشد! لطفاً BOT_TOKEN را تنظیم کنید.")
    exit(1)

# Admin ID - شناسه کاربری مدیر اصلی ربات
ADMIN_ID = os.getenv("ADMIN_ID")  # می‌توانید شناسه کاربریتان را در Secrets تنظیم کنید
if not ADMIN_ID:
    logger.warning("⚠️ ADMIN_ID تنظیم نشده - برای دریافت گزارش‌ها لطفاً ADMIN_ID را در Secrets تنظیم کنید")
else:
    ADMIN_ID = int(ADMIN_ID)
    logger.info(f"✅ مدیر ربات: {ADMIN_ID}")

# آمار و گزارش‌ها
daily_stats = {
    "deleted_messages": 0,
    "warned_users": 0,
    "banned_users": 0,
    "total_messages_checked": 0
}

# کلمات ممنوعه فارسی و انگلیسی
persian_bad_words = [
    # فحش‌های اصلی فارسی
    "کسکش", "کص کش", "کس کش", "کوس کش", "کوسکش", "کوثکش",
    "کیر", "کیری", "کون", "کونی", "کونده", 
    "جنده", "جندگی", "فاحشه", "زانیه",
    "گاییدم", "گایید", "میگام", "بگام",
    "خارکسده", "خار کسده", "مادرجنده", "مادر جنده",
    "بی شرف", "بیشرف", "حرومزاده", "حروم زاده",
    "لاشی", "لاش", "عوضی", "سگ", "خر"
]

english_bad_words = [
    # فحش‌های انگلیسی
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard",
    "damn", "hell", "crap", "piss", "cock", "dick", "pussy",
    "whore", "slut", "faggot", "nigger", "retard", "stupid"
]

# کلمات مجاز که نباید اشتباه فحش حساب شوند
allowed_words = [
    "این", "سگمنت", "انگلیسی", "گردی", "دکتر", "سگهای", 
    "گلسنگ", "رنگسگ", "کیست", "یکی", "رکورد", "سکه"
]

# شمارش تخلف هر کاربر
user_warnings = defaultdict(int)

def normalize_text(text):
    """متن را نرمال‌سازی می‌کند و نقطه‌ها، فاصله‌ها و حروف اضافی را حذف می‌کند"""
    if not text:
        return ""
    
    # تبدیل به حروف کوچک
    text = text.lower().strip()
    
    # حذف نقطه‌ها، فاصله‌ها، خط تیره‌ها و کاراکترهای غیرضروری
    text = re.sub(r'[.\s\-_\*\@\#\$\%\^\&\(\)\[\]\{\}\|\\\<\>\?\~\`\!\=\+]+', '', text)
    
    # حذف اعداد
    text = re.sub(r'\d+', '', text)
    
    # حذف کاراکترهای تکراری
    text = re.sub(r'(.)\1{2,}', r'\1', text)
    
    return text

def contains_profanity(text):
    """بررسی وجود فحاشی در متن با روش‌های مختلف"""
    if not text:
        return False
    
    original_text = text.lower().strip()
    normalized_text = normalize_text(text)
    
    # ابتدا بررسی کلمات مجاز
    for allowed in allowed_words:
        if allowed in original_text and len(original_text.strip()) <= len(allowed) + 2:
            return False
    
    # بررسی فحش‌های فارسی
    for bad_word in persian_bad_words:
        normalized_bad = normalize_text(bad_word)
        
        # بررسی در متن نرمال‌سازی شده
        if len(normalized_bad) >= 3 and normalized_bad in normalized_text:
            return True
            
        # بررسی در متن اصلی
        if bad_word in original_text:
            return True
            
        # بررسی با regex برای تشخیص کلمات با فاصله/نقطه
        pattern = ''.join([f'{char}[.\s\-_*]*' for char in bad_word])
        if re.search(pattern, original_text):
            return True
    
    # بررسی فحش‌های انگلیسی
    for bad_word in english_bad_words:
        if len(bad_word) >= 3:
            # بررسی مستقیم
            if bad_word in original_text:
                return True
                
            # بررسی با regex
            pattern = ''.join([f'{char}[.\s\-_*]*' for char in bad_word])
            if re.search(pattern, original_text):
                return True
    
    return False

async def send_admin_report(context: ContextTypes.DEFAULT_TYPE, message: str):
    """ارسال گزارش به مدیر"""
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🤖 گزارش ربات:\n{message}")
        except Exception as e:
            logger.error(f"خطا در ارسال گزارش به مدیر: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع و شناسایی مدیر"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "کاربر"
    
    if user_id == ADMIN_ID:
        welcome_msg = f"""
🔑 سلام مدیر عزیز {user_name}!

شما به عنوان مدیر ربات شناسایی شدید.

دستورات مدیریتی:
/admin - پنل مدیریت
/stats - آمار عملکرد ربات
/report - گزارش تفصیلی

ربات در حال محافظت از گروه‌هاست! ✅
        """
    else:
        welcome_msg = f"""
👋 سلام {user_name}!

من ربات مدیریت گروه هستم.
وظیفه من نظارت بر گروه‌ها و حذف پیام‌های نامناسب است.

برای اضافه کردن به گروه، مدیر گروه باید:
1. من را به گروه اضافه کند
2. مجوز حذف پیام بدهد
3. مجوز محدود کردن کاربران بدهد

🐛 گزارش مشکل:
اگر مشکلی با عملکرد ربات دارید، از دستور /bug استفاده کنید.

بعد از آن، خودکار شروع به کار می‌کنم! 🤖
        """
    
    await update.message.reply_text(welcome_msg)
    
    # گزارش دسترسی جدید به مدیر
    if user_id != ADMIN_ID and ADMIN_ID:
        report = f"📋 کاربر جدید ربات را شروع کرد:\n👤 نام: {user_name}\n🆔 شناسه: {user_id}"
        await send_admin_report(context, report)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل مدیریت (فقط برای مدیر)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ شما مجوز دسترسی به این دستور را ندارید.")
        return
    
    admin_panel = f"""
🔧 پنل مدیریت ربات

📊 آمار امروز:
• پیام‌های حذف شده: {daily_stats['deleted_messages']}
• کاربران اخطار گرفته: {daily_stats['warned_users']} 
• کاربران محدود شده: {daily_stats['banned_users']}
• کل پیام‌های بررسی شده: {daily_stats['total_messages_checked']}

⚡ وضعیت ربات: فعال ✅
🌐 وب‌سرور: آنلاین ✅

دستورات:
/stats - آمار تفصیلی
/report - گزارش کامل
    """
    
    await update.message.reply_text(admin_panel)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار (فقط برای مدیر)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ شما مجوز دسترسی به این دستور را ندارید.")
        return
    
    total_warnings = sum(user_warnings.values())
    active_users = len(user_warnings)
    
    stats_msg = f"""
📈 آمار تفصیلی ربات

🗓️ آمار امروز:
• پیام‌های نامناسب حذف شده: {daily_stats['deleted_messages']}
• کاربران اخطار گرفته: {daily_stats['warned_users']}
• کاربران محدود شده: {daily_stats['banned_users']}
• کل پیام‌های بررسی شده: {daily_stats['total_messages_checked']}

👥 آمار کلی:
• کل اخطارها: {total_warnings}
• کاربران فعال تحت نظر: {active_users}

🔄 وضعیت سیستم:
• ربات: فعال ✅
• وب‌سرور: آنلاین ✅
• تشخیص فحش: فعال ✅
    """
    
    await update.message.reply_text(stats_msg)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش کامل سیستم (فقط برای مدیر)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ شما مجوز دسترسی به این دستور را ندارید.")
        return
    
    # آمار تفصیلی کاربران
    warning_details = ""
    if user_warnings:
        warning_details = "\n👥 جزئیات اخطارها:\n"
        for uid, warnings in list(user_warnings.items())[:10]:  # نمایش 10 کاربر اول
            warning_details += f"• کاربر {uid}: {warnings} اخطار\n"
        if len(user_warnings) > 10:
            warning_details += f"... و {len(user_warnings) - 10} کاربر دیگر\n"
    
    report_msg = f"""
📋 گزارش کامل ربات مدیریت

📊 عملکرد:
• کارایی: {((daily_stats['deleted_messages'] / max(daily_stats['total_messages_checked'], 1)) * 100):.1f}% پیام‌های نامناسب شناسایی شده
• میانگین اخطار: {(sum(user_warnings.values()) / max(len(user_warnings), 1)):.1f} اخطار به ازای هر کاربر

{warning_details}

🔧 تنظیمات فعال:
• کلمات فارسی: {len(persian_bad_words)} کلمه
• کلمات انگلیسی: {len(english_bad_words)} کلمه
• کلمات مجاز: {len(allowed_words)} کلمه

⚙️ سیستم:
• نرمال‌سازی متن: فعال ✅
• تشخیص با نقطه/فاصله: فعال ✅
• گزارش‌دهی خودکار: فعال ✅
    """
    
    await update.message.reply_text(report_msg)

async def bug_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش مشکل از طرف کاربران"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "کاربر"
    
    # دریافت متن گزارش
    if not context.args:
        help_msg = """
🐛 گزارش مشکل

برای گزارش مشکل از دستور زیر استفاده کنید:
/bug متن گزارش شما

مثال:
/bug ربات پیام من را اشتباه حذف کرد

گزارش شما به مدیر ارسال خواهد شد.
        """
        await update.message.reply_text(help_msg)
        return
    
    # جمع‌آوری متن گزارش
    bug_text = " ".join(context.args)
    
    # ارسال تأیید به کاربر
    confirmation_msg = """
✅ گزارش شما دریافت شد!

گزارش شما به مدیر ارسال گردید و بررسی خواهد شد.
ممنون از همکاری‌تان! 🙏
    """
    await update.message.reply_text(confirmation_msg)
    
    # ارسال گزارش به مدیر
    if ADMIN_ID:
        admin_report = f"""
🐛 گزارش مشکل جدید:

👤 از طرف: {user_name} (ID: {user_id})
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}
📝 گزارش: {bug_text}

💬 برای پاسخ: می‌توانید مستقیماً به کاربر پیام دهید.
        """
        await send_admin_report(context, admin_report)
    
    logger.info(f"گزارش مشکل از {user_name}: {bug_text[:100]}...")

async def check_bad_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی پیام‌ها برای کلمات ممنوعه"""
    if not update.message or not update.message.from_user or not update.message.text:
        return
        
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name or "کاربر"
    text = update.message.text
    chat_id = update.message.chat_id
    
    # به‌روزرسانی آمار
    daily_stats["total_messages_checked"] += 1

    # بررسی وجود فحاشی
    if contains_profanity(text):
        user_warnings[user_id] += 1
        daily_stats["deleted_messages"] += 1
        
        # گزارش به مدیر در صورت اولین تخلف کاربر
        if user_warnings[user_id] == 1:
            daily_stats["warned_users"] += 1
            admin_report = f"🚨 تخلف جدید:\n👤 {user_name} (ID: {user_id})\n💬 گروه: {chat_id}\n📝 پیام: {text[:100]}..."
            await send_admin_report(context, admin_report)
        
        try:
            # حذف پیام
            await update.message.delete()
            logger.info(f"پیام نامناسب از {user_name} حذف شد: '{text[:50]}...'")
        except Exception as e:
            logger.error(f"خطا در حذف پیام: {e}")

        # ارسال اخطار
        try:
            if user_warnings[user_id] == 1:
                warning_msg = f"⚠️ {user_name} اخطار اول! لطفاً از کلمات نامناسب استفاده نکنید."
            elif user_warnings[user_id] == 2:
                warning_msg = f"🔶 {user_name} اخطار دوم! رعایت احترام کنید."
            elif user_warnings[user_id] == 3:
                warning_msg = f"🔴 {user_name} اخطار سوم! اخطار نهایی."
            else:
                warning_msg = f"⚠️ {user_name} پیام نامناسب حذف شد. اخطار #{user_warnings[user_id]}"
            
            sent_msg = await context.bot.send_message(chat_id=chat_id, text=warning_msg)
            
            # حذف پیام اخطار بعد از 5 ثانیه
            await asyncio.sleep(5)
            try:
                await sent_msg.delete()
            except:
                pass
                
        except Exception as e:
            logger.error(f"خطا در ارسال اخطار: {e}")

        # اگر ۴ بار تکرار شد → یک روز محدود می‌شود
        if user_warnings[user_id] >= 4:
            daily_stats["banned_users"] += 1
            
            # گزارش محدودسازی به مدیر
            ban_report = f"🔒 کاربر محدود شد:\n👤 {user_name} (ID: {user_id})\n💬 گروه: {chat_id}\n⚠️ علت: ۴ تخلف"
            await send_admin_report(context, ban_report)
            
            try:
                # محدود کردن کاربر برای یک روز
                restrict_until = datetime.now() + timedelta(days=1)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False
                    ),
                    until_date=restrict_until
                )
                
                ban_msg = f"🚫 {user_name} به دلیل تکرار تخلف برای ۱ روز محدود شد."
                ban_sent = await context.bot.send_message(chat_id=chat_id, text=ban_msg)
                
                # حذف پیام بن بعد از 10 ثانیه
                await asyncio.sleep(10)
                try:
                    await ban_sent.delete()
                except:
                    pass
                
                # ری‌ست کردن شمارنده
                user_warnings[user_id] = 0
                
                logger.info(f"کاربر {user_name} محدود شد")
                
            except Exception as e:
                error_msg = f"❌ خطا در محدود کردن کاربر: {e}"
                await context.bot.send_message(chat_id=chat_id, text=error_msg)
                logger.error(f"خطا در محدود کردن کاربر: {e}")
                
                # گزارش خطا به مدیر
                error_report = f"❌ خطا در محدودسازی:\n👤 {user_name}\n🔧 خطا: {str(e)}"
                await send_admin_report(context, error_report)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت خطاها"""
    logger.warning(f'خطا در به‌روزرسانی: {update}')
    logger.error(f'خطا: {context.error}')
    
    # گزارش خطاهای مهم به مدیر
    if ADMIN_ID and context.error:
        error_report = f"🔥 خطای سیستم:\n🛠️ {str(context.error)[:200]}..."
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🤖 گزارش ربات:\n{error_report}")
        except:
            pass  # جلوگیری از لوپ بی‌نهایت خطا

def main():
    """اجرای اصلی ربات"""
    # شروع وب‌سرور برای نگه داشتن ربات فعال
    keep_alive()
    
    # ساخت اپلیکیشن
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن command handlerها
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("bug", bug_report_command))
    
    # اضافه کردن هندلر برای پیام‌های متنی (غیر از کامندها)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, check_bad_words)
    )
    
    # اضافه کردن هندلر خطا
    application.add_error_handler(error_handler)
    
    logger.info("✅ ربات و وب‌سرور شروع به کار کردند...")
    logger.info("🌐 وب‌سرور در آدرس http://0.0.0.0:5000 فعال است")
    if ADMIN_ID:
        logger.info(f"👤 مدیر ربات: {ADMIN_ID}")
    
    # اجرای ربات
    application.run_polling(allowed_updates=Update.ALL_TYPES)
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=5000)

def keep_alive():
    t = Thread(target=run)
    t.start()
if __name__ == "__main__":
    try:
        keep_alive()   # ✅ این خط وب‌سرور رو فعال نگه می‌داره
        main()
    except KeyboardInterrupt:
        logger.info("ربات متوقف شد.")
    except Exception as e:
        logger.error(f"خطا در اجرای ربات: {e}")
        # تلاش برای ادامه اجرا
        import time
        time.sleep(5)
        main()
