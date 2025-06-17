import sqlite3
from config import DB_PATH
import os
from datetime import datetime
from logger import print_status

def parse_modem_date(date_str):
    """Parse date string from modem format to SQLite datetime format"""
    try:
        # If date is None or empty, return current time
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        # Handle modem date format: "YY/MM/DD,HH:MM:SS±TZ"
        if ',' in date_str:
            date_part, time_part = date_str.split(',')
            # Split time and timezone
            time_part = time_part.split('+')[0].split('-')[0]
            
            # Parse date parts
            year, month, day = map(int, date_part.split('/'))
            hour, minute, second = map(int, time_part.split(':'))
            
            # Adjust year to full format (assume 20xx)
            year = 2000 + year
            
            # Format as SQLite datetime
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
    except Exception as e:
        print_status(f"Error parsing date {date_str}: {e}", "ERROR")
        # Return current time as fallback
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    """Initialize the SQLite database and create tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    
    # Enable UTF-8 text handling
    conn.execute('PRAGMA encoding = "UTF-8"')
    
    c = conn.cursor()
    
    # Create messages table without msg_index field
    c.execute('''CREATE TABLE IF NOT EXISTS sms_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        status TEXT,
        received_date TEXT,
        content TEXT,
        processed_at TEXT,
        deleted_from_sim INTEGER DEFAULT 0,
        is_sended_to_telegram INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

def verify_message_saved(msg_index, sender, content):
    """Verify a message was properly saved to the database"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check for exact match
        c.execute('''SELECT id FROM sms_messages 
                    WHERE sender = ? AND content = ?''',
                 (sender, content))
        result = c.fetchone()
        return result is not None
        
    except Exception as e:
        print_status(f"Error verifying message: {e}", "ERROR")
        return False
    finally:
        if conn:
            conn.close()

def message_exists(sender, content):
    """Check if message already exists in database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # Check for exact match of sender and content
        c.execute('''SELECT id FROM sms_messages 
                    WHERE sender = ? AND content = ?''', 
                 (sender, content))
        result = c.fetchone()
        if result:
            print_status(f"Message already exists in database", "DEBUG")
            return True
        return False
    except Exception as e:
        print_status(f"Database error checking message: {e}", "ERROR")
        return False
    finally:
        conn.close()

def save_sms(status, sender, timestamp, content):
    """Save new SMS message to database permanently"""
    # Parse the modem date format to SQLite format
    parsed_date = parse_modem_date(timestamp)
    
    # Don't save if message already exists
    if message_exists(sender, content):
        print_status(f"Message already exists in database", "DEBUG")
        return True
        
    conn = sqlite3.connect(DB_PATH)
    
    # Enable UTF-8 text handling
    conn.execute('PRAGMA encoding = "UTF-8"')
    
    c = conn.cursor()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print_status(f"Saving new message: From={sender}, Content={content}", "DEBUG")
        
        c.execute('''INSERT INTO sms_messages 
                    (status, sender, received_date, content, processed_at, is_sended_to_telegram)
                    VALUES (?, ?, ?, ?, ?, 0)''',
                 (status, sender, parsed_date, content, now))
        conn.commit()
        
        print_status(f"Successfully saved message with ID {c.lastrowid}", "SUCCESS")
        return True
    except Exception as e:
        print_status(f"Database error saving message: {e}", "ERROR")
        return False
    finally:
        conn.close()

def mark_message_deleted(msg_index):
    """Mark message as deleted from SIM (tracking only, message stays in DB)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('UPDATE sms_messages SET deleted_from_sim = 1 WHERE msg_index = ?', 
                 (msg_index,))
        conn.commit()
        return True
    except Exception as e:
        print_status(f"Database error marking message deleted: {e}", "ERROR")
        return False
    finally:
        conn.close()

def mark_message_processed():
    """Update the last processed message timestamp"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('INSERT INTO last_processed (processed_at) VALUES (?)', (now,))
        conn.commit()
        return True
    except Exception as e:
        print_status(f"Database error marking message processed: {e}", "ERROR")
        return False
    finally:
        conn.close()