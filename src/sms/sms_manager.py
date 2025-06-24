"""
SMS Management Module - Handles SMS deletion and processing
"""
import time
from src.utils.logger import print_status
from src.utils.db import save_sms, message_exists
from .modem import send_at_command, notify_admins_new_sms, is_message_fragment

def delete_sms(ser, index, max_retries=3):
    """Delete an SMS message from SIM card with retries"""
    try:
        for attempt in range(max_retries):
            response = send_at_command(ser, f'AT+CMGD={index}', wait=1)
            if 'OK' in response:
                print_status(f"✅ Successfully deleted message {index} from SIM", "SUCCESS")
                return True
            else:
                if attempt < max_retries - 1:
                    print_status(f"⚠️ Retry {attempt + 1}/{max_retries} to delete message {index}", "WARN")
                    time.sleep(1)
        
        print_status(f"❌ Failed to delete message {index} after {max_retries} attempts", "ERROR")
        return False
    except Exception as e:
        print_status(f"❌ Error deleting message {index}: {e}", "ERROR")
        return False

def process_and_delete_message(ser, index, status, sender, timestamp, content, force_save=False):
    """Process a message and delete it from SIM if successful"""
    try:
        # Validate message content
        if not content or not sender:
            print_status("❌ Empty content or invalid sender", "ERROR")
            return False
        
        # Check for existing message
        already_exists = message_exists(sender, content)
        
        if already_exists and not force_save:
            print_status(f"📋 Message already in database", "INFO")
            # Ensure notification was sent
            if not is_message_fragment(content):
                notify_admins_new_sms(sender, content, timestamp)
            # Delete from SIM since it's already processed
            delete_sms(ser, index)
            return True
            
        # Save new message
        save_result = save_sms(status, sender, timestamp, content, force_save=force_save)
        
        if save_result:
            print_status(f"✅ Saved message from {sender}", "SUCCESS")
            # Send notification
            if not is_message_fragment(content):
                notify_admins_new_sms(sender, content, timestamp)
            # Delete from SIM
            delete_sms(ser, index)
            return True
        else:
            print_status("❌ Failed to save message", "ERROR") 
            return False
            
    except Exception as e:
        print_status(f"❌ Error processing message: {e}", "ERROR")
        return False
