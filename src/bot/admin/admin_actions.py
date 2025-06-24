import sqlite3
import re
from src.utils.config import DB_PATH, ADMIN_CHAT_IDS
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from src.utils.paths import DATA_DIR
import arabic_reshaper
from bidi.algorithm import get_display

# تسجيل الخط العربي
FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'assets', 'fonts', 'arial.ttf')
FONT_NAME = 'CustomArial'

def process_arabic_text(text):
    """معالجة النص العربي ليظهر بشكل صحيح في PDF"""
    if not text:
        return ""
    try:
        reshaped_text = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        print(f"Error processing Arabic text: {e}")
        return str(text)

def register_font():
    """تسجيل الخط العربي للـ PDF"""
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        try:
            if not os.path.exists(FONT_PATH):
                print(f"Font file not found at: {FONT_PATH}")
                return False
            custom_font = TTFont(FONT_NAME, FONT_PATH)
            pdfmetrics.registerFont(custom_font)
            print(f"Font registered successfully from: {FONT_PATH}")
            return True
        except Exception as e:
            print(f"Error registering font: {e}")
            return False
    return True

def get_all_users():
    """
    جلب جميع المستخدمين من قاعدة البيانات مع معلوماتهم الكاملة.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, telegram_id, username, phone_number, is_admin 
        FROM users 
        ORDER BY id DESC
    ''')
    users = c.fetchall()
    conn.close()
    return users

def get_user_stats(user_id):
    """
    جلب إحصائيات المستخدم: عدد عمليات التأكيد، إجمالي المبالغ، إلخ.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # جلب معلومات المستخدم الأساسية
        c.execute('''
            SELECT username, phone_number
            FROM users
            WHERE telegram_id = ?
        ''', (str(user_id),))
        user_info = c.fetchone() or (None, None)
        
        # إضافة حالة المشرف من ADMIN_CHAT_IDS
        is_admin = int(user_id) in ADMIN_CHAT_IDS
        user_info = (*user_info, is_admin)  # إضافة حالة المشرف للمعلومات
        
        # جلب إحصائيات التأكيد
        c.execute('''
            SELECT 
                COUNT(v.id) as total_verifications,
                SUM(CASE WHEN v.status = 'success' THEN 1 ELSE 0 END) as success_count,
                MAX(v.verified_at) as last_verification
            FROM verification v
            JOIN users u ON u.id = v.user_id
            WHERE u.telegram_id = ?
        ''', (str(user_id),))
        stats = c.fetchone() or (0, 0, None)
        
        # جلب آخر 5 عمليات تأكيد
        c.execute('''
            SELECT v.id, v.status, v.verified_at, s.content
            FROM verification v
            JOIN users u ON u.id = v.user_id
            JOIN sms s ON s.id = v.sms_id
            WHERE u.telegram_id = ?
            ORDER BY v.verified_at DESC
            LIMIT 5
        ''', (str(user_id),))
        recent_verifications = c.fetchall()
        
        return {
            'user_info': user_info,
            'stats': {
                'total': stats[0] or 0,
                'success': stats[1] or 0,
                'last_verification': stats[2]
            },
            'recent': recent_verifications
        }
    finally:
        conn.close()

def generate_user_pdf(user_id, output_path):
    """
    إنشاء ملف PDF يحتوي على تقرير كامل عن المستخدم.
    """
    try:
        # التأكد من تسجيل الخط
        if not register_font():
            return False
            
        # جلب بيانات المستخدم
        user_data = get_user_stats(user_id)
        if not user_data['user_info']:
            return False
            
        # إنشاء ملف PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        styles = getSampleStyleSheet()
        story = []
        
        # تعريف الأنماط مع الخط العربي
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=FONT_NAME,
            fontSize=24,
            spaceAfter=30,
            leading=35,
            alignment=1  # وسط
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=FONT_NAME,
            fontSize=14,
            leading=25,
            alignment=2  # يمين
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=FONT_NAME,
            fontSize=18,
            leading=30,
            alignment=2  # يمين
        )
        
        # إضافة العنوان
        story.append(Paragraph(process_arabic_text("تقرير المستخدم"), title_style))
        story.append(Spacer(1, 20))
        
        # معلومات المستخدم
        username, phone, is_admin = user_data['user_info']
        story.append(Paragraph(process_arabic_text(f"الاسم: {username or 'غير محدد'}"), normal_style))
        story.append(Paragraph(process_arabic_text(f"رقم الهاتف: {phone or 'غير محدد'}"), normal_style))
        story.append(Paragraph(process_arabic_text(f"نوع الحساب: {'مشرف' if is_admin else 'مستخدم عادي'}"), normal_style))
        story.append(Spacer(1, 20))
        
        # إحصائيات
        stats = user_data['stats']
        story.append(Paragraph(process_arabic_text("إحصائيات"), heading_style))
        story.append(Paragraph(process_arabic_text(f"إجمالي العمليات: {stats['total']}"), normal_style))
        story.append(Paragraph(process_arabic_text(f"العمليات الناجحة: {stats['success']}"), normal_style))
        story.append(Paragraph(process_arabic_text(f"العمليات الفاشلة: {stats['total'] - stats['success']}"), normal_style))
        if stats['last_verification']:
            story.append(Paragraph(process_arabic_text(f"آخر عملية: {stats['last_verification']}"), normal_style))
        story.append(Spacer(1, 20))
        
        # آخر العمليات
        if user_data['recent']:
            story.append(Paragraph(process_arabic_text("آخر العمليات"), heading_style))
            for v in user_data['recent']:
                status = '✓' if v[1] == 'success' else '✗'
                story.append(Paragraph(
                    process_arabic_text(f"{status} العملية #{v[0]} | {v[2]}"),
                    normal_style
                ))
                story.append(Paragraph(process_arabic_text(f"المحتوى: {v[3]}"), normal_style))
                story.append(Spacer(1, 10))
        
        # إضافة تاريخ إنشاء التقرير
        story.append(Spacer(1, 30))
        story.append(Paragraph(
            process_arabic_text(f"تم إنشاء التقرير في: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            normal_style
        ))
        
        # بناء الملف
        doc.build(story)
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return False

def get_all_sms():
    """
    جلب جميع الرسائل من قاعدة البيانات.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, sender, content, received_date FROM sms ORDER BY received_date DESC')
    messages = c.fetchall()
    conn.close()
    return messages

def get_user_verifications(telegram_id):
    """
    جلب رسائل التفعيل (التحقق) الخاصة بمستخدم معين.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT v.id, v.status, v.verified_at, s.content
        FROM verification v
        JOIN sms s ON v.sms_id = s.id
        WHERE v.telegram_id = ?
        ORDER BY v.verified_at DESC
    ''', (str(telegram_id),))
    verifications = c.fetchall()
    conn.close()
    return verifications

def get_formatted_messages(page=0, per_page=5):
    """
    جلب الرسائل من قاعدة البيانات مع تنسيق وترتيب احترافي.
    يتم جلب per_page رسائل في كل صفحة.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # جلب إجمالي عدد الرسائل
        total_messages = c.execute('SELECT COUNT(*) FROM sms').fetchone()[0]
        
        # جلب الرسائل مع معلومات التأكيد
        c.execute('''
            SELECT 
                s.id,
                s.sender,
                s.content,
                s.received_date,
                COUNT(v.id) as verification_count,
                SUM(CASE WHEN v.status = 'success' THEN 1 ELSE 0 END) as success_count
            FROM sms s
            LEFT JOIN verification v ON s.id = v.sms_id
            GROUP BY s.id
            ORDER BY s.received_date DESC
            LIMIT ? OFFSET ?
        ''', (per_page, page * per_page))
        
        messages = c.fetchall()
        
        # تنسيق كل رسالة
        formatted_messages = []
        for msg in messages:
            msg_id, sender, content, date, ver_count, success_count = msg
            ver_count = ver_count or 0
            success_count = success_count or 0
            
            # استخراج المبلغ إن وجد
            amount_match = re.search(r'(\d+(?:\.\d+)?)\s*DZD', content or '')
            amount = amount_match.group(1) if amount_match else None
            
            # تحديد نوع الرسالة
            has_amount = amount is not None
            message_type = "💰 رسالة رصيد" if has_amount else "📄 رسالة عادية"
            
            # إنشاء معاينة قصيرة للرسالة
            preview = content[:40] + "..." if len(content or '') > 40 else content
            
            # تنسيق التاريخ
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
                formatted_date = date_obj.strftime("%Y/%m/%d %H:%M")
            except:
                formatted_date = date
            
            formatted_messages.append({
                'id': msg_id,
                'sender': sender,
                'content': content,
                'preview': preview,
                'date': date,
                'formatted_date': formatted_date,
                'amount': amount,
                'has_amount': has_amount,
                'message_type': message_type,
                'verifications': {
                    'total': ver_count,
                    'success': success_count,
                    'failed': ver_count - success_count
                }
            })
        
        return {
            'messages': formatted_messages,
            'total': total_messages,
            'pages': (total_messages - 1) // per_page + 1 if total_messages > 0 else 1,
            'current_page': page
        }
        
    finally:
        conn.close()

def get_message_details(message_id):
    """جلب تفاصيل الرسالة الكاملة"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            SELECT 
                s.id,
                s.sender,
                s.content,
                s.received_date,
                COUNT(v.id) as verification_count,
                SUM(CASE WHEN v.status = 'success' THEN 1 ELSE 0 END) as success_count
            FROM sms s
            LEFT JOIN verification v ON s.id = v.sms_id
            WHERE s.id = ?
            GROUP BY s.id
        ''', (message_id,))
        
        msg = c.fetchone()
        if not msg:
            return None
            
        msg_id, sender, content, date, ver_count, success_count = msg
        ver_count = ver_count or 0
        success_count = success_count or 0
        
        # استخراج المبلغ إن وجد
        amount_match = re.search(r'(\d+(?:\.\d+)?)\s*DZD', content or '')
        amount = amount_match.group(1) if amount_match else None
        
        # جلب تفاصيل التحققات
        c.execute('''
            SELECT v.verified_at, v.status, u.username, u.phone_number
            FROM verification v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.sms_id = ?
            ORDER BY v.verified_at DESC
        ''', (message_id,))
        
        verifications = c.fetchall()
        
        return {
            'id': msg_id,
            'sender': sender,
            'content': content,
            'date': date,
            'amount': amount,
            'has_amount': amount is not None,
            'verifications': {
                'total': ver_count,
                'success': success_count,
                'failed': ver_count - success_count,
                'details': verifications
            }
        }
        
    finally:
        conn.close()
