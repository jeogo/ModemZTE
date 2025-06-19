import sqlite3
from src.utils.config import DB_PATH
from datetime import datetime, timedelta

# الرقم الوحيد المسموح بالتحقق منه
ALLOWED_SENDER = "7711198105108105115"

# دالة استخراج المبلغ والتاريخ والوقت من نص الرسالة
import re
def extract_recharge_info(content):
    pattern = r"rechargé\s+(\d+(?:\.\d{2})?)\s+DZD.*le\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}):"
    match = re.search(pattern, content)
    if match:
        return {
            'amount': float(match.group(1)),
            'date': match.group(2),
            'time': match.group(3)
        }
    return None

def verify_transaction(amount, date, time, margin_minutes=5):
    """
    التحقق من وجود عملية تعبئة بنفس المبلغ والتاريخ والوقت (مع هامش دقائق)
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # ابحث فقط عن الرسائل من الرقم المسموح
        c.execute('''SELECT content, received_date FROM sms WHERE sender = ?''', (ALLOWED_SENDER,))
        rows = c.fetchall()
        target_dt = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
        for content, received_date in rows:
            info = extract_recharge_info(content)
            if not info:
                continue
            msg_dt = datetime.strptime(f"{info['date']} {info['time']}", "%d/%m/%Y %H:%M")
            if abs((msg_dt - target_dt).total_seconds()) <= margin_minutes * 60 and float(info['amount']) == float(amount):
                return True
        return False
    finally:
        conn.close()
