import sys
import os
import time
import threading
from src.sms.modem import find_modem_port, listen_for_sms_with_event
from src.bot.telegram_bot import run_bot
from src.utils.db import init_db
from src.utils.logger import setup_logger, print_status
from src.utils.paths import DATA_DIR

# تأكد من وجود مجلد data
DATA_DIR.mkdir(exist_ok=True)

logger = setup_logger('main')

LOCK_FILE = 'bot.lock'
if os.path.exists(LOCK_FILE):
    print('❌ يوجد نسخة أخرى من البوت تعمل بالفعل. الرجاء إغلاقها أولاً.')
    exit(1)
with open(LOCK_FILE, 'w') as f:
    f.write('lock')
import atexit
def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
atexit.register(remove_lock)

def run_modem_service():
    """Run the modem SMS polling service forever."""
    while True:
        try:
            port = find_modem_port()
            if not port:
                print_status("No modem found. Retrying in 10 seconds...", "ERROR")
                time.sleep(10)
                continue
            listen_for_sms_with_event(port, threading.Event())
        except Exception as e:
            print_status(f"Error: {str(e)}", "ERROR")
            time.sleep(5)

def run_telegram_service():
    # انتظر حتى يصبح النظام جاهزاً قبل بدء البوت (حتى في التشغيل المنفصل)
    from src.utils.paths import DATA_DIR
    import os, time
    sms_ready_flag = DATA_DIR / 'sms_ready.flag'
    waited = 0
    print_status("[SYSTEM] Waiting for SMS system to become ready...", "INFO")
    while not os.path.exists(sms_ready_flag):
        time.sleep(1)
        waited += 1
        if waited % 10 == 0:
            print_status(f"[SYSTEM] Still waiting for SMS system... ({waited}s)", "INFO")
    print_status("[SYSTEM] ✓ SMS System Ready - Starting Telegram bot...", "SUCCESS")
    time.sleep(2)
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[Telegram] Bot stopped by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        print_status(f"[Telegram] Critical error: {e}", "ERROR")
        sys.exit(1)

def print_usage():
    print("Usage: python main.py [sms|telegram]")
    print("  sms      - Run the SMS modem service (saves SMS to DB)")
    print("  telegram - Run the Telegram bot service (forwards SMS from DB)")

def wait_for_sms_ready(timeout=60):
    """Wait for the SMS system to signal readiness (via flag file)."""
    sms_ready_flag = DATA_DIR / 'sms_ready.flag'
    waited = 0
    print_status("[SYSTEM] Waiting for SMS system to become ready...", "INFO")
    while waited < timeout:
        if os.path.exists(sms_ready_flag):
            print_status("[SYSTEM] ✓ SMS System Ready - Starting Telegram bot...", "SUCCESS")
            # Give the SMS system a moment to fully initialize
            time.sleep(2)
            return True
        time.sleep(1)
        waited += 1
        if waited % 10 == 0:  # Show a waiting message every 10 seconds
            print_status(f"[SYSTEM] Still waiting for SMS system... ({waited}s)", "INFO")
    print_status("[SYSTEM] SMS system did not become ready in time!", "ERROR")
    return False

def supervisor_mode():
    """Start SMS service, wait for readiness, then start Telegram bot. Monitor both."""
    print("\n==============================")
    print("[SYSTEM] STARTUP SEQUENCE STARTED")
    print("==============================\n")
    
    # Phase 1: Initialize database
    print("[SYSTEM] Phase 1: Database Setup")
    init_db()
    print("[SYSTEM] ✓ Database initialized successfully\n")

    # Phase 2: Start SMS Service
    print("[SYSTEM] Phase 2: SMS System Setup")
    print("[SYSTEM] Starting SMS modem service...")
    sms_thread = threading.Thread(target=run_modem_service, daemon=True)
    sms_thread.start()

    # Wait for SMS system to be ready
    if not wait_for_sms_ready(timeout=60):
        print_status("[SYSTEM] Error: SMS system failed to start!", "ERROR")
        sys.exit(1)

    # Phase 3: Start Telegram Bot
    print("\n[SYSTEM] Phase 3: Telegram Bot Setup")
    telegram_thread = threading.Thread(target=run_telegram_service, daemon=True)
    telegram_thread.start()
    
    print("\n==============================")
    print("[SYSTEM] STARTUP COMPLETE")
    print("==============================")
    print("[SYSTEM] ✓ SMS System: Active")
    print("[SYSTEM] ✓ Database: Connected")
    print("[SYSTEM] ✓ Telegram: Running")
    print("==============================\n")

    try:
        while True:
            if not sms_thread.is_alive():
                print_status("[SYSTEM] SMS service crashed! Restarting...", "ERROR")
                sms_thread = threading.Thread(target=run_modem_service, daemon=True)
                sms_thread.start()
            if not telegram_thread.is_alive():
                print_status("[SYSTEM] Telegram bot crashed! Restarting...", "ERROR")
                telegram_thread = threading.Thread(target=run_telegram_service, daemon=True)
                telegram_thread.start()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Supervisor stopped by user (Ctrl+C)")
        sys.exit(0)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        supervisor_mode()
    elif len(sys.argv) == 2 and sys.argv[1] in ("sms", "telegram"):
        init_db()
        print("[SYSTEM] Database initialized.")
        if sys.argv[1] == "sms":
            print("[SYSTEM] Starting SMS modem service...")
            run_modem_service()
        elif sys.argv[1] == "telegram":
            print("[SYSTEM] Starting Telegram bot service...")
            run_telegram_service()
    else:
        print_usage()
        sys.exit(1)