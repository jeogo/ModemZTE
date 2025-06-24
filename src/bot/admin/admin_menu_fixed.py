from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from .admin_actions import get_formatted_messages
import time

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ['المستخدمون', 'الرسائل'],
        ['التقارير'],
    ],
    resize_keyboard=True
)

def send_admin_menu(bot, chat_id):
    try:
        bot.send_message(
            chat_id=chat_id,
            text="اختر من قائمة المشرف:",
            reply_markup=ADMIN_MENU
        )
    except Exception as e:
        print(f"Error sending admin menu: {e}")

def send_users_list(bot, chat_id, users, page=0):
    """
    عرض قائمة المستخدمين باستخدام أزرار Inline.
    كل مستخدم يظهر اسمه ورقم هاتفه في زر كامل العرض.
    """
    if not users:
        try:
            bot.send_message(chat_id=chat_id, text='لا يوجد مستخدمون.')
        except Exception as e:
            print(f"Error sending users message: {e}")
        return

    USERS_PER_PAGE = 5
    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    current_users = users[start:end]
    
    buttons = []
    for user in current_users:
        user_id, telegram_id, username, phone, is_admin = user
        # تنسيق معلومات المستخدم في زر كامل العرض
        user_text = f"{username or 'مجهول'} | {phone or 'لا يوجد'}"
        if is_admin:
            user_text += " | مشرف"
        buttons.append([InlineKeyboardButton(
            text=user_text,
            callback_data=f"user_{telegram_id}"
        )])

    # أزرار التنقل بين الصفحات
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons)
    text = f"قائمة المستخدمين (صفحة {page+1}/{(len(users)-1)//USERS_PER_PAGE+1}):"
    
    try:
        bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error sending users list: {e}")

def send_messages_view(bot, chat_id, page=0, wait_message_id=None):
    """
    عرض الرسائل في شكل جدول منظم مع أزرار التصفح
    إذا تم تمرير wait_message_id سيتم تعديل نفس الرسالة.
    """
    if wait_message_id is None:
        try:
            wait_msg = bot.send_message(chat_id=chat_id, text="⏳ جاري تحميل الرسائل ...")
            wait_message_id = wait_msg.message_id
        except Exception as e:
            print(f"Error sending loading message: {e}")
            return None
    
    result = get_formatted_messages(page)
    
    if not result['messages']:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=wait_message_id, text="لا توجد رسائل للعرض.")
        except Exception as e:
            print(f"Error editing message: {e}")
        return None
        
    # إنشاء عرض الرسائل
    text = f"الرسائل ({result['current_page'] + 1}/{result['pages']})\n"
    text += f"إجمالي الرسائل: {result['total']}\n\n"
    
    buttons = []
    for msg in result['messages']:
        amount_text = f"{msg['amount']} DZD" if msg['amount'] else "بدون مبلغ"
        ver_text = f"{msg['verifications']['success']}/{msg['verifications']['total']}"
        row_text = f"#{msg['id']} | {msg['sender']} | {amount_text} | {ver_text} | {msg['content']}"
        # تضمين رقم الصفحة في callback_data
        buttons.append([InlineKeyboardButton(
            text=row_text,
            callback_data=f"msg_{msg['id']}_page_{result['current_page']}"
        )])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"msgpage_{page-1}"))
    if page + 1 < result['pages']:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"msgpage_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # زر العودة
    buttons.append([InlineKeyboardButton("رجوع للقائمة", callback_data="back_to_menu")])
    
    markup = InlineKeyboardMarkup(buttons)
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=wait_message_id,
            text=text,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error editing message text: {e}")
    return None
