import os
import time
import sqlite3
import asyncio
import threading
from zoneinfo import ZoneInfo  # Modern timezone support
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode

from src.utils.config import (
    DB_PATH, TELEGRAM_BOT_TOKEN,
    TELEGRAM_MESSAGE_CHECK_INTERVAL, MAX_MESSAGE_LENGTH
)
from src.utils.logger import setup_logger, print_status
from src.utils.paths import DATA_DIR
from src.utils.db import get_db_connection
from src.bot.registration import RegistrationHandler
from src.bot.verification_ui import send_main_menu, handle_user_message
from src.bot.admin.admin_utils import is_admin
from src.bot.admin.admin_actions import (
    get_all_users, get_all_sms, get_user_stats,
    generate_user_pdf
)
from src.bot.admin.admin_menu import send_admin_menu, send_users_list, send_messages_view
from src.bot.admin.admin_reports import send_admin_reports_menu, handle_admin_reports

logger = setup_logger('telegram_bot')

class TelegramBot:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.bot = Bot(token=self.bot_token)
        
        # Create Application with proper configuration for v22+
        # Completely disable job queue functionality to avoid timezone/APScheduler issues
        try:
            self.application = Application.builder().token(self.bot_token).build()
            # Explicitly set job_queue to None after building
            self.application._job_queue = None
            print_status("SUCCESS: Application created successfully (job queue disabled)", "SUCCESS")
        except Exception as e:
            print_status(f"Error creating application: {e}", "ERROR")
            # Fallback: Try with explicit job_queue disable
            try:
                builder = Application.builder()
                builder.token(self.bot_token)
                # More explicit way to disable job queue
                self.application = builder.build()
                self.application._job_queue = None
                print_status("SUCCESS: Application created with fallback method", "SUCCESS")
            except Exception as e2:
                print_status(f"Both methods failed: {e2}", "ERROR")
                raise
        
        self.chat_id = self._load_chat_id()
        self.messages_sent = 0
        self.registration = RegistrationHandler(self.bot)

    def _load_chat_id(self):
        """Load chat ID from users table."""
        try:
            with get_db_connection(commit_on_success=False) as conn:
                cursor = conn.execute('SELECT telegram_id FROM users WHERE is_admin = 1 LIMIT 1')
                row = cursor.fetchone()
                if row and row[0]:
                    print_status("SUCCESS: Chat ID loaded from database", "SUCCESS")
                    return row[0]
        except Exception as e:
            print_status(f"Error loading chat ID: {e}", "ERROR")
        return None
    
    def _save_chat_id(self, chat_id):
        """Save chat ID to users table."""
        try:
            with get_db_connection() as conn:
                cursor = conn.execute('SELECT id FROM users WHERE telegram_id = ?', (str(chat_id),))
                user = cursor.fetchone()
                if user:
                    conn.execute('UPDATE users SET is_admin = 1 WHERE telegram_id = ?', (str(chat_id),))
                else:
                    conn.execute('''INSERT INTO users (telegram_id, is_admin) 
                                   VALUES (?, 1)''', (str(chat_id),))
                print_status("SUCCESS: Chat ID saved as admin user", "SUCCESS")        
        except Exception as e:
            print_status(f"Error saving chat ID: {e}", "ERROR")
    
    def format_message(self, msg_id, sender, content, received_date):
        """Format message for Telegram."""
        return (
            f"Message #{msg_id}\n"
            f"From: {sender}\n"
            f"Date: {received_date}\n"
            f"Message:\n{content}"
        )
    
    async def send_message(self, text, chat_id=None, reply_markup=None, parse_mode='HTML'):
        """Send message to Telegram chat."""
        if not chat_id:
            chat_id = self.chat_id
        if not chat_id:
            print_status("Error: No chat ID available", "ERROR")
            return False

        try:
            response = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            if response:
                self.messages_sent += 1
                return response
            return False
        except Exception as e:
            print_status(f"Error sending message: {e}", "ERROR")
            return False
    
    async def process_unsent_messages(self, retries: int = 10):
        """Process unsent messages from database with improved error handling."""
        for attempt in range(retries):
            conn = None
            try:
                # Use a more robust database connection
                conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False, isolation_level=None)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('PRAGMA journal_mode=WAL')
                c.execute('PRAGMA busy_timeout=30000')  # 30 second timeout
                
                c.execute('''
                    SELECT id, sender, content, received_date 
                    FROM sms 
                    WHERE is_sent_to_telegram = 0 
                    ORDER BY sender, received_date ASC
                    LIMIT 50
                ''')
                messages = c.fetchall()
                
                if not messages:
                    return  # No messages to process
                
                print_status(f"📨 العثور على {len(messages)} رسالة جديدة للمعالجة", "SUCCESS")
                
                # Mark messages as being processed
                message_ids = [msg['id'] for msg in messages]
                c.execute('BEGIN IMMEDIATE')
                c.executemany('UPDATE sms SET is_sent_to_telegram = 1 WHERE id = ?', 
                             [(i,) for i in message_ids])
                conn.commit()
                
                # Process messages one by one
                successful_count = 0
                for msg in messages:
                    try:
                        msg_id, sender, content, received_date = msg['id'], msg['sender'], msg['content'], msg['received_date']
                        formatted_msg = self.format_message(msg_id, sender, content, received_date)
                        
                        # Send message with timeout
                        result = await asyncio.wait_for(
                            self.send_message(formatted_msg), 
                            timeout=30.0
                        )
                        
                        if result:
                            successful_count += 1
                        else:
                            print_status(f"⚠️ فشل في إرسال الرسالة {msg_id}", "WARN")
                            
                    except asyncio.TimeoutError:
                        print_status(f"⏰ انتهت مهلة إرسال الرسالة {msg_id}", "ERROR")
                    except Exception as e:
                        print_status(f"❌ خطأ في معالجة الرسالة {msg_id}: {e}", "ERROR")
                
                if successful_count > 0:
                    print_status(f"✅ تم إرسال {successful_count} من أصل {len(messages)} رسالة بنجاح", "SUCCESS")
                
                return  # Success, exit retry loop
                
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if 'database is locked' in error_msg and attempt < retries - 1:
                    wait_time = min(5, 0.5 * (2 ** attempt))  # Exponential backoff
                    print_status(f"🔒 قاعدة البيانات مقفلة، إعادة المحاولة خلال {wait_time:.1f} ثانية", "WARN")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print_status(f"❌ خطأ في قاعدة البيانات: {e}", "ERROR")
                    break
                    
            except Exception as e:
                print_status(f"❌ خطأ في معالجة الرسائل: {e}", "ERROR")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                break
                
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
    
    def check_sms_ready(self):
        """Check if SMS system is ready."""
        sms_ready_flag = DATA_DIR / 'sms_ready.flag'
        if os.path.exists(sms_ready_flag):
            print_status("SMS system is ready", "SUCCESS")
            return True
        print_status("SMS system is NOT ready yet", "ERROR")
        return False

async def start_command(update, context):
    """Handle /start command"""
    chat_id = update.effective_chat.id
    bot_instance = context.bot_data.get('bot_instance')
    
    if not bot_instance.registration.is_registered(chat_id):
        response = bot_instance.registration.handle_registration(chat_id, '/start')
        if response:
            await update.message.reply_text(response)
        return

    if is_admin(chat_id):
        await send_admin_menu(context.bot, chat_id)
    else:
        await send_main_menu(context.bot, chat_id)

async def handle_message(update, context):
    """Handle regular messages"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    bot_instance = context.bot_data.get('bot_instance')
    
    if not bot_instance.registration.is_registered(chat_id):
        response = bot_instance.registration.handle_registration(chat_id, text)
        if response:
            await update.message.reply_text(response)
        return

    if is_admin(chat_id):
        if text == 'المستخدمون':
            users = get_all_users()
            await send_users_list(context.bot, chat_id, users)
            return
        elif text == 'الرسائل':
            wait_msg = await context.bot.send_message(chat_id=chat_id, text="Loading messages...")            
            await send_messages_view(context.bot, chat_id, page=0, wait_message_id=wait_msg.message_id)
            return
        elif text == 'التقارير':
            await send_admin_reports_menu(context.bot, chat_id)
            return
        elif text == 'رجوع':
            await send_admin_menu(context.bot, chat_id)
            return
        elif text in ['تقرير اليوم', 'تقرير أمس', 'آخر 7 أيام', 'آخر 30 يوم', 'تقرير مخصص', 'إحصائيات شاملة']:
            await handle_admin_reports(context.bot, chat_id, text)
            return
        elif text == 'العودة للقائمة الرئيسية':
            await send_admin_menu(context.bot, chat_id)
            return

    await handle_user_message(update, context.bot)

async def handle_callback_query(update, context):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    data = query.data
    
    # معالجة عرض تفاصيل الرسالة
    if data.startswith('msg_details_'):
        parts = data.split('_')
        message_id = int(parts[2])
        return_page = int(parts[4]) if len(parts) > 4 else 0
        
        from src.bot.admin.admin_menu import send_message_details
        await send_message_details(
            context.bot, 
            chat_id, 
            message_id, 
            return_page, 
            wait_message_id=query.message.message_id
        )
    
    # معالجة التنقل بين صفحات الرسائل
    elif data.startswith('msgpage_'):
        page = int(data.split('_')[1])
        from src.bot.admin.admin_menu import send_messages_view
        await send_messages_view(
            context.bot, 
            chat_id, 
            page, 
            wait_message_id=query.message.message_id
        )
    
    # معالجة الرجوع للقائمة الرئيسية
    elif data == "back_to_menu":
        await query.delete_message()
        from src.bot.admin.admin_menu import send_admin_menu
        await send_admin_menu(context.bot, chat_id)
    
    elif data.startswith('user_'):
        telegram_id = data.split('_')[1]
        user_data = get_user_stats(telegram_id)
        
        await query.delete_message()
        
        username, phone, admin_status = user_data['user_info']
        stats = user_data['stats']
        recent = user_data['recent']
        
        msg = f"User Information:\n"
        msg += f"Name: {username or 'Not specified'}\n"
        msg += f"Phone: {phone or 'Not specified'}\n"
        msg += f"Type: {'Admin' if admin_status else 'Regular user'}\n\n"
        
        msg += "Statistics:\n"
        msg += f"Total operations: {stats['total']}\n"
        msg += f"Successful: {stats['success']}\n"
        msg += f"Failed: {stats['total'] - stats['success']}\n"
        if stats['last_verification']:
            msg += f"Last operation: {stats['last_verification']}\n\n"
        
        if recent:
            msg += "Recent operations:\n"
            for v in recent:
                status_emoji = 'SUCCESS' if v[1] == 'success' else 'FAILED'
                msg += f"{status_emoji} #{v[0]} - {v[2]}\n"
        
        buttons = [
            [
                InlineKeyboardButton("PDF Report", callback_data=f"pdf_{telegram_id}"),
                InlineKeyboardButton("Back", callback_data="back_to_users")
            ]        ]
        markup = InlineKeyboardMarkup(buttons)
        
        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=markup)
    
    # معالجة التنقل بين صفحات المستخدمين
    elif data.startswith('page_'):
        page = int(data.split('_')[1])
        users = get_all_users()
        await query.delete_message()
        await send_users_list(context.bot, chat_id, users, page=page)
    
    elif data == "back_to_users":
        await query.delete_message()
        users = get_all_users()
        await send_users_list(context.bot, chat_id, users, page=0)
    
    elif data.startswith('pdf_'):
        telegram_id = data.split('_')[1]
        pdf_path = os.path.join(DATA_DIR, f'user_{telegram_id}.pdf')
        
        if generate_user_pdf(telegram_id, pdf_path):
            with open(pdf_path, 'rb') as pdf:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=pdf,
                    caption="User Report"
                )
            os.remove(pdf_path)
        else:
            await context.bot.send_message(chat_id, "Error generating report")

def run_bot():
    """Main function to run the Telegram bot with proper async handling."""
    
    def run_bot_sync():
        """Run bot synchronously in its own event loop."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            print_status("🤖 إنشاء حلقة أحداث جديدة لبوت التليجرام", "INFO")
            
            # Run the async bot function
            loop.run_until_complete(async_run_bot())
            
        except Exception as e:
            print_status(f"❌ خطأ في تشغيل البوت: {e}", "ERROR")
            import traceback
            print_status(f"🔍 تفاصيل الخطأ: {traceback.format_exc()}", "ERROR")
        finally:
            try:
                # Clean shutdown
                if not loop.is_closed():
                    # Cancel all pending tasks
                    pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                    if pending_tasks:
                        print_status(f"🧹 إلغاء {len(pending_tasks)} مهمة معلقة", "INFO")
                        for task in pending_tasks:
                            task.cancel()
                        
                        # Wait for cancellation to complete
                        try:
                            loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                        except Exception:
                            pass
                    
                    loop.close()
                    print_status("✅ تم إغلاق حلقة الأحداث بنجاح", "SUCCESS")
            except Exception as e:
                print_status(f"⚠️ خطأ في إغلاق حلقة الأحداث: {e}", "WARN")
    
    async def async_run_bot():
        """Async bot runner with improved error handling."""
        bot_instance = None
        application = None
        processor_task = None
        
        try:
            print_status("🚀 بدء خدمة بوت التليجرام", "SUCCESS")
            
            # Create bot instance
            bot_instance = TelegramBot()
            
            # Wait for SMS system to be ready
            print_status("⏳ انتظار جاهزية نظام SMS...", "INFO")
            ready_attempts = 0
            while not bot_instance.check_sms_ready() and ready_attempts < 30:
                await asyncio.sleep(2)
                ready_attempts += 1
            
            if ready_attempts >= 30:
                print_status("⚠️ انتهت مهلة انتظار نظام SMS، المتابعة مع ذلك", "WARN")
            else:
                print_status("✅ نظام SMS جاهز", "SUCCESS")
            
            application = bot_instance.application
            application.bot_data['bot_instance'] = bot_instance
            
            # Add handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            application.add_handler(CallbackQueryHandler(handle_callback_query))
            
            print_status("📱 إضافة معالجات الرسائل", "SUCCESS")
            
            async def safe_message_processor():
                """Safe message processor with error handling."""
                consecutive_errors = 0
                max_consecutive_errors = 5
                
                while consecutive_errors < max_consecutive_errors:
                    try:
                        await bot_instance.process_unsent_messages()
                        consecutive_errors = 0  # Reset on success
                        await asyncio.sleep(TELEGRAM_MESSAGE_CHECK_INTERVAL)
                        
                    except Exception as e:
                        consecutive_errors += 1
                        print_status(f"❌ خطأ في معالج الرسائل (المحاولة {consecutive_errors}): {e}", "ERROR")
                        
                        # Exponential backoff
                        wait_time = min(30, 2 ** consecutive_errors)
                        await asyncio.sleep(wait_time)
                
                print_status("❌ تم تعطيل معالج الرسائل بسبب كثرة الأخطاء", "ERROR")
            
            # Start the message processor as a background task
            processor_task = asyncio.create_task(safe_message_processor())
            
            print_status("🔄 بدء معالج الرسائل في الخلفية", "INFO")
              # Initialize and start the application properly
            try:
                await application.initialize()
                print_status("✅ تم تهيئة التطبيق بنجاح", "SUCCESS")
                
                await application.start()
                print_status("🚀 تم بدء التطبيق بنجاح", "SUCCESS")
                
                # Start polling with improved error handling
                print_status("📡 بدء استقبال الرسائل...", "SUCCESS")
                  # Configure polling with proper error handling
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=None
                )
                
                # Keep the bot running
                print_status("✅ بوت التليجرام يعمل بنجاح", "SUCCESS")
                
                # Wait for stop signal (this will run indefinitely)
                try:
                    await asyncio.Future()  # Run forever until cancelled
                except asyncio.CancelledError:
                    print_status("⏹️ تم إيقاف البوت", "INFO")
                    
            except Exception as e:
                error_msg = str(e).lower()
                if 'conflict' in error_msg and 'getupdates' in error_msg:
                    print_status("🔄 تم اكتشاف نسخة أخرى من البوت، محاولة إيقافها...", "WARN")
                    await asyncio.sleep(5)  # Wait for other instance to stop
                    raise Exception("يوجد نسخة أخرى من البوت تعمل، يرجى إيقافها أولاً")
                elif 'timed out' in error_msg or 'timeout' in error_msg:
                    print_status("⏰ انتهت مهلة الاتصال، إعادة المحاولة...", "WARN")
                    raise Exception("انتهت مهلة الاتصال مع Telegram")
                else:
                    print_status(f"❌ خطأ في تشغيل التطبيق: {e}", "ERROR")
                    raise
                
        except KeyboardInterrupt:
            print_status("⏹️ تم إيقاف البوت بواسطة المستخدم (Ctrl+C)", "SUCCESS")
            
        except Exception as e:
            print_status(f"❌ خطأ عام في البوت: {e}", "ERROR")
            import traceback
            print_status(f"🔍 تفاصيل الخطأ: {traceback.format_exc()}", "ERROR")
            
        finally:
            # Cleanup
            print_status("🧹 بدء تنظيف الموارد...", "INFO")
            
            try:
                # Cancel processor task
                if processor_task and not processor_task.done():
                    processor_task.cancel()
                    try:
                        await processor_task
                    except asyncio.CancelledError:
                        print_status("✅ تم إلغاء معالج الرسائل", "SUCCESS")
                  # Stop application with proper cleanup
                if application:
                    try:
                        # Stop updater if running
                        if hasattr(application, 'updater') and application.updater and application.updater.running:
                            print_status("🛑 إيقاف المحدث...", "INFO")
                            await application.updater.stop()
                            print_status("✅ تم إيقاف المحدث", "SUCCESS")
                    except Exception as e:
                        print_status(f"⚠️ خطأ في إيقاف المحدث: {e}", "WARN")
                    
                    try:
                        # Stop application if running
                        if hasattr(application, 'running') and application.running:
                            print_status("🛑 إيقاف التطبيق...", "INFO")
                            await application.stop()
                            print_status("✅ تم إيقاف التطبيق", "SUCCESS")
                    except Exception as e:
                        print_status(f"⚠️ خطأ في إيقاف التطبيق: {e}", "WARN")
                    
                    try:
                        # Shutdown application
                        print_status("🔄 إغلاق التطبيق...", "INFO")
                        await application.shutdown()
                        print_status("✅ تم إغلاق التطبيق", "SUCCESS")
                    except Exception as e:
                        print_status(f"⚠️ خطأ في إغلاق التطبيق: {e}", "WARN")
                
                # Final cleanup
                print_status("✅ تم تنظيف جميع الموارد", "SUCCESS")
                        
            except Exception as e:
                print_status(f"❌ خطأ في تنظيف الموارد: {e}", "ERROR")    # Always run in a separate thread to avoid event loop conflicts
    print_status("[BOT] تشغيل البوت في بيئة محمية من تعارض حلقات الأحداث", "INFO")
    
    # Check if we need to run in a separate thread
    import threading
    try:
        # Try to get the current running loop
        current_loop = asyncio.get_running_loop()
        print_status("[WARN] تم اكتشاف حلقة أحداث موجودة، تشغيل البوت في خيط منفصل", "WARNING")
        use_thread = True
    except RuntimeError:
        # No event loop running, but still use thread for consistency
        print_status("[INFO] لا توجد حلقة أحداث نشطة، تشغيل البوت في بيئة محمية", "INFO")
        use_thread = True
    
    if use_thread:
        bot_thread = threading.Thread(target=run_bot_sync, daemon=False, name="TelegramBot")
        bot_thread.start()
        
        # Keep the main thread alive and handle shutdown
        try:
            while bot_thread.is_alive():
                bot_thread.join(timeout=1.0)
        except KeyboardInterrupt:
            print_status("⏹️ تم إيقاف البوت من الخيط الرئيسي", "INFO")
    else:
        run_bot_sync()

if __name__ == '__main__':
    run_bot()