import sqlite3
from datetime import datetime, timedelta
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import inch
from src.utils.config import DB_PATH
from src.utils.logger import print_status
import arabic_reshaper
from bidi.algorithm import get_display
import re

# تحديد مسار الخط
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(CURRENT_DIR, '..', '..', 'assets', 'fonts')
NOTO_ARABIC_FONT = os.path.join(FONTS_DIR, 'arial.ttf')
FONT_NAME = 'arial'

def ensure_arabic_fonts():
    """التأكد من وجود وتسجيل الخط العربي"""
    try:
        # التحقق من وجود الملف
        if not os.path.exists(NOTO_ARABIC_FONT):
            print_status(f"ERROR: ملف الخط غير موجود في المسار: {NOTO_ARABIC_FONT}", "ERROR")
            return False
        
        # التحقق من حجم الملف
        font_size = os.path.getsize(NOTO_ARABIC_FONT)
        if font_size < 1000:  # الملف صغير جدًا ليكون خطًا صالحًا
            print_status("ERROR: ملف الخط تالف أو غير مكتمل", "ERROR")
            return False

        # إلغاء تسجيل الخط إذا كان مسجلاً مسبقاً
        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.unregisterFont(FONT_NAME)

        # تسجيل الخط
        font = TTFont(FONT_NAME, NOTO_ARABIC_FONT)
        pdfmetrics.registerFont(font)
            
        # التحقق من نجاح التسجيل
        if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            print_status("ERROR: فشل تسجيل الخط", "ERROR")
            return False
            
        print_status("تم تسجيل الخط العربي بنجاح", "SUCCESS")
        return True

    except Exception as e:
        print_status(f"ERROR: خطأ في تسجيل الخط: {str(e)}", "ERROR")
        return False

def get_date_range(period):
    """تحديد نطاق التاريخ بناءً على الفترة المحددة"""
    now = datetime.now()
    if period == "1":      # يوم واحد
        start_date = now - timedelta(days=1)
    elif period == "3":    # 3 أيام
        start_date = now - timedelta(days=3)
    elif period == "7":    # 7 أيام
        start_date = now - timedelta(days=7)
    elif period == "30":   # شهر
        start_date = now - timedelta(days=30)
    else:                  # الكل
        start_date = datetime(2000, 1, 1)
    return start_date.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')

def get_successful_verifications(start_date, end_date):
    """جلب عمليات التحقق الناجحة من قاعدة البيانات"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            SELECT 
                s.received_date,        -- تاريخ الرسالة
                s.content,              -- محتوى الرسالة (للمبلغ)
                v.verified_at           -- وقت التحقق
            FROM verification v
            JOIN sms s ON v.sms_id = s.id
            WHERE v.status = 'success'
            AND v.verified_at BETWEEN ? AND ?
            ORDER BY v.verified_at DESC
        ''', (start_date, end_date))
        return c.fetchall()
    finally:
        conn.close()

def extract_amount(content):
    """استخراج المبلغ من نص الرسالة"""
    match = re.search(r'(\d+(?:\.\d+)?)\s*DZD', content)
    if match:
        return f"{float(match.group(1)):,.2f} DZD"
    return "غير معروف"

def format_datetime(dt_str, include_seconds=False):
    """تنسيق التاريخ والوقت"""
    dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    if include_seconds:
        return dt.strftime('%Y/%m/%d %H:%M:%S')
    return dt.strftime('%Y/%m/%d %H:%M')

def format_arabic_text(text):
    """معالجة النص العربي"""
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        print_status(f"خطأ في معالجة النص العربي: {e}", "ERROR")
        return text

def create_pdf_report(data, period, filename):
    """إنشاء تقرير PDF للعمليات"""
    
    # التحقق من تسجيل الخط
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        if not ensure_arabic_fonts():
            raise Exception("تعذر تسجيل الخط العربي")

    # إنشاء المستند
    try:
        doc = SimpleDocTemplate(
            filename,
            pagesize=landscape(A4),
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        story = []

        # تعريف نمط العنوان
        try:
            title_style = ParagraphStyle(
                'ArabicTitle',
                fontName=FONT_NAME,
                fontSize=24,
                alignment=1,
                spaceAfter=30,
                leading=35
            )
        except Exception as e:
            print_status(f"خطأ في تعريف نمط العنوان: {e}", "ERROR")
            raise

        # تحديد نص الفترة
        period_text = {
            "1": "آخر 24 ساعة",
            "3": "آخر 3 أيام",
            "7": "آخر 7 أيام",
            "30": "آخر شهر",
            "all": "كل العمليات"
        }.get(period, "كل العمليات")

        # إضافة العنوان
        title = Paragraph(format_arabic_text(f"تقرير العمليات - {period_text}"), title_style)
        story.append(title)
        story.append(Spacer(1, 20))

        # إعداد الجدول
        headers = [
            format_arabic_text("تاريخ الرسالة"),
            format_arabic_text("المبلغ"),
            format_arabic_text("وقت التحقق")
        ]
        
        table_data = [headers]
        
        for msg_date, content, verify_date in data:
            row = [
                format_datetime(msg_date),
                extract_amount(content),
                format_datetime(verify_date, True)
            ]
            table_data.append(row)

        # إنشاء وتنسيق الجدول
        try:
            col_widths = [2.7*inch, 2.2*inch, 2.7*inch]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.1, 0.5)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
                ('FONTSIZE', (0, 0), (-1, 0), 16),
                ('FONTSIZE', (0, 1), (-1, -1), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.Color(0.97, 0.97, 1.0)),
                ('GRID', (0, 0), (-1, -1), 1, colors.Color(0.3, 0.3, 0.8)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 1)]),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))

            story.append(table)
        except Exception as e:
            print_status(f"خطأ في إنشاء الجدول: {e}", "ERROR")
            raise

        # إضافة الملخص
        try:
            summary_style = ParagraphStyle(
                'ArabicSummary',
                fontName=FONT_NAME,
                fontSize=14,
                alignment=1,
                spaceAfter=30,
                textColor=colors.Color(0.1, 0.1, 0.5)
            )
            
            summary = Paragraph(
                format_arabic_text(f"إجمالي العمليات: {len(data)}"),
                summary_style
            )
            story.append(Spacer(1, 20))
            story.append(summary)
        except Exception as e:
            print_status(f"خطأ في إضافة الملخص: {e}", "ERROR")
            raise

        # بناء المستند
        try:
            doc.build(story)
            print_status("تم إنشاء التقرير بنجاح", "SUCCESS")
            return True
        except Exception as e:
            print_status(f"خطأ في بناء التقرير: {e}", "ERROR")
            raise

    except Exception as e:
        print_status(f"خطأ في إنشاء التقرير: {e}", "ERROR")
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass
        return False

def generate_report(period):
    """إنشاء تقرير للفترة المحددة"""
    try:
        start_date, end_date = get_date_range(period)
        data = get_successful_verifications(start_date, end_date)
        
        if not data:
            return None, "لا توجد عمليات تحقق ناجحة في الفترة المحددة."
        
        reports_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
        
        filename = os.path.join(reports_dir, f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
        
        if create_pdf_report(data, period, filename):
            return filename, f"تم إنشاء التقرير بنجاح! ({len(data)} عملية)"
        else:
            return None, "حدث خطأ أثناء إنشاء التقرير."
            
    except Exception as e:
        print_status(f"خطأ في إنشاء التقرير: {e}", "ERROR")
        return None, f"حدث خطأ: {str(e)}"
