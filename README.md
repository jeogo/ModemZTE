# SMS to Telegram Relay System

A robust system that receives SMS messages via a GSM modem and forwards them to a Telegram bot.

## Features

- Automatic GSM modem detection and configuration
- SMS message reception and processing
- Telegram bot integration
- SQLite database storage
- Robust error handling and logging
- Support for various message encodings (UCS2, UTF-8, GSM)

## Requirements

- Python 3.8+
- pyserial
- python-telegram-bot
- sqlite3

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your Telegram bot:
   - Create a bot using BotFather and get the token
   - Add your bot token to config.py
   - Start a chat with your bot and save the chat ID to telegram_chat_id.txt

## Usage

Run the main script:
```bash
python main.py
```

The system will:
1. Detect your GSM modem
2. Initialize the SMS receiving system
3. Start the Telegram bot
4. Begin forwarding messages

## Configuration

Edit `config.py` to customize:
- Modem settings
- Telegram bot settings
- Logging preferences
- Database configuration

## Error Handling

The system includes comprehensive error handling:
- Modem connection issues
- Message processing errors
- Database operations
- Telegram API interactions

## Logs

- `error.log`: Contains error messages and warnings
- `received.log`: Tracks received messages

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
