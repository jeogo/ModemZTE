# Project settings
DB_PATH = 'sms_messages.db'
RECONNECT_INTERVAL = 5  # seconds
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1
POLL_INTERVAL = 5  # seconds for SMS polling

# Telegram Bot settings
TELEGRAM_BOT_TOKEN = '6243200710:AAFDH5QmjtOT4ldBAumRnNTDYsWj33kf0TQ'  # Get this from @BotFather
TELEGRAM_CHAT_ID_FILE = 'telegram_chat_id.txt'
TELEGRAM_MESSAGE_CHECK_INTERVAL = 10  # seconds
MAX_MESSAGE_LENGTH = 4096  # Telegram's max message length