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

# القائمة الرئيسية - تصميم محسن ومنظم
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ['✅ تحقق من العملية'],
        ['👤 معلوماتي الشخصية', '📊 تقارير العمليات'],
        ['🆘 اتصل بالدعم الفني', '❓ شرح كيفية الاستخدام']
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# قائمة فترات التقارير - تصميم محسن ومنظم
REPORT_PERIODS = ReplyKeyboardMarkup(
    [
        ['⏰ آخر 24 ساعة', '📅 آخر 3 أيام'],
        ['📆 آخر 7 أيام', '📝 آخر شهر'],
        ['📋 كل العمليات'],
        ['🔙 رجوع للقائمة الرئيسية']
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

async def send_main_menu(bot, chat_id):
    """إرسال القائمة الرئيسية مع رسالة ترحيبية مختصرة وواضحة"""
    try:
        welcome_text = """
🤖 *مرحباً بك في نظام التحقق من عمليات التعبئة!*

📋 اختر الخدمة المطلوبة من الأزرار أدناه:
        """
        await bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )
        user_sessions[chat_id] = {'state': FSMState.IDLE}
    except Exception as e:
        await bot.send_message(
            chat_id=chat_id,
            text="🤖 *مرحباً!* اختر من القائمة:",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )

async def start_verification(bot, chat_id):
    """بدء عملية التحقق مع رسالة مختصرة"""
    user_sessions[chat_id] = {'state': FSMState.WAIT_AMOUNT}
    verification_text = """
💰 *الخطوة 1: أدخل مبلغ التعبئة*

📝 أدخل المبلغ بالأرقام فقط
📋 مثال: `1000` أو `500`
    """
    cancel_keyboard = ReplyKeyboardMarkup([['❌ إلغاء']], resize_keyboard=True, one_time_keyboard=True)
    await bot.send_message(
        chat_id=chat_id,
        text=verification_text,
        reply_markup=cancel_keyboard,
        parse_mode='Markdown'
    )

async def handle_user_message(update, bot):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    session = user_sessions.get(chat_id, {'state': FSMState.IDLE})
    state = session['state']
    if text == '❌ إلغاء':
        await send_main_menu(bot, chat_id)
        return
    if state == FSMState.IDLE:
        if text == '👤 معلوماتي الشخصية':
            await show_profile(bot, chat_id)
        elif text == '✅ تحقق من العملية':
            await start_verification(bot, chat_id)
        elif text == '📊 تقارير العمليات':
            await show_report_periods(bot, chat_id)
        elif text == '🆘 اتصل بالدعم الفني':
            await show_support_contact(bot, chat_id)
        elif text == '❓ شرح كيفية الاستخدام':
            await show_usage_instructions(bot, chat_id)
        else:
            await send_main_menu(bot, chat_id)
    elif state == FSMState.WAIT_AMOUNT:
        if not text.isdigit():
            error_text = """
❌ *خطأ: أدخل أرقام فقط*

📋 مثال صحيح: `1400`
⚠️ لا تضع رموز أو حروف
            """
            await bot.send_message(
                chat_id=chat_id, 
                text=error_text,
                parse_mode='Markdown'            )
            return
        session['amount'] = text
        session['state'] = FSMState.WAIT_DATE
        user_sessions[chat_id] = session
        await show_date_keyboard(bot, chat_id)
    elif state == FSMState.WAIT_DATE:
        if text == '📅 اليوم':
            session['date'] = datetime.now().strftime('%d/%m/%Y')
            session['state'] = FSMState.WAIT_TIME
            user_sessions[chat_id] = session
            await ask_time(bot, chat_id)
        elif text == '📆 أمس':
            session['date'] = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
            session['state'] = FSMState.WAIT_TIME
            user_sessions[chat_id] = session
            await ask_time(bot, chat_id)
        elif text == '🗓️ تاريخ آخر':
            session['state'] = FSMState.WAIT_CUSTOM_DATE
            user_sessions[chat_id] = session
            await bot.send_message(chat_id=chat_id, text="📅 أدخل التاريخ بالصيغة: `DD/MM/YYYY`", parse_mode='Markdown')
        else:
            await bot.send_message(chat_id=chat_id, text="⚠️ اختر تاريخ من الأزرار المتاحة")
            await show_date_keyboard(bot, chat_id)
    elif state == FSMState.WAIT_CUSTOM_DATE:
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', text):
            await bot.send_message(chat_id=chat_id, text="❌ صيغة التاريخ غير صحيحة\n📋 استخدم الصيغة: `DD/MM/YYYY`", parse_mode='Markdown')
            return
        session['date'] = text
        session['state'] = FSMState.WAIT_TIME
        user_sessions[chat_id] = session
        await ask_time(bot, chat_id)
    elif state == FSMState.WAIT_TIME:
        parsed_time = parse_time(text)
        if not parsed_time:
            await bot.send_message(chat_id=chat_id, text="❌ صيغة الوقت غير صحيحة\n📋 مثال: `17:56` أو `5:56 PM`", parse_mode='Markdown')
            return
        session['time'] = parsed_time
        session['state'] = FSMState.CONFIRM
        user_sessions[chat_id] = session
        await show_summary(bot, chat_id, session)
    elif state == FSMState.CONFIRM:
        if text == '✅ تأكيد':
            await bot.send_message(chat_id=chat_id, text="⏳ جاري التحقق...", reply_markup=ReplyKeyboardMarkup([['❌ إلغاء']], resize_keyboard=True, one_time_keyboard=True))
            result = await real_verify(session, telegram_id=chat_id, bot=bot)
            await bot.send_message(chat_id=chat_id, text=result)
            await send_main_menu(bot, chat_id)
        elif text == '❌ إلغاء':
            await send_main_menu(bot, chat_id)
        else:
            await bot.send_message(chat_id=chat_id, text="⚠️ اضغط تأكيد أو إلغاء")
            await show_summary(bot, chat_id, session)
    elif state == FSMState.WAIT_REPORT_PERIOD:
        await handle_report_period(bot, chat_id, text)
    else:
        await send_main_menu(bot, chat_id)

async def show_date_keyboard(bot, chat_id):
    """عرض أزرار اختيار التاريخ بشكل مختصر"""
    date_text = """
📅 *الخطوة 2: اختر تاريخ العملية*

⏰ اختر من الأزرار أدناه:
    """
    keyboard = ReplyKeyboardMarkup(
        [
            ['📅 اليوم', '📆 أمس'],
            ['🗓️ تاريخ آخر'],
            ['❌ إلغاء']
        ], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    await bot.send_message(
        chat_id=chat_id, 
        text=date_text, 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def ask_time(bot, chat_id):
    """طلب الوقت بشكل مختصر"""
    time_text = """
⏰ *الخطوة 3: أدخل وقت العملية*

📋 أدخل الوقت بإحدى الصيغ التالية:
• `14:30` (24 ساعة)
• `2:30 PM` (12 ساعة)
    """
    cancel_keyboard = ReplyKeyboardMarkup([['❌ إلغاء']], resize_keyboard=True, one_time_keyboard=True)
    await bot.send_message(
        chat_id=chat_id, 
        text=time_text, 
        reply_markup=cancel_keyboard,
        parse_mode='Markdown'
    )

async def show_summary(bot, chat_id, session):
    """عرض ملخص مختصر قبل التأكيد"""
    summary_text = f"""
📋 *راجع البيانات قبل التأكيد:*

💰 المبلغ: `{session['amount']} دج`
📅 التاريخ: `{session['date']}`
⏰ الوقت: `{session['time']}`

✅ إذا كانت البيانات صحيحة اضغط تأكيد
    """
    keyboard = ReplyKeyboardMarkup(
        [['✅ تأكيد', '❌ إلغاء']], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    await bot.send_message(
        chat_id=chat_id, 
        text=summary_text, 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

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

async def real_verify(data, telegram_id=None, bot=None):
    """
    تحقق فعلي من قاعدة البيانات مع تسجيل كل عملية تحقق
    يمنع تكرار التحقق لنفس المبلغ من نفس العميل أو من عميل آخر
    """
    try:
        amount = str(data['amount'])
        date_str = data['date']
        time_str = data['time']
        
        # التحقق من المستخدم وتحضير معلوماته
        user = None
        display_name = str(telegram_id) if telegram_id else "غير معروف"
        user_phone = "---"
        
        if telegram_id:
            from src.utils.db import get_user_by_telegram_id
            user = get_user_by_telegram_id(str(telegram_id))
            if user:
                # استخدم الاسم الكامل إذا وجد، وإلا استخدم اسم المستخدم
                first_name = user.get('first_name') or ''
                last_name = user.get('last_name') or ''
                username = user.get('username') or str(telegram_id)
                if first_name.strip() or last_name.strip():
                    full_name = f"{first_name} {last_name}".strip()
                else:
                    full_name = username
                display_name = full_name
                user_phone = user.get('phone_number', '---')
        
        # بيانات المستخدم للإشعارات
        user_data = {
            'display_name': display_name,
            'phone': user_phone,
            'telegram_id': telegram_id
        }
        
        # التحقق من صحة التاريخ والوقت
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
        except Exception:
            error_msg = "خطأ في صيغة التاريخ أو الوقت"
            if user:
                from src.utils.db import add_verification, get_failed_attempts_today
                add_verification(user['id'], None, 'failed')
                
                # التحقق من عدد المحاولات الفاشلة اليوم
                failed_attempts = get_failed_attempts_today(user['id'])
                
                if bot:                    # إشعار أساسي
                    notif_msg = (
                        f"<b>محاولة تحقق فاشلة</b>\n\n"
                        f"<b>معلومات المستخدم:</b>\n"
                        f"   الاسم: <b>{display_name}</b>\n"
                        f"   الهاتف: <b>{user_phone}</b>\n"
                        f"   المعرف: <code>{telegram_id}</code>\n"
                        f"   عدد المحاولات الفاشلة اليوم: <b>{failed_attempts}</b>\n\n"
                        f"<b>سبب الفشل:</b>\n"                        f"خطأ في صيغة التاريخ أو الوقت\n\n"
                        f"<b>البيانات المدخلة:</b>\n"
                        f"   المبلغ: {amount} DZD\n"
                        f"   التاريخ: {date_str}\n"
                        f"   الوقت: {time_str}"
                    )
                    await notify_admins(bot, notif_msg, parse_mode='HTML')
                    
                    # إذا وصل لـ 3 محاولات فاشلة
                    if failed_attempts >= 3:
                        await send_failed_attempts_alert(bot, user_data, failed_attempts)
            return error_msg

        # التحقق من العملية
        from src.utils.db import get_transaction_by_details, get_failed_attempts_today
        exact_match = get_transaction_by_details(float(amount), date_str, time_str)
        
        if exact_match:
            error_msg = None
            # تحقق من وجود عملية تحقق ناجحة فقط
            from src.utils.db import get_user_verifications
            already_verified = False
            if user:
                verifications = get_user_verifications(user['id'])
                for v in verifications:
                    if v['sms_id'] == exact_match['id'] and v['status'] == 'success':
                        already_verified = True
                        break
            if already_verified:
                error_msg = "لا يمكنك تأكيد نفس المبلغ مرتين (تمت الموافقة عليه سابقاً)"
            elif exact_match['verified_by_user'] and (not user or exact_match['verified_by_user'] != user['id']):
                error_msg = "هذا المبلغ تم تأكيده من مستخدم آخر بالفعل"
            if error_msg:
                if bot and user:
                    failed_attempts = get_failed_attempts_today(user['id'])
                    notif_msg = (
                        f"<b>محاولة تحقق مكررة</b>\n\n"
                        f"<b>معلومات المستخدم:</b>\n"
                        f"   الاسم: <b>{display_name}</b>\n"
                        f"   الهاتف: <b>{user_phone}</b>\n"
                        f"   المعرف: <code>{telegram_id}</code>\n"
                        f"   عدد المحاولات الفاشلة اليوم: <b>{failed_attempts}</b>\n\n"
                        f"<b>سبب الفشل:</b>\n"
                        f"{error_msg}\n\n"
                        f"<b>البيانات المدخلة:</b>\n"
                        f"   المبلغ: {amount} DZD\n"                      f"   التاريخ: {date_str}\n"
                        f"   الوقت: {time_str}"
                    )
                    await notify_admins(bot, notif_msg, parse_mode='HTML')
                    if failed_attempts >= 3:
                        await send_failed_attempts_alert(bot, user_data, failed_attempts)
                return error_msg

            # تأكيد العملية
            if user:
                from src.utils.db import add_verification, get_user_last_success
                add_verification(user['id'], exact_match['id'], 'success')
                last_success = get_user_last_success(user['id'])
                if bot:
                    success_count = sum(1 for v in db.get_user_verifications(user['id']) if v['status'] == 'success')
                    notif_msg = (
                        f"<b>تم تأكيد عملية تعبئة رصيد</b>\n\n"
                        f"<b>معلومات المستخدم:</b>\n"
                        f"   الاسم: <b>{display_name}</b>\n"
                        f"   الهاتف: <b>{user_phone}</b>\n"
                        f"   المعرف: <code>{telegram_id}</code>\n"
                        f"   عدد العمليات الناجحة: <b>{success_count}</b>\n\n"
                        f"<b>تفاصيل العملية:</b>\n"
                        f"   المبلغ: <b>{amount}</b> DZD\n"
                        f"   التاريخ: <b>{date_str}</b>\n"
                        f"   الوقت: <b>{time_str}</b>\n\n"                        f"<b>الرسالة الأصلية:</b>\n"
                        f"<code>{exact_match['content']}</code>"
                    )
                    await notify_admins(bot, notif_msg, parse_mode='HTML')

            return f"""
🎉 **تم تأكيد العملية بنجاح!**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **تفاصيل العملية المؤكدة:**
💰 المبلغ: **{amount} دج**
📅 التاريخ: **{date_str}**
⏰ الوقت: **{time_str}**

🔍 **تم العثور على العملية في النظام وتأكيدها**
📢 **سيتم إشعار المشرفين بنجاح العملية**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🙏 **شكراً لاستخدامك النظام!**
            """

        # إذا لم يجد تطابق تام، سجل الفشل
        if user:
            from src.utils.db import add_verification
            add_verification(user['id'], None, 'failed')
            
            failed_attempts = get_failed_attempts_today(user['id'])
            if bot:
                notif_msg = (
                    f"<b>محاولة تحقق فاشلة</b>\n\n"
                    f"<b>معلومات المستخدم:</b>\n"
                    f"   الاسم: <b>{display_name}</b>\n"
                    f"   الهاتف: <b>{user_phone}</b>\n"
                    f"   المعرف: <code>{telegram_id}</code>\n"
                    f"   عدد المحاولات الفاشلة اليوم: <b>{failed_attempts}</b>\n\n"
                    f"<b>سبب الفشل:</b>\n"                    f"لم يتم العثور على عملية مطابقة\n\n"
                    f"<b>البيانات المدخلة:</b>\n"
                    f"   المبلغ: {amount} DZD\n"
                    f"   التاريخ: {date_str}\n"
                    f"   الوقت: {time_str}"
                )
                await notify_admins(bot, notif_msg, parse_mode='HTML')
                  # إذا وصل لـ 3 محاولات فاشلة
                if failed_attempts >= 3:
                    await send_failed_attempts_alert(bot, user_data, failed_attempts)
            return """
❌ **لم يتم العثور على عملية مطابقة**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤔 **أسباب محتملة:**
• البيانات المدخلة غير صحيحة
• العملية لم تصل للنظام بعد
• تم إدخال وقت أو تاريخ خاطئ
• المبلغ غير مطابق للعملية الفعلية

💡 **اقتراحات للحل:**
✅ تأكد من البيانات من رسالة تأكيد التعبئة
⏳ انتظر بضع دقائق وحاول مرة أخرى
🕐 تأكد من كتابة الوقت بالضبط كما في الرسالة
📅 راجع صيغة التاريخ (DD/MM/YYYY)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆘 **تحتاج مساعدة؟**
**اتصل بالدعم الفني** من القائمة الرئيسية
        """

    except Exception as e:
        print_status(f"خطأ في التحقق: {str(e)}", "ERROR")
        if user:
            from src.utils.db import add_verification
            add_verification(user['id'], None, 'failed')
            failed_attempts = get_failed_attempts_today(user['id'])
            
            if bot:
                notif_msg = (
                    f"خطأ في عملية التحقق\n\n"
                    f"معلومات المستخدم:\n"
                    f"   الاسم: {display_name}\n"
                    f"   الهاتف: {user_phone}\n"
                    f"   المعرف: {telegram_id}\n"
                    f"   عدد المحاولات الفاشلة اليوم: {failed_attempts}\n\n"
                    f"تفاصيل الخطأ:\n"
                    f"{str(e)}\n\n"
                    f"البيانات المدخلة:\n"
                    f"   المبلغ: {amount} DZD\n"                    f"   التاريخ: {date_str}\n"
                    f"   الوقت: {time_str}"
                )
                await notify_admins(bot, notif_msg, parse_mode='HTML')
                
                # إذا وصل لـ 3 محاولات فاشلة
                if failed_attempts >= 3:
                    await send_failed_attempts_alert(bot, user_data, failed_attempts)
        
        return f"حدث خطأ أثناء التحقق: {str(e)}\n\nتحتاج مساعدة؟\nتواصل مع الدعم الفني عبر القائمة الرئيسية ← اتصل بالدعم الفني"

async def show_report_periods(bot, chat_id):
    """عرض خيارات فترات التقارير بشكل مختصر"""
    user_sessions[chat_id] = {'state': FSMState.WAIT_REPORT_PERIOD}
    await bot.send_message(
        chat_id=chat_id,
        text="📊 *اختر فترة التقرير:*\n\n📈 سيتم عرض جميع عملياتك في الفترة المحددة",
        reply_markup=REPORT_PERIODS,
        parse_mode='Markdown'
    )

async def handle_report_period(bot, chat_id, text):
    """معالجة اختيار فترة التقرير"""
    # التحقق من زر العودة
    if text == '🔙 رجوع للقائمة الرئيسية':
        await send_main_menu(bot, chat_id)
        return
    
    period_map = {
        '⏰ آخر 24 ساعة': '1',
        '📅 آخر 3 أيام': '3',
        '📆 آخر 7 أيام': '7',
        '📝 آخر شهر': '30',
        '📋 كل العمليات': 'all'
    }
    
    period = period_map.get(text)
    if not period:
        await bot.send_message(
            chat_id=chat_id, 
            text="⚠️ يرجى اختيار فترة صحيحة من القائمة",
            reply_markup=REPORT_PERIODS
        )
        return

    await bot.send_message(
        chat_id=chat_id,
        text="📊 *جاري إنشاء التقرير...*\n⏳ يرجى الانتظار",
        reply_markup=ReplyKeyboardMarkup([['❌ إلغاء']], resize_keyboard=True),
        parse_mode='Markdown'
    )
    
    try:
        # إنشاء التقرير
        pdf_path, message = generate_report(period)
        
        if pdf_path and os.path.exists(pdf_path):
            # إرسال ملف PDF
            with open(pdf_path, 'rb') as pdf:
                await bot.send_document(
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
            await send_main_menu(bot, chat_id)
        else:
            # في حالة عدم وجود بيانات أو حدوث خطأ
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=REPORT_PERIODS
            )
            
    except Exception as e:
        print_status(f"خطأ في إنشاء أو إرسال التقرير: {e}", "ERROR")
        await bot.send_message(
            chat_id=chat_id,
            text="عذراً، حدث خطأ أثناء إنشاء التقرير. يرجى المحاولة مرة أخرى.",
            reply_markup=REPORT_PERIODS
        )
    
async def show_profile_info(bot, chat_id):
    """عرض المعلومات الشخصية للمستخدم"""
    user = db.get_user_by_telegram_id(str(chat_id))
    if user:
        user_id, telegram_id, username, first_name, last_name, phone, created_at = user
        profile_info = f"""
معلوماتك الشخصية:
- الاسم: {first_name} {last_name}
- اسم المستخدم: {username}
- الهاتف: {phone}
- تاريخ الانضمام: {created_at}
"""
        await bot.send_message(chat_id=chat_id, text=profile_info)
    else:
        await bot.send_message(chat_id=chat_id, text="لم يتم العثور على معلومات شخصية.")

async def show_profile(bot, chat_id):
    """عرض المعلومات الشخصية للمستخدم بشكل مختصر"""
    try:
        user = db.get_user_by_telegram_id(str(chat_id))
        if not user:
            await bot.send_message(
                chat_id=chat_id,
                text="لا توجد بيانات. سجل أولاً.",
                reply_markup=MAIN_MENU
            )
            return
        user_id = user.get('id') or user.get('user_id')
        stats = db.get_user_stats(user_id)
        last_activity = 'لا يوجد'
        if stats['last_activity']:
            try:
                dt = datetime.strptime(stats['last_activity'], '%Y-%m-%d %H:%M:%S')
                last_activity = dt.strftime('%Y/%m/%d %H:%M')
            except:
                last_activity = stats['last_activity']
        
        username = user.get('username', 'غير محدد')
        phone_number = user.get('phone_number', 'غير محدد')
        profile_text = f"""
👤 *معلوماتك الشخصية:*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 الاسم: `{username}`
📱 الهاتف: `{phone_number}`
✅ عمليات ناجحة: `{stats['successful_verifications']}`
📅 آخر عملية: `{last_activity}`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        await bot.send_message(
            chat_id=chat_id,
            text=profile_text,
            parse_mode='Markdown',
            reply_markup=MAIN_MENU
        )
    except Exception as e:
        print_status(f"خطأ في عرض الملف الشخصي: {e}", "ERROR")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ حدث خطأ في تحميل بياناتك. حاول لاحقاً.",
            reply_markup=MAIN_MENU
        )

async def send_failed_attempts_alert(bot, user_data, failed_attempts):
    """إرسال تنبيه للمشرفين عند وصول المستخدم لـ 3 محاولات فاشلة"""
    try:
        alert_msg = (
            f"<b>تحذير: محاولات متكررة فاشلة</b>\n\n"
            f"<b>معلومات المستخدم:</b>\n"
            f"   الاسم: <b>{user_data['display_name']}</b>\n"
            f"   الهاتف: <b>{user_data['phone']}</b>\n"
            f"   المعرف: <code>{user_data['telegram_id']}</code>\n\n"            f"<b>عدد المحاولات الفاشلة اليوم:</b> <b>{failed_attempts}</b>\n\n"
            f"يرجى مراجعة نشاط هذا المستخدم!"
        )
        await notify_admins(bot, alert_msg, parse_mode='HTML')
    except Exception as e:
        print_status(f"خطأ في إرسال تنبيه المحاولات الفاشلة: {e}", "ERROR")

async def notify_admins(bot, text, parse_mode=None):
    from src.utils.config import ADMIN_CHAT_IDS
    from src.utils.logger import print_status
    
    if not ADMIN_CHAT_IDS:
        print_status("لا يوجد مشرفين معرفين في ADMIN_CHAT_IDS!", "WARNING")
        return False

    success_count = 0
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            success_count += 1
        except Exception as e:
            print_status(f"فشل إرسال إشعار للمشرف {admin_id}: {str(e)}", "ERROR")
    
    if success_count == 0:
        print_status("فشل إرسال الإشعارات لجميع المشرفين!", "ERROR")
    elif success_count < len(ADMIN_CHAT_IDS):
        print_status(f"تم إرسال الإشعارات لـ {success_count} من {len(ADMIN_CHAT_IDS)} مشرف", "WARNING")
    
    return success_count > 0

async def show_support_contact(bot, chat_id):
    """عرض الدعم الفني بشكل مختصر"""
    try:
        from src.utils.config import ADMIN_CONTACT_INFO, SUPPORT_MESSAGE
        support_text = f"""
🆘 *الدعم الفني*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 {SUPPORT_MESSAGE}

👥 *فريق الدعم:*
"""
        for i, admin in enumerate(ADMIN_CONTACT_INFO, 1):
            support_text += f"• {admin['name']}: {admin['username']}\n"
        
        support_text += "\n💡 *للمساعدة:* أرسل مشكلتك بوضوح مع رقم هاتفك"
        support_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await bot.send_message(
            chat_id=chat_id,
            text=support_text,
            parse_mode='Markdown',
            reply_markup=MAIN_MENU
        )
    except Exception as e:
        print_status(f"خطأ في عرض معلومات الدعم الفني: {e}", "ERROR")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ حدث خطأ في تحميل معلومات الدعم الفني.",
            reply_markup=MAIN_MENU
        )

async def show_usage_instructions(bot, chat_id):
    """شرح مختصر لكيفية استخدام البوت"""
    instructions_text = """
❓ *دليل الاستخدام السريع*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔢 **خطوات التحقق من العملية:**

1️⃣ اضغط "✅ تحقق من العملية"
2️⃣ أدخل المبلغ (أرقام فقط)
3️⃣ اختر التاريخ (اليوم/أمس/آخر)
4️⃣ أدخل الوقت (مثل: 14:30)
5️⃣ راجع البيانات واضغط "✅ تأكيد"

📊 **التقارير:** عرض جميع عملياتك السابقة
👤 **معلوماتي:** عرض بياناتك وإحصائياتك
🆘 **الدعم:** للمساعدة والاستفسارات

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 *نصيحة:* تأكد من دقة البيانات للحصول على أفضل النتائج
    """
    await bot.send_message(
        chat_id=chat_id,
        text=instructions_text,
        parse_mode='Markdown',
        reply_markup=MAIN_MENU
    )
