import os
import time
import sqlite3
import requests
from config import (
    DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_FILE,
    TELEGRAM_MESSAGE_CHECK_INTERVAL, MAX_MESSAGE_LENGTH
)
from logger import setup_logger, print_status

# Set up logging
logger = setup_logger('telegram_bot')

class TelegramBot:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id_file = TELEGRAM_CHAT_ID_FILE
        self.base_url = f'https://api.telegram.org/bot{self.bot_token}'
        self.chat_id = self._load_chat_id()
        self.last_update_id = 0
        self.messages_sent = 0

    def _load_chat_id(self):
        """Load the chat ID from file or return None if not found."""
        try:
            if os.path.exists(self.chat_id_file):
                with open(self.chat_id_file, 'r') as f:
                    chat_id = f.read().strip()
                    if chat_id:
                        print_status("✅ Telegram: Chat ID loaded", "SUCCESS")
                        return chat_id
        except Exception as e:
            print_status(f"Error loading chat ID: {e}", "ERROR")
        return None

    def _save_chat_id(self, chat_id):
        """Save the chat ID to a file."""
        try:
            with open(self.chat_id_file, 'w') as f:
                f.write(str(chat_id))
            print_status("✅ Telegram: Chat ID saved", "SUCCESS")
        except Exception as e:
            print_status(f"Error saving chat ID: {e}", "ERROR")

    def get_forwarded_count(self):
        """Return the number of SMS messages actually forwarded to Telegram."""
        import sqlite3
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM sms_messages WHERE is_sended_to_telegram = 1')
            count = c.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            print_status(f"Error counting forwarded messages: {e}", "ERROR")
            return 0

    def handle_command(self, message):
        """Handle bot commands and always log action"""
        text = message.get('text', '').lower()
        chat_id = message['chat']['id']
        print_status(f"[Telegram] Handling command: {text}", "DEBUG")
        
        if text == '/start':
            welcome_msg = (
                f"✅ SMS Bot activated successfully!\n\n"
                f"Your chat ID: <code>{chat_id}</code>\n"
                f"You will receive all SMS messages here.\n\n"
                f"🚦 The system is ready to use."
            )
            sent = self.send_message(welcome_msg)
            if sent:
                print_status("✅ Telegram: Welcome message sent to user.", "SUCCESS")
            else:
                print_status("❌ Telegram: Failed to send welcome message.", "ERROR")
            print_status("✅ Telegram: Bot activated via /start", "SUCCESS")
            return True
        return False

    def wait_for_chat_id(self):
        """Wait for a message from any user to get the chat ID."""
        if self.chat_id:
            print_status("✅ Telegram: Already activated", "SUCCESS")
            return

        print_status("ℹ️ Telegram: Send /start to the bot to activate", "SUCCESS")
        
        while not self.chat_id:
            try:
                updates = requests.get(f"{self.base_url}/getUpdates", 
                                    params={'offset': self.last_update_id}).json()
                print_status(f"[Telegram] Polled updates: {updates}", "DEBUG")
                
                if updates.get('ok') and updates.get('result'):
                    for update in updates['result']:
                        self.last_update_id = update['update_id'] + 1
                        if 'message' in update:
                            message = update['message']
                            print_status(f"[Telegram] Received message: {message}", "DEBUG")
                            # Save the chat ID
                            self.chat_id = message['chat']['id']
                            self._save_chat_id(self.chat_id)
                            # Handle the command (like /start)
                            handled = self.handle_command(message)
                            if handled:
                                print_status("[Telegram] /start command handled and response sent.", "SUCCESS")
                            else:
                                print_status("[Telegram] Message received but not a command.", "INFO")
                            return
                else:
                    print_status("[Telegram] No new messages or updates.", "INFO")
                time.sleep(1)
            except Exception as e:
                print_status(f"Error while waiting for chat ID: {e}", "ERROR")
                time.sleep(5)

    def send_message(self, text):
        """Send a message to the Telegram chat."""
        if not self.chat_id:
            print_status("Error: No chat ID available", "ERROR")
            return False

        try:
            # Split message if it's too long
            if len(text) > MAX_MESSAGE_LENGTH:
                chunks = [text[i:i + MAX_MESSAGE_LENGTH] 
                         for i in range(0, len(text), MAX_MESSAGE_LENGTH)]
            else:
                chunks = [text]

            for chunk in chunks:
                response = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        'chat_id': self.chat_id,
                        'text': chunk,
                        'parse_mode': 'HTML'
                    }
                ).json()

                if not response.get('ok'):
                    print_status(f"Failed to send message: {response}", "ERROR")
                    return False
            
            self.messages_sent += 1
            return True

        except Exception as e:
            print_status(f"Error sending to Telegram: {e}", "ERROR")
            return False

    def process_unsent_messages(self):
        """Fetch and send unsent messages from the database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Get unsent messages
            c.execute('''
                SELECT id, sender, content, received_date 
                FROM sms_messages 
                WHERE is_sended_to_telegram = 0 
                ORDER BY received_date ASC
            ''')
            
            messages = c.fetchall()
            
            if messages:
                print_status(f"ℹ️ Telegram: Found {len(messages)} new messages to forward", "SUCCESS")
            
            for msg_id, sender, content, received_date in messages:
                # Format message
                message = (
                    f"📱 <b>New SMS</b>\n"
                    f"From: <code>{sender}</code>\n"
                    f"Date: <code>{received_date}</code>\n"
                    f"Message:\n<pre>{content}</pre>"
                )

                # Send to Telegram
                if self.send_message(message):
                    # Update database
                    c.execute('''
                        UPDATE sms_messages 
                        SET is_sended_to_telegram = 1 
                        WHERE id = ?
                    ''', (msg_id,))
                    conn.commit()
                    print_status(f"✅ Message forwarded to Telegram", "SUCCESS")
                else:
                    print_status(f"Failed to forward message {msg_id}", "ERROR")

        except Exception as e:
            print_status(f"Error processing messages: {e}", "ERROR")
        finally:
            if 'conn' in locals():
                conn.close()

    def poll_telegram_commands(self):
        """Continuously poll for Telegram commands and handle them."""
        while True:
            try:
                updates = requests.get(f"{self.base_url}/getUpdates", 
                                    params={'offset': self.last_update_id}).json()
                if updates.get('ok') and updates.get('result'):
                    for update in updates['result']:
                        self.last_update_id = update['update_id'] + 1
                        if 'message' in update:
                            message = update['message']
                            text = message.get('text', '').strip()
                            # Only handle /start command
                            if text == '/start':
                                print_status(f"[Telegram] Received /start command: {message}", "DEBUG")
                                self.chat_id = message['chat']['id']
                                self._save_chat_id(self.chat_id)
                                handled = self.handle_command(message)
                                if handled:
                                    print_status("[Telegram] /start command handled and response sent.", "SUCCESS")
                                else:
                                    print_status("[Telegram] /start command received but not handled.", "INFO")
                time.sleep(1)
            except Exception as e:
                print_status(f"Error polling Telegram commands: {e}", "ERROR")
                time.sleep(5)

    def check_sms_ready(self):
        """Check if the SMS system is ready by looking for the flag file."""
        import os
        sms_ready_flag = 'sms_ready.flag'
        if os.path.exists(sms_ready_flag):
            print_status("[Telegram] SMS system is ready.", "SUCCESS")
            return True
        else:
            print_status("[Telegram] SMS system is NOT ready yet.", "ERROR")
            return False

def run_bot():
    """Main function to run the Telegram bot."""
    bot = TelegramBot()
    print_status("✅ Telegram Bot Service Started", "SUCCESS")
    bot.check_sms_ready()
    # Start command polling in a background thread
    import threading
    command_thread = threading.Thread(target=bot.poll_telegram_commands, daemon=True)
    command_thread.start()
    
    # First, ensure we have a chat ID
    bot.wait_for_chat_id()
    
    print_status("🔄 Starting message monitoring...", "SUCCESS")
    
    try:
        while True:
            bot.process_unsent_messages()
            time.sleep(TELEGRAM_MESSAGE_CHECK_INTERVAL)
    except KeyboardInterrupt:
        print_status("[Telegram] Bot stopped by user (Ctrl+C)", "SUCCESS")
        return
    except Exception as e:
        print_status(f"Error in bot loop: {e}", "ERROR")
        time.sleep(5)

if __name__ == '__main__':
    run_bot()
