from .paths import DATA_DIR

# Project settings
DB_PATH = str(DATA_DIR / 'sms_messages.db')
RECONNECT_INTERVAL = 10  # seconds
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1
POLL_INTERVAL = 10  # seconds for SMS polling

# Telegram Bot settings
TELEGRAM_BOT_TOKEN = '6243200710:AAFDH5QmjtOT4ldBAumRnNTDYsWj33kf0TQ'  # Get this from @BotFather
TELEGRAM_MESSAGE_CHECK_INTERVAL = 10  # seconds
MAX_MESSAGE_LENGTH = 4096  # Telegram's max message length