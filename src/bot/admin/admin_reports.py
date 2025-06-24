from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from src.utils.db import get_db_connection
from src.utils.logger import print_status
import sqlite3

# قائمة فترات التقارير للأدمين
ADMIN_REPORTS_MENU = ReplyKeyboardMarkup(
    [
        ['تقرير اليوم', 'تقرير أمس'],
        ['آخر 7 أيام', 'آخر 30 يوم'],
        ['تقرير مخصص', 'إحصائيات شاملة'],
        ['العودة للقائمة الرئيسية']
    ],
    resize_keyboard=True
)

async def send_admin_reports_menu(bot, chat_id):
    """إرسال قائمة التقارير للأدمين"""
    try:        await bot.send_message(
            chat_id=chat_id,
            text="*نظام التقارير الإدارية*\n\nاختر نوع التقرير الذي تريده:",
            reply_markup=ADMIN_REPORTS_MENU,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error sending admin reports menu: {e}")

def get_users_stats_for_period(start_date, end_date):
    """جلب إحصائيات المستخدمين لفترة معينة"""
    try:
        with get_db_connection(commit_on_success=False) as conn:
            cursor = conn.execute('''
                SELECT 
                    u.username,
                    u.phone_number,
                    u.telegram_id,
                    COUNT(v.id) as total_verifications,
                    SUM(CASE WHEN v.status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN v.status = 'failed' THEN 1 ELSE 0 END) as failed,
                    MAX(v.verified_at) as last_activity
                FROM users u
                LEFT JOIN verification v ON u.id = v.user_id 
                    AND v.verified_at BETWEEN ? AND ?
                WHERE u.is_admin = 0
                GROUP BY u.id, u.username, u.phone_number, u.telegram_id
                ORDER BY total_verifications DESC
            ''', (start_date, end_date))
            
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print_status(f"خطأ في جلب إحصائيات المستخدمين: {e}", "ERROR")
        return []

def get_system_stats_for_period(start_date, end_date):
    """جلب إحصائيات النظام لفترة معينة"""
    try:
        with get_db_connection(commit_on_success=False) as conn:
            # إحصائيات الرسائل
            cursor = conn.execute('''
                SELECT COUNT(*) as total_messages
                FROM sms 
                WHERE received_date BETWEEN ? AND ?
            ''', (start_date, end_date))
            
            total_messages = cursor.fetchone()[0] or 0
            
            # إحصائيات التحقق
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_verifications,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM verification 
                WHERE verified_at BETWEEN ? AND ?
            ''', (start_date, end_date))
            
            result = cursor.fetchone()
            total_verifications = result[0] or 0
            successful = result[1] or 0
            failed = result[2] or 0
            
            # عدد المستخدمين النشطين
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT user_id) as active_users
                FROM verification 
                WHERE verified_at BETWEEN ? AND ?
            ''', (start_date, end_date))
            
            active_users = cursor.fetchone()[0] or 0
            
            return {
                'total_messages': total_messages,
                'total_verifications': total_verifications,
                'successful_verifications': successful,
                'failed_verifications': failed,
                'active_users': active_users,
                'success_rate': round((successful / total_verifications * 100) if total_verifications > 0 else 0, 2)
            }
    except Exception as e:
        print_status(f"خطأ في جلب إحصائيات النظام: {e}", "ERROR")
        return {}

async def generate_period_report(bot, chat_id, period_type):
    """إنشاء تقرير لفترة محددة"""
    try:
        now = datetime.now()
        
        if period_type == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            period_name = "اليوم"
        elif period_type == 'yesterday':
            start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date.replace(hour=23, minute=59, second=59)
            period_name = "أمس"
        elif period_type == 'week':
            start_date = now - timedelta(days=7)
            end_date = now
            period_name = "آخر 7 أيام"
        elif period_type == 'month':
            start_date = now - timedelta(days=30)
            end_date = now
            period_name = "آخر 30 يوم"
        else:           
            try:
                await bot.send_message(chat_id=chat_id, text="نوع التقرير غير صحيح")
            except Exception as e:
                print(f"Error sending error message: {e}")
            return
        
        # تحويل التواريخ إلى نص للقاعدة
        start_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # جلب الإحصائيات
        system_stats = get_system_stats_for_period(start_str, end_str)
        users_stats = get_users_stats_for_period(start_str, end_str)
        
        # إنشاء التقرير
        report = f"""
*تقرير {period_name}*
من: {start_date.strftime('%Y/%m/%d %H:%M')}
إلى: {end_date.strftime('%Y/%m/%d %H:%M')}

إحصائيات عامة:
• إجمالي الرسائل: `{system_stats.get('total_messages', 0)}`
• إجمالي عمليات التحقق: `{system_stats.get('total_verifications', 0)}`
• العمليات الناجحة: `{system_stats.get('successful_verifications', 0)}`
• العمليات الفاشلة: `{system_stats.get('failed_verifications', 0)}`
• معدل النجاح: `{system_stats.get('success_rate', 0)}%`
• المستخدمون النشطون: `{system_stats.get('active_users', 0)}`

أكثر المستخدمين نشاطاً:
"""
        
        # إضافة أفضل 5 مستخدمين
        for i, user in enumerate(users_stats[:5], 1):
            if user['total_verifications'] > 0:
                report += f"{i}. {user['username'] or 'مجهول'} - {user['total_verifications']} عملية\n"
        
        if not any(user['total_verifications'] > 0 for user in users_stats[:5]):
            report += "لا يوجد نشاط في هذه الفترة\n"
        
        # إضافة أزرار للمزيد من التفاصيل
        buttons = [
            [InlineKeyboardButton("تفاصيل المستخدمين", callback_data=f"user_details_{period_type}")],
            [InlineKeyboardButton("تقرير مفصل", callback_data=f"detailed_report_{period_type}")],
            [InlineKeyboardButton("العودة للتقارير", callback_data="back_to_reports")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await bot.send_message(
            chat_id=chat_id,
            text=report,
            parse_mode='Markdown',
            reply_markup=markup        )
        
    except Exception as e:
        print_status(f"خطأ في إنشاء التقرير: {e}", "ERROR")
        await bot.send_message(
            chat_id=chat_id,
            text="حدث خطأ أثناء إنشاء التقرير. يرجى المحاولة مرة أخرى."
        )

async def generate_overall_stats(bot, chat_id):
    """إنشاء إحصائيات شاملة للنظام"""
    try:
        with get_db_connection(commit_on_success=False) as conn:
            # إحصائيات عامة
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END) as admins,
                    SUM(CASE WHEN is_admin = 0 THEN 1 ELSE 0 END) as regular_users
                FROM users
            ''')
            
            user_stats = cursor.fetchone()
            
            cursor = conn.execute('SELECT COUNT(*) FROM sms')
            total_sms = cursor.fetchone()[0]
            
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM verification
            ''')
            
            verification_stats = cursor.fetchone()
            
            # أحدث النشاطات
            cursor = conn.execute('''
                SELECT u.username, v.verified_at, v.status
                FROM verification v
                JOIN users u ON v.user_id = u.id
                ORDER BY v.verified_at DESC
                LIMIT 5
            ''')
            
            recent_activities = cursor.fetchall()
            
        report = f"""
*الإحصائيات الشاملة للنظام*

المستخدمون:
• إجمالي المستخدمين: `{user_stats[0]}`
• المشرفون: `{user_stats[1]}`
• المستخدمون العاديون: `{user_stats[2]}`

الرسائل:
• إجمالي الرسائل: `{total_sms}`

عمليات التحقق:
• إجمالي العمليات: `{verification_stats[0]}`
• الناجحة: `{verification_stats[1]}`
• الفاشلة: `{verification_stats[2]}`
• معدل النجاح: `{round((verification_stats[1] / verification_stats[0] * 100) if verification_stats[0] > 0 else 0, 2)}%`

آخر النشاطات:
"""
        
        for activity in recent_activities:
            username = activity[0] or 'مجهول'
            timestamp = activity[1]
            status = 'ناجح' if activity[2] == 'success' else 'فاشل'
            
            try:
                dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                time_str = dt.strftime('%m/%d %H:%M')
            except:
                time_str = timestamp
                
            report += f"• {status} {username} - {time_str}\n"
        
        await bot.send_message(
            chat_id=chat_id,
            text=report,
            parse_mode='Markdown',
            reply_markup=ADMIN_REPORTS_MENU
        )        
    except Exception as e:
        print_status(f"خطأ في إنشاء الإحصائيات الشاملة: {e}", "ERROR")
        await bot.send_message(
            chat_id=chat_id,
            text="حدث خطأ أثناء إنشاء الإحصائيات."
        )

async def handle_admin_reports(bot, chat_id, text):
    """معالجة طلبات التقارير الإدارية"""
    if text == 'تقرير اليوم':
        await generate_period_report(bot, chat_id, 'today')
    elif text == 'تقرير أمس':
        await generate_period_report(bot, chat_id, 'yesterday')
    elif text == 'آخر 7 أيام':
        await generate_period_report(bot, chat_id, 'week')
    elif text == 'آخر 30 يوم':
        await generate_period_report(bot, chat_id, 'month')
    elif text == 'إحصائيات شاملة':
        await generate_overall_stats(bot, chat_id)
    elif text == 'تقرير مخصص':
        await bot.send_message(
            chat_id=chat_id,
            text="ميزة التقرير المخصص قيد التطوير...\n\nيمكنك استخدام التقارير الجاهزة في الوقت الحالي.",
            reply_markup=ADMIN_REPORTS_MENU        )
    elif text == 'العودة للقائمة الرئيسية':
        from .admin_menu import send_admin_menu
        await send_admin_menu(bot, chat_id)
    else:
        await send_admin_reports_menu(bot, chat_id)
