from telegram import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta
import re
import sqlite3
from src.utils import db
from src.utils.logger import print_status  # إضافة استيراد print_status
from src.bot.verification_logic import verify_transaction, ALLOWED_SENDER
from src.bot.reports import generate_report
import os

# حالات المستخدم
class FSMState:
    IDLE = 'idle'
    WAIT_AMOUNT = 'wait_amount'
    WAIT_DATE = 'wait_date'
    WAIT_CUSTOM_DATE = 'wait_custom_date'
    WAIT_TIME = 'wait_time'
    CONFIRM = 'confirm'
    WAIT_REPORT_PERIOD = 'wait_report_period'
    SHOW_PROFILE = 'show_profile'  # حالة جديدة لعرض المعلومات الشخصية

# جلسات المستخدمين
user_sessions = {}

# القائمة الرئيسية
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ['👤 معلوماتي الشخصية'],
        ['🧾 تحقق من العملية'],
        ['📊 تقارير العمليات']
    ],
    resize_keyboard=True
)

# قائمة فترات التقارير
REPORT_PERIODS = ReplyKeyboardMarkup(
    [
        ['آخر 24 ساعة', 'آخر 3 أيام'],
        ['آخر 7 أيام', 'آخر شهر'],
        ['كل العمليات'],
        ['رجوع للقائمة الرئيسية']
    ],
    resize_keyboard=True
)

def send_main_menu(bot, chat_id):
    try:
        bot.send_message(
            chat_id=chat_id,
            text="اختر من القائمة:",
            reply_markup=MAIN_MENU
        )
        user_sessions[chat_id] = {'state': FSMState.IDLE}
    except Exception as e:
        print(f"Error sending main menu: {e}")

def start_verification(bot, chat_id):
    user_sessions[chat_id] = {'state': FSMState.WAIT_AMOUNT}
    bot.send_message(
        chat_id=chat_id,
        text="💰 أدخل مبلغ العملية (مثال: 1400):",
        reply_markup=ReplyKeyboardMarkup([['إلغاء']], resize_keyboard=True, one_time_keyboard=True)
    )

def handle_user_message(update, bot):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    session = user_sessions.get(chat_id, {'state': FSMState.IDLE})
    state = session['state']

    if text == 'إلغاء':
        send_main_menu(bot, chat_id)
        return

    if state == FSMState.IDLE:
        if text == '👤 معلوماتي الشخصية':
            show_profile(bot, chat_id)
        elif text == '🧾 تحقق من العملية':
            start_verification(bot, chat_id)
        elif text == '📊 تقارير العمليات':
            show_report_periods(bot, chat_id)
        else:
            send_main_menu(bot, chat_id)

    elif state == FSMState.WAIT_AMOUNT:
        if not text.isdigit():
            bot.send_message(chat_id=chat_id, text="❌ المبلغ غير صالح. أدخل رقم فقط (مثال: 1400):")
            return
        session['amount'] = text
        session['state'] = FSMState.WAIT_DATE
        user_sessions[chat_id] = session
        show_date_keyboard(bot, chat_id)

    elif state == FSMState.WAIT_DATE:
        if text == '📆 اليوم':
            session['date'] = datetime.now().strftime('%d/%m/%Y')
            session['state'] = FSMState.WAIT_TIME
            user_sessions[chat_id] = session
            ask_time(bot, chat_id)
        elif text == '📆 أمس':
            session['date'] = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
            session['state'] = FSMState.WAIT_TIME
            user_sessions[chat_id] = session
            ask_time(bot, chat_id)
        elif text == '🗓️ تاريخ آخر':
            session['state'] = FSMState.WAIT_CUSTOM_DATE
            user_sessions[chat_id] = session
            bot.send_message(chat_id=chat_id, text="📅 أدخل التاريخ بصيغة DD/MM/YYYY:")
        else:
            bot.send_message(chat_id=chat_id, text="❌ يرجى اختيار تاريخ من الأزرار.")
            show_date_keyboard(bot, chat_id)

    elif state == FSMState.WAIT_CUSTOM_DATE:
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', text):
            bot.send_message(chat_id=chat_id, text="❌ التاريخ غير صالح. أدخل بصيغة DD/MM/YYYY:")
            return
        session['date'] = text
        session['state'] = FSMState.WAIT_TIME
        user_sessions[chat_id] = session
        ask_time(bot, chat_id)

    elif state == FSMState.WAIT_TIME:
        parsed_time = parse_time(text)
        if not parsed_time:
            bot.send_message(chat_id=chat_id, text="❌ الوقت غير صالح. أدخل بصيغة 17:56 أو 5:56 PM:")
            return
        session['time'] = parsed_time
        session['state'] = FSMState.CONFIRM
        user_sessions[chat_id] = session
        show_summary(bot, chat_id, session)

    elif state == FSMState.CONFIRM:
        if text == 'تأكيد':
            bot.send_message(chat_id=chat_id, text="جاري التحقق...", reply_markup=ReplyKeyboardMarkup([['إلغاء']], resize_keyboard=True, one_time_keyboard=True))
            # هنا ضع منطق التحقق الفعلي
            result = real_verify(session, telegram_id=chat_id)
            bot.send_message(chat_id=chat_id, text=result)
            send_main_menu(bot, chat_id)
        elif text == 'إلغاء':
            send_main_menu(bot, chat_id)
        else:
            bot.send_message(chat_id=chat_id, text="يرجى الضغط على تأكيد أو إلغاء.")
            show_summary(bot, chat_id, session)
    elif state == FSMState.WAIT_REPORT_PERIOD:
        handle_report_period(bot, chat_id, text)
    else:
        send_main_menu(bot, chat_id)

def show_date_keyboard(bot, chat_id):
    keyboard = ReplyKeyboardMarkup(
        [
            ['📆 اليوم', '📆 أمس'],
            ['🗓️ تاريخ آخر'],
            ['إلغاء']
        ], resize_keyboard=True, one_time_keyboard=True
    )
    bot.send_message(chat_id=chat_id, text="📅 اختر التاريخ:", reply_markup=keyboard)

def ask_time(bot, chat_id):
    bot.send_message(chat_id=chat_id, text="⏰ أدخل وقت العملية (مثال: 17:56 أو 5:56 PM):", reply_markup=ReplyKeyboardMarkup([['إلغاء']], resize_keyboard=True, one_time_keyboard=True))

def show_summary(bot, chat_id, session):
    summary = f"""
💰 المبلغ: {session['amount']}
📅 التاريخ: {session['date']}
⏰ الوقت: {session['time']}
"""
    keyboard = ReplyKeyboardMarkup(
        [['تأكيد', 'إلغاء']], resize_keyboard=True, one_time_keyboard=True
    )
    bot.send_message(chat_id=chat_id, text=summary + "\nهل تريد المتابعة؟", reply_markup=keyboard)

def parse_time(text):
    # يقبل 17:56 أو 5:56 PM أو 5:56 am
    text = text.strip().lower().replace('ص', 'am').replace('م', 'pm')
    try:
        if re.match(r'^\d{1,2}:\d{2}\s*(am|pm)?$', text):
            if 'am' in text or 'pm' in text:
                t = datetime.strptime(text, '%I:%M %p')
            else:
                t = datetime.strptime(text, '%H:%M')
            return t.strftime('%H:%M')
    except Exception:
        pass
    return None

def real_verify(data, telegram_id=None):
    """
    تحقق فعلي من قاعدة البيانات مع تسجيل كل عملية تحقق (نجاح أو فشل)
    """
    try:
        amount = str(data['amount'])
        date_str = data['date']
        time_str = data['time']
        user_id = None
        
        # الحصول على user_id من telegram_id
        if telegram_id:
            user = db.get_user_by_telegram_id(str(telegram_id))
            if user:
                user_id = user[0]
        
        # التحقق من صحة التاريخ والوقت
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
        except Exception:
            if user_id:  # تسجيل فشل محاولة بسبب خطأ في التاريخ
                db.add_verification(user_id, None, 'failed')
            return "❌ خطأ في صيغة التاريخ أو الوقت."
        
        # حساب نطاق البحث (10 دقائق قبل وبعد)
        start_dt = dt - timedelta(minutes=10)
        end_dt = dt + timedelta(minutes=10)
        start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect(db.DB_PATH)
        c = conn.cursor()
        try:
            c.execute('''SELECT id, sender, received_date, content FROM sms 
                WHERE sender = ? AND content LIKE ? AND received_date BETWEEN ? AND ?''',
                (ALLOWED_SENDER, f"%{amount}%", start_str, end_str))
            row = c.fetchone()
            
            if row:
                # نجاح: وجدنا الرسالة
                sms_id, sender, received_date, content = row
                if user_id:  # تسجيل نجاح العملية مع ربطها بالرسالة
                    db.add_verification(user_id, sms_id, 'success')
                return f"✅ تم العثور على العملية!\nالمبلغ: {amount}\nالتاريخ: {date_str}\nالوقت: {time_str}\nالمرسل: {sender}\nالرسالة: {content}"
            else:
                # فشل: لم نجد الرسالة
                if user_id:  # تسجيل فشل محاولة التحقق
                    db.add_verification(user_id, None, 'failed')
                return "❌ لم يتم العثور على عملية مطابقة. تأكد من البيانات أو حاول تغيير الوقت بدقائق قليلة."
        finally:
            conn.close()
    except Exception as e:
        if user_id:  # تسجيل فشل بسبب خطأ غير متوقع
            db.add_verification(user_id, None, 'failed')
        return f"❌ حدث خطأ أثناء التحقق: {str(e)}"

def show_report_periods(bot, chat_id):
    """عرض خيارات فترات التقارير"""
    user_sessions[chat_id] = {'state': FSMState.WAIT_REPORT_PERIOD}
    bot.send_message(
        chat_id=chat_id,
        text="📊 اختر الفترة الزمنية للتقرير:",
        reply_markup=REPORT_PERIODS
    )

def handle_report_period(bot, chat_id, text):
    """معالجة اختيار فترة التقرير"""
    # التحقق من زر العودة
    if text == 'رجوع للقائمة الرئيسية':
        send_main_menu(bot, chat_id)
        return

    period_map = {
        'آخر 24 ساعة': '1',
        'آخر 3 أيام': '3',
        'آخر 7 أيام': '7',
        'آخر شهر': '30',
        'كل العمليات': 'all'
    }
    
    period = period_map.get(text)
    if not period:
        bot.send_message(
            chat_id=chat_id, 
            text="❌ يرجى اختيار فترة صحيحة من القائمة",
            reply_markup=REPORT_PERIODS
        )
        return

    bot.send_message(
        chat_id=chat_id,
        text="🔄 جاري إنشاء التقرير...",
        reply_markup=ReplyKeyboardMarkup([['إلغاء']], resize_keyboard=True)
    )
    
    try:
        # إنشاء التقرير
        pdf_path, message = generate_report(period)
        
        if pdf_path and os.path.exists(pdf_path):
            # إرسال ملف PDF
            with open(pdf_path, 'rb') as pdf:
                bot.send_document(
                    chat_id=chat_id,
                    document=pdf,
                    caption=message,
                    filename=f"تقرير_العمليات_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                )
            # حذف الملف بعد إرساله
            try:
                os.remove(pdf_path)
            except Exception as e:
                print_status(f"خطأ في حذف ملف التقرير: {e}", "WARNING")
            
            # العودة للقائمة الرئيسية بعد نجاح إرسال التقرير
            send_main_menu(bot, chat_id)
        else:
            # في حالة عدم وجود بيانات أو حدوث خطأ
            bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=REPORT_PERIODS
            )
            
    except Exception as e:
        print_status(f"خطأ في إنشاء أو إرسال التقرير: {e}", "ERROR")
        bot.send_message(
            chat_id=chat_id,
            text="❌ عذراً، حدث خطأ أثناء إنشاء التقرير. يرجى المحاولة مرة أخرى.",
            reply_markup=REPORT_PERIODS
        )
    
def show_profile_info(bot, chat_id):
    """عرض المعلومات الشخصية للمستخدم"""
    user = db.get_user_by_telegram_id(str(chat_id))
    if user:
        user_id, telegram_id, username, first_name, last_name, phone, created_at = user
        profile_info = f"""
👤 معلوماتك الشخصية:
- الاسم: {first_name} {last_name}
- اسم المستخدم: {username}
- الهاتف: {phone}
- تاريخ الانضمام: {created_at}
"""
        bot.send_message(chat_id=chat_id, text=profile_info)
    else:
        bot.send_message(chat_id=chat_id, text="❌ لم يتم العثور على معلومات شخصية.")

def show_profile(bot, chat_id):
    """عرض المعلومات الشخصية للمستخدم"""
    try:
        user = db.get_user_by_telegram_id(str(chat_id))
        if not user:
            bot.send_message(
                chat_id=chat_id,
                text="❌ عذراً، لم يتم العثور على بياناتك. يرجى التسجيل أولاً.",
                reply_markup=MAIN_MENU
            )
            return

        # جلب إحصائيات المستخدم للعمليات الناجحة فقط
        stats = db.get_user_stats(user[0])
        
        # تنسيق الوقت بشكل أنيق إذا وجد
        last_activity = 'لم يتم إجراء أي عملية بعد'
        if stats['last_activity']:
            dt = datetime.strptime(stats['last_activity'], '%Y-%m-%d %H:%M:%S')
            last_activity = dt.strftime('%Y/%m/%d %H:%M')
        
        profile_text = f"""
👤 *بيانات المستخدم*
• الاسم: `{user[1]}`
• رقم الهاتف: `{user[3]}`

📊 *إحصائيات*
• العمليات الناجحة: `{stats['successful_verifications']}`
• آخر عملية: `{last_activity}`

ℹ️ لتحديث بياناتك، استخدم الأمر /start"""
        
        bot.send_message(
            chat_id=chat_id,
            text=profile_text,
            parse_mode='Markdown',
            reply_markup=MAIN_MENU
        )
        
    except Exception as e:
        print_status(f"خطأ في عرض الملف الشخصي: {e}", "ERROR")
        bot.send_message(
            chat_id=chat_id,
            text="❌ عذراً، حدث خطأ أثناء عرض معلوماتك. يرجى المحاولة مرة أخرى.",
            reply_markup=MAIN_MENU
        )
