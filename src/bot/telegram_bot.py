import os
import time
import sqlite3
import requests
from telegram import Update, Bot
from telegram.ext import CallbackContext, Updater
from src.utils.config import (
    DB_PATH, TELEGRAM_BOT_TOKEN,
    TELEGRAM_MESSAGE_CHECK_INTERVAL, MAX_MESSAGE_LENGTH
)
from src.utils.logger import setup_logger, print_status
from src.utils.paths import DATA_DIR
from src.bot.registration import RegistrationHandler
from src.bot.verification_ui import send_main_menu, handle_user_message

# Set up logging
logger = setup_logger('telegram_bot')

class TelegramBot:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.base_url = f'https://api.telegram.org/bot{self.bot_token}'
        self.bot = Bot(token=self.bot_token)  # Create actual bot instance
        self.chat_id = self._load_chat_id()
        self.last_update_id = 0
        self.messages_sent = 0
        self.registration = RegistrationHandler(self)

    def _load_chat_id(self):
        """تحميل معرف الدردشة من جدول المستخدمين."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT telegram_id FROM users WHERE is_admin = 1 LIMIT 1')
            row = c.fetchone()
            conn.close()
            if row and row[0]:
                print_status("✅ تم تحميل معرف الدردشة من قاعدة البيانات", "SUCCESS")
                return row[0]
        except Exception as e:
            print_status(f"خطأ في تحميل معرف الدردشة من قاعدة البيانات: {e}", "ERROR")
        return None

    def _save_chat_id(self, chat_id):
        """حفظ معرف الدردشة في جدول المستخدمين."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE telegram_id = ?', (str(chat_id),))
            user = c.fetchone()
            if user:
                c.execute('UPDATE users SET is_admin = 1 WHERE telegram_id = ?', (str(chat_id),))
            else:
                c.execute('''INSERT INTO users (telegram_id, is_admin) 
                           VALUES (?, 1)''', (str(chat_id),))
            conn.commit()
            conn.close()
            print_status("✅ تم حفظ معرف الدردشة كمستخدم مسؤول", "SUCCESS")
        except Exception as e:
            print_status(f"خطأ في حفظ معرف الدردشة: {e}", "ERROR")

    def format_message(self, msg_id, sender, content, received_date):
        """تنسيق الرسالة للإرسال إلى تيليجرام."""
        return (
            f"📱 <b>Message #{msg_id}</b>\n"
            f"From: <code>{sender}</code>\n"
            f"Date: <code>{received_date}</code>\n"
            f"Message:\n<pre>{content}</pre>"
        )

    def send_message(self, text, chat_id=None):
        """إرسال رسالة إلى دردشة التيليجرام."""
        if not chat_id:
            chat_id = self.chat_id
        if not chat_id:
            print_status("Error: No chat ID available", "ERROR")
            return False

        try:
            response = self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML'
            )
            self.messages_sent += 1
            return True
        except Exception as e:
            print_status(f"خطأ في إرسال الرسالة: {e}", "ERROR")
            return False

    def process_unsent_messages(self):
        """معالجة الرسائل غير المرسلة في قاعدة البيانات."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                SELECT id, sender, content, received_date 
                FROM sms 
                WHERE is_sent_to_telegram = 0 
                ORDER BY sender, received_date ASC
            ''')
            messages = c.fetchall()
            
            if not messages:
                return
                
            print_status(f"ℹ️ تم العثور على {len(messages)} رسالة جديدة", "SUCCESS")
            
            message_ids = [msg[0] for msg in messages]
            c.executemany('UPDATE sms SET is_sent_to_telegram = 1 WHERE id = ?', 
                         [(i,) for i in message_ids])
            conn.commit()
            
            for msg_id, sender, content, received_date in messages:
                formatted_msg = self.format_message(msg_id, sender, content, received_date)
                if self.send_message(formatted_msg):
                    print_status(f"✅ تم إرسال الرسالة رقم {msg_id}", "SUCCESS")
                
        except Exception as e:
            print_status(f"خطأ في معالجة الرسائل: {e}", "ERROR")
        finally:
            if 'conn' in locals():
                conn.close()

    def poll_telegram_commands(self):
        """Poll for Telegram updates and handle menu/callbacks/messages"""
        while True:
            try:
                updates = requests.get(f"{self.base_url}/getUpdates", 
                                    params={'offset': self.last_update_id}).json()
                if updates.get('ok') and updates.get('result'):
                    for update in updates['result']:
                        self.last_update_id = update['update_id'] + 1
                        # لم يعد هناك callback_query في النظام الجديد
                        if 'message' in update:
                            update_obj = Update.de_json(update, self.bot)
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '').strip()
                            # التحقق من حالة التسجيل
                            if not self.registration.is_registered(chat_id):
                                response = self.registration.handle_registration(chat_id, text)
                                if response:
                                    self.send_message(response, chat_id)
                                continue
                            # معالجة الأوامر
                            if text == '/start':
                                send_main_menu(self.bot, chat_id)
                            else:
                                handle_user_message(update_obj, self.bot)
                time.sleep(1)
            except Exception as e:
                print_status(f"Error polling Telegram commands: {e}", "ERROR")
                time.sleep(5)

    def check_sms_ready(self):
        """Check if the SMS system is ready."""
        sms_ready_flag = DATA_DIR / 'sms_ready.flag'
        if os.path.exists(sms_ready_flag):
            print_status("[Telegram] SMS system is ready.", "SUCCESS")
            return True
        print_status("[Telegram] SMS system is NOT ready yet.", "ERROR")
        return False

def run_bot():
    """Main function to run the Telegram bot."""
    bot = TelegramBot()
    print_status("✅ Telegram Bot Service Started", "SUCCESS")
    
    while not bot.check_sms_ready():
        time.sleep(2)
        
    import threading
    # Start command polling in a background thread
    command_thread = threading.Thread(target=bot.poll_telegram_commands, daemon=True)
    command_thread.start()
    
    print_status("🔄 Starting message monitoring...", "SUCCESS")
    try:
        while True:
            bot.process_unsent_messages()
            time.sleep(TELEGRAM_MESSAGE_CHECK_INTERVAL)
    except KeyboardInterrupt:
        print_status("[Telegram] Bot stopped by user (Ctrl+C)", "SUCCESS")
    except Exception as e:
        print_status(f"Error in bot loop: {e}", "ERROR")
        time.sleep(5)

if __name__ == '__main__':
    run_bot()
