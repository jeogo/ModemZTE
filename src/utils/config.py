import os
from .paths import DATA_DIR

# Project settings
DB_PATH = str(DATA_DIR / 'sms_messages.db')
RECONNECT_INTERVAL = 10  # seconds
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1
POLL_INTERVAL = 10  # seconds for SMS polling

# SMS settings
ALLOWED_SENDER = ""  # Empty = Accept ALL SMS messages from any sender

# Telegram Bot settings
# !! تحذير أمني !!
# يوصى بشدة باستخدام متغيرات البيئة للبيانات الحساسة.
# قم بتعيين هذه المتغيرات في نظام التشغيل الخاص بك قبل تشغيل البوت.
# مثال:
# export TELEGRAM_BOT_TOKEN='your_token_here'
# export ADMIN_CHAT_IDS='12345,67890'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '6243200710:AAFDH5QmjtOT4ldBAumRnNTDYsWj33kf0TQ')  # Get this from @BotFather
TELEGRAM_MESSAGE_CHECK_INTERVAL = 5  # seconds
MAX_MESSAGE_LENGTH = 4096*2 # Telegram's max message length

# Admin (supervisor) chat IDs - يمكن إضافة أكثر من مشرف
# يتم تحميلها من متغيرات البيئة، أو استخدام القيمة الافتراضية إذا لم يتم تعيينها
admin_ids_str = os.getenv('ADMIN_CHAT_IDS', '5565239578')
ADMIN_CHAT_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip()]

# Admin contact information (for users to contact support)
# معلومات المشرفين للدعم الفني - نفس ترتيب ADMIN_CHAT_IDS أعلاه
ADMIN_CONTACT_INFO = [
    {
        'name': 'المشرف الأول',
        'username': '@YourAdminUsername',  # ضع هنا اسم المستخدم الخاص بالمشرف الأول
        'contact_id': '5565239578',       # معرف التليجرام للمشرف الأول (نفس الرقم في ADMIN_CHAT_IDS)
    },
    # {
    #     'name': 'المشرف الثاني',
    #     'username': '@SecondAdminUsername',  # ضع هنا اسم المستخدم الخاص بالمشرف الثاني
    #     'contact_id': '1234567890',          # معرف التليجرام للمشرف الثاني (نفس الرقم في ADMIN_CHAT_IDS)
    # }
    # لإضافة مشرف جديد: احذف # من الأسطر أعلاه وأضف معلوماته
]

# رسالة الدعم العامة
SUPPORT_MESSAGE = 'للحصول على المساعدة، تواصل مع أحد المشرفين أدناه'