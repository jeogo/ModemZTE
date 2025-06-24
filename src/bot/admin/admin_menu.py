from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from .admin_actions import get_formatted_messages
from ..bot_utils import handle_bot_call
import time

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ['المستخدمون', 'الرسائل'],
    ],
    resize_keyboard=True
)

async def send_admin_menu(bot, chat_id):
    try:
        # Send message directly with await for v22+ compatibility
        message = await bot.send_message(
            chat_id=chat_id,
            text="اختر من قائمة المشرف:",
            reply_markup=ADMIN_MENU
        )
        return message
    except Exception as e:
        print(f"Error sending admin menu: {e}")
        return None

async def send_users_list(bot, chat_id, users, page=0):
    """
    عرض قائمة المستخدمين بشكل احترافي ومفصل
    """    
    if not users:
        try:
            message = await bot.send_message(
                chat_id=chat_id, 
                text='📭 لا يوجد مستخدمون مسجلون في النظام.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")]])
            )
            return message
        except Exception as e:
            print(f"Error sending users message: {e}")
        return
    
    USERS_PER_PAGE = 4  # تقليل العدد لعرض أفضل
    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    current_users = users[start:end]
    
    # إنشاء النص الرئيسي
    text = f"👥 **إدارة المستخدمين**\n"
    text += f"📄 الصفحة {page + 1} من {(len(users) - 1) // USERS_PER_PAGE + 1}\n"
    text += f"📊 إجمالي المستخدمين: {len(users)}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    
    # عرض تفاصيل كل مستخدم
    for i, user in enumerate(current_users, 1):
        user_id, telegram_id, username, phone, is_admin = user
        
        # تحديد نوع المستخدم
        user_type = "👑 مدير" if is_admin else "👤 مستخدم عادي"
        username_display = username or "غير محدد"
        phone_display = phone or "غير محدد"
        
        # إضافة معلومات المستخدم للنص
        text += f"{start + i}. {user_type}\n"
        text += f"   📝 الاسم: `{username_display}`\n"
        text += f"   📱 الهاتف: `{phone_display}`\n"
        text += f"   🆔 معرف التليجرام: `{telegram_id}`\n"
        
        # جلب إحصائيات سريعة
        try:
            from .admin_actions import get_user_stats
            user_stats = get_user_stats(telegram_id)
            if user_stats and user_stats['stats']:
                stats = user_stats['stats']
                text += f"   📊 العمليات: {stats['success']}/{stats['total']} نجح\n"
        except:
            text += f"   📊 العمليات: غير متوفر\n"
        
        text += "\n"
        
        # زر لعرض تفاصيل المستخدم
        button_text = f"📋 {username_display[:20]} {'👑' if is_admin else '👤'}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"user_{telegram_id}"
        )])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # زر العودة دائماً موجود
    buttons.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_menu")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        return message
    except Exception as e:
        print(f"Error sending users list: {e}")
        return None

async def send_messages_view(bot, chat_id, page=0, wait_message_id=None):
    """
    عرض الرسائل في شكل احترافي مع معاينة سريعة وإمكانية عرض التفاصيل
    """
    if wait_message_id is None:
        try:
            wait_msg = await bot.send_message(chat_id=chat_id, text="📱 جاري تحميل الرسائل...")
            wait_message_id = wait_msg.message_id
        except Exception as e:
            print(f"Error sending loading message: {e}")
            return None
    
    result = get_formatted_messages(page)
    
    if not result['messages']:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=wait_message_id, 
                text="📭 لا توجد رسائل للعرض.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")]])
            )
        except Exception as e:
            print(f"Error editing message: {e}")
        return None
    
    # إنشاء عرض الرسائل الاحترافي
    text = f"📨 **إدارة الرسائل**\n"
    text += f"📄 الصفحة {result['current_page'] + 1} من {result['pages']}\n"
    text += f"📊 إجمالي الرسائل: {result['total']}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    
    # عرض الرسائل مع معاينة احترافية
    for i, msg in enumerate(result['messages'], 1):
        # أيقونة حسب نوع الرسالة
        icon = "💰" if msg['has_amount'] else "📄"
        
        # معلومات الرسالة المختصرة
        amount_info = f" • {msg['amount']} DZD" if msg['has_amount'] else ""
        verification_info = f" • ✅{msg['verifications']['success']}/❌{msg['verifications']['failed']}" if msg['verifications']['total'] > 0 else ""
        
        # النص المعروض على الزر
        button_text = f"{icon} #{msg['id']} - {msg['sender'][:15]}{amount_info}"
        
        # معلومات إضافية في النص الرئيسي
        text += f"{i}. {icon} **رسالة #{msg['id']}**\n"
        text += f"   📞 من: `{msg['sender']}`\n"
        text += f"   📅 التاريخ: `{msg['formatted_date']}`\n"
        if msg['has_amount']:
            text += f"   💰 المبلغ: **{msg['amount']} DZD**\n"
        else:
            text += f"   📝 نوع: رسالة عادية\n"
        text += f"   📝 المعاينة: `{msg['preview']}`\n"
        if msg['verifications']['total'] > 0:
            text += f"   📊 التحققات: ✅{msg['verifications']['success']} | ❌{msg['verifications']['failed']}\n"
        text += "\n"
        
        # زر لعرض التفاصيل الكاملة
        buttons.append([InlineKeyboardButton(
            text=f"📋 عرض تفاصيل الرسالة #{msg['id']}",
            callback_data=f"msg_details_{msg['id']}_page_{result['current_page']}"
        )])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"msgpage_{page-1}"))
    if page + 1 < result['pages']:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"msgpage_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # زر العودة دائماً موجود
    buttons.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_menu")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=wait_message_id,
            text=text,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error editing message text: {e}")
    
    return None

async def send_message_details(bot, chat_id, message_id, return_page=0, wait_message_id=None):
    """عرض تفاصيل الرسالة الكاملة"""
    from .admin_actions import get_message_details
    
    if wait_message_id is None:
        try:
            wait_msg = await bot.send_message(chat_id=chat_id, text="🔍 جاري تحميل التفاصيل...")
            wait_message_id = wait_msg.message_id
        except Exception as e:
            print(f"Error sending loading message: {e}")
            return None
    
    message_details = get_message_details(message_id)
    
    if not message_details:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=wait_message_id,
                text="❌ لم يتم العثور على الرسالة",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"msgpage_{return_page}")]])
            )
        except Exception as e:
            print(f"Error editing message: {e}")
        return None
    
    # تنسيق التفاصيل الكاملة
    text = f"📋 **تفاصيل الرسالة #{message_details['id']}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # معلومات أساسية
    text += f"📞 **المرسل:** `{message_details['sender']}`\n"
    text += f"📅 **التاريخ:** `{message_details['date']}`\n"
    
    # معلومات المبلغ
    if message_details['has_amount']:
        text += f"💰 **المبلغ:** **{message_details['amount']} DZD**\n"
        text += f"📊 **نوع الرسالة:** رسالة رصيد 💰\n"
    else:
        text += f"📊 **نوع الرسالة:** رسالة عادية 📄\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 **المحتوى الكامل:**\n\n`{message_details['content']}`\n"
    
    # إحصائيات التحقق
    if message_details['verifications']['total'] > 0:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 **إحصائيات التحقق:**\n"
        text += f"• إجمالي التحققات: **{message_details['verifications']['total']}**\n"
        text += f"• نجح: **{message_details['verifications']['success']}** ✅\n"
        text += f"• فشل: **{message_details['verifications']['failed']}** ❌\n"
        
        # تفاصيل التحققات
        if message_details['verifications']['details']:
            text += f"\n**تفاصيل التحققات:**\n"
            for ver in message_details['verifications']['details'][:5]:  # أول 5 تحققات
                date, status, username, phone = ver
                status_icon = "✅" if status == 'success' else "❌"
                user_info = username or phone or "مستخدم غير معروف"
                text += f"{status_icon} `{date}` - {user_info}\n"
    else:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 **حالة التحقق:** لم يتم استخدامها بعد\n"
    
    # أزرار التحكم
    buttons = [
        [InlineKeyboardButton("🔙 رجوع للرسائل", callback_data=f"msgpage_{return_page}")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_menu")]
    ]
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=wait_message_id,
            text=text,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error editing message text: {e}")
    
    return None
