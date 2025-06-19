import sqlite3
from datetime import datetime, timedelta
from src.utils.config import DB_PATH
from src.utils.db import init_db

# إنشاء قاعدة بيانات جديدة
init_db()

# المُرسل الثابت
SENDER = "7711198105108105115"

# قائمة المبالغ المختلفة (بالدينار)
test_amounts = [
    1400.00,  # مبلغ متكرر
    2000.00,
    500.00,
    1000.00,
    1400.00,  # نفس المبلغ بتاريخ مختلف
    750.00,
    1400.00,  # نفس المبلغ مرة أخرى
    3000.00,
    1200.00,
    900.00,
    1400.00,  # مبلغ متكرر بفارق دقائق
    2500.00,
    1800.00,
    1400.00,  # آخر تكرار
]

# تواريخ وأوقات موزعة على 10 أيام
base_date = datetime(2025, 6, 10, 14, 30)  # نبدأ من 10 يونيو
messages = []

# إنشاء رسائل متنوعة
for i, amount in enumerate(test_amounts):
    # تاريخ عشوائي ضمن 10 أيام
    days_offset = i % 10  # توزيع على 10 أيام
    hours_offset = (i * 2) % 24  # توزيع الساعات
    minutes_offset = (i * 7) % 60  # توزيع الدقائق
    
    msg_date = base_date + timedelta(
        days=days_offset,
        hours=hours_offset,
        minutes=minutes_offset
    )
    
    # تنسيق التاريخ والوقت
    formatted_date = msg_date.strftime("%d/%m/%Y")
    formatted_time = msg_date.strftime("%H:%M:%S")
    
    # إنشاء نص الرسالة
    content = f"Vous avez rechargé {amount:.2f} DZD DA avec succès le {formatted_date} {formatted_time} ."
    
    # تنسيق التاريخ لقاعدة البيانات
    db_date = msg_date.strftime("%Y-%m-%d %H:%M:%S")
    
    messages.append((SENDER, db_date, content))

# إضافة رسالتين متقاربتين جداً (فارق دقائق)
close_date = datetime(2025, 6, 18, 17, 56, 21)
messages.append((
    SENDER,
    close_date.strftime("%Y-%m-%d %H:%M:%S"),
    f"Vous avez rechargé 1400.00 DZD DA avec succès le {close_date.strftime('%d/%m/%Y %H:%M:%S')} ."
))

close_date2 = close_date + timedelta(minutes=3)
messages.append((
    SENDER,
    close_date2.strftime("%Y-%m-%d %H:%M:%S"),
    f"Vous avez rechargé 1400.00 DZD DA avec succès le {close_date2.strftime('%d/%m/%Y %H:%M:%S')} ."
))

# حفظ في قاعدة البيانات
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    # إضافة كل الرسائل
    c.executemany('''
        INSERT INTO sms (sender, received_date, content, is_sent_to_telegram)
        VALUES (?, ?, ?, 1)
    ''', messages)
    
    conn.commit()
    print(f"✅ تم إضافة {len(messages)} رسالة بنجاح!")
    
    # عرض ملخص البيانات المضافة
    print("\nملخص الرسائل المضافة:")
    for sender, date, content in messages:
        print(f"\n📱 تاريخ: {date}")
        print(f"💰 محتوى: {content}")
    
except Exception as e:
    print(f"❌ حدث خطأ: {e}")
finally:
    conn.close()
