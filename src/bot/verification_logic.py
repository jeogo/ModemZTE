import sqlite3
from datetime import datetime, timedelta
from src.utils.config import DB_PATH, ALLOWED_SENDER
from src.utils.db import get_transaction_by_details
from src.sms.advanced_message_processor import MessageProcessor

# الرقم الوحيد المسموح بالتحقق منه
# ALLOWED_SENDER = "7711198105108105115"

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

def verify_transaction(amount, date, time):
    """
    التحقق من وجود عملية تعبئة بنفس المبلغ والتاريخ والوقت.
    يبحث أولاً عن تطابق تام (مع تجاهل الثواني)،
    ثم يبحث بهامش ±3 دقائق فقط إذا لم يجد تطابق تام.
    """
    try:
        # البحث عن تطابق تام أولاً
        exact_match = get_transaction_by_details(amount, date, time)
        if exact_match:
            return True
            
        # إذا لم يجد تطابق تام، ابحث بهامش ±3 دقائق
        margin_match = get_transaction_by_details(amount, date, time, margin_minutes=3)
        return bool(margin_match)
        
    except Exception as e:
        print(f"خطأ في التحقق من العملية: {e}")
        return False

def process_sms_advanced(message_bytes: bytes) -> dict:
    """
    معالجة متقدمة لرسائل SMS باستخدام المعالج المتقدم
    يستخرج المبلغ والتاريخ والوقت بشكل ذكي ودقيق
    """
    processor = MessageProcessor()
    result = processor.process_message(message_bytes)
    
    if result['success'] and result['amount'] and result['datetime']:
        date_str = result['datetime'].strftime('%d/%m/%Y')
        time_str = result['datetime'].strftime('%H:%M')
        
        return {
            'success': True,
            'amount': result['amount'],
            'date': date_str,
            'time': time_str,
            'cleaned_text': result['cleaned']
        }
    
    # إذا فشل المعالج المتقدم، جرب الطريقة التقليدية
    basic_result = extract_recharge_info(message_bytes.decode('utf-8', errors='replace'))
    if basic_result:
        return {
            'success': True,
            **basic_result,
            'cleaned_text': message_bytes.decode('utf-8', errors='replace').strip()
        }
        
    return {
        'success': False,
        'error': result.get('error', 'فشل في استخراج المعلومات')
    }

def verify_transaction_advanced(message_bytes: bytes):
    """
    التحقق من العملية باستخدام المعالج المتقدم للرسائل
    يدعم أنماط مختلفة من الرسائل وترميزات متعددة
    """
    try:
        # معالجة الرسالة باستخدام المعالج المتقدم
        info = process_sms_advanced(message_bytes)
        
        if not info['success']:
            return False, "لم نتمكن من استخراج المعلومات من الرسالة"
            
        # التحقق من العملية
        verified = verify_transaction(
            amount=info['amount'],
            date=info['date'],
            time=info['time']
        )
        
        if verified:
            return True, {
                'amount': info['amount'],
                'date': info['date'],
                'time': info['time'],
                'text': info['cleaned_text']
            }
        
        return False, "لم نجد عملية مطابقة"
        
    except Exception as e:
        return False, f"حدث خطأ أثناء التحقق: {str(e)}"
