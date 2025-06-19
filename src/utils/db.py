import sqlite3
from .config import DB_PATH
import os
from datetime import datetime
from .logger import print_status
from .paths import DATA_DIR

def parse_modem_date(date_str):
    """تحويل التاريخ من صيغة المودم إلى صيغة SQLite"""
    try:
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        if ',' in date_str:
            date_part, time_part = date_str.split(',')
            time_part = time_part.split('+')[0].split('-')[0]
            
            year, month, day = map(int, date_part.split('/'))
            hour, minute, second = map(int, time_part.split(':'))
            
            year = 2000 + year
            
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
    except Exception as e:
        print_status(f"خطأ في تحويل التاريخ {date_str}: {e}", "ERROR")
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول الجديدة"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA encoding = "UTF-8"')
    c = conn.cursor()

    # حذف الجداول القديمة إذا كانت موجودة
    c.execute('DROP TABLE IF EXISTS sms_messages')
    c.execute('DROP TABLE IF EXISTS telegram_chat')

    # إنشاء الجداول الجديدة
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        telegram_id TEXT UNIQUE,
        phone_number TEXT,
        is_admin INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        received_date TEXT,
        content TEXT,
        is_sent_to_telegram INTEGER DEFAULT 0,
        verified_by INTEGER,
        deleted_from_sim INTEGER DEFAULT 0,
        FOREIGN KEY (verified_by) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS verification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        sms_id INTEGER,
        status TEXT CHECK(status IN ('success', 'failed')),
        verified_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (sms_id) REFERENCES sms(id)
    )''')

    conn.commit()
    conn.close()
    print_status("✅ تم تهيئة قاعدة البيانات بنجاح", "SUCCESS")

def verify_message_saved(sender, content):
    """التحقق من حفظ الرسالة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM sms WHERE sender = ? AND content = ?', (sender, content))
        result = c.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print_status(f"خطأ في التحقق من حفظ الرسالة: {e}", "ERROR")
        return False

def message_exists(sender, content):
    """التحقق من وجود الرسالة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM sms WHERE sender = ? AND content = ?', (sender, content))
        result = c.fetchone()
        if result:
            print_status(f"الرسالة موجودة مسبقاً في قاعدة البيانات", "DEBUG")
            return True
        return False
    except Exception as e:
        print_status(f"خطأ في التحقق من وجود الرسالة: {e}", "ERROR")
        return False
    finally:
        conn.close()

def save_sms(status, sender, timestamp, content):
    """حفظ رسالة SMS جديدة في قاعدة البيانات"""
    try:
        # تحويل التاريخ لصيغة موحدة
        parsed_date = parse_modem_date(timestamp)
        
        # حفظ الرسالة في قاعدة البيانات
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO sms (sender, received_date, content, is_sent_to_telegram)
            VALUES (?, ?, ?, 1)
        ''', (sender, parsed_date, content))
        
        msg_id = c.lastrowid
        conn.commit()
        
        print_status(f"✅ تم حفظ الرسالة برقم {msg_id}", "SUCCESS")
        print_status(f"   المرسل: {sender}", "INFO")
        print_status(f"   التاريخ: {parsed_date}", "INFO")
        
        return msg_id
        
    except Exception as e:
        print_status(f"خطأ في حفظ الرسالة: {e}", "ERROR")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

def mark_message_deleted(msg_id):
    """تحديث حالة حذف الرسالة من الشريحة"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('UPDATE sms SET deleted_from_sim = 1 WHERE id = ?', (msg_id,))
        conn.commit()
        return True
    except Exception as e:
        print_status(f"خطأ في تحديث حالة حذف الرسالة: {e}", "ERROR")
        return False
    finally:
        conn.close()

def get_user_by_telegram_id(telegram_id):
    """الحصول على بيانات المستخدم من خلال معرف التليجرام"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = c.fetchone()
        return user
    except Exception as e:
        print_status(f"خطأ في البحث عن المستخدم: {e}", "ERROR")
        return None
    finally:
        conn.close()

def save_or_update_user(telegram_id, username=None, phone_number=None, is_admin=0):
    """حفظ أو تحديث بيانات المستخدم"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO users (telegram_id, username, phone_number, is_admin)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(telegram_id) 
                    DO UPDATE SET username=?, phone_number=?''',
                 (telegram_id, username, phone_number, is_admin, username, phone_number))
        conn.commit()
        return True
    except Exception as e:
        print_status(f"خطأ في حفظ/تحديث المستخدم: {e}", "ERROR")
        return False
    finally:
        conn.close()

def add_verification(user_id, sms_id, status):
    """إضافة سجل تحقق جديد"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('''INSERT INTO verification (user_id, sms_id, status, verified_at)
                    VALUES (?, ?, ?, ?)''',
                 (user_id, sms_id, status, now))
        if status == 'success':
            c.execute('UPDATE sms SET verified_by = ? WHERE id = ?', (user_id, sms_id))
        conn.commit()
        return True
    except Exception as e:
        print_status(f"خطأ في إضافة سجل التحقق: {e}", "ERROR")
        return False
    finally:
        conn.close()

def get_unverified_messages():
    """الحصول على الرسائل غير المتحقق منها"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''SELECT * FROM sms 
                    WHERE verified_by IS NULL 
                    ORDER BY received_date ASC''')
        messages = c.fetchall()
        return messages
    except Exception as e:
        print_status(f"خطأ في جلب الرسائل غير المتحقق منها: {e}", "ERROR")
        return []
    finally:
        conn.close()

def get_user_stats(user_id):
    """جلب إحصائيات المستخدم للعمليات الناجحة فقط"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # عمليات التحقق الناجحة فقط
        c.execute('''
            SELECT 
                COUNT(*) as successful,
                MAX(verified_at) as last_activity
            FROM verification
            WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        
        successful, last_activity = c.fetchone()
        
        return {
            'successful_verifications': successful or 0,
            'last_activity': last_activity
        }
        
    except Exception as e:
        print_status(f"خطأ في جلب إحصائيات المستخدم: {e}", "ERROR")
        return {
            'successful_verifications': 0,
            'last_activity': None
        }
    finally:
        conn.close()