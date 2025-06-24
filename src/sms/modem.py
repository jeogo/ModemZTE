import serial
import serial.tools.list_ports
import time
import re
import threading
from datetime import datetime, timedelta
from src.utils.db import save_sms, message_exists
from src.utils.logger import print_status
from src.utils.paths import DATA_DIR
from functools import lru_cache

# Professional PDU decoder
try:
    from smspdudecoder.easy import read_incoming_sms
    PROFESSIONAL_PDU_AVAILABLE = True
    print_status("Professional PDU decoder (smspdudecoder) loaded", "SUCCESS")
except ImportError:
    PROFESSIONAL_PDU_AVAILABLE = False
    print_status("Professional PDU decoder (smspdudecoder) not available", "WARN")

# SMSPDU library - excellent for SMS processing
try:
    import smspdu
    SMSPDU_AVAILABLE = True
    print_status("SMSPDU library loaded - excellent SMS support", "SUCCESS")
except ImportError:
    SMSPDU_AVAILABLE = False
    print_status("SMSPDU library not available", "WARN")

# SMS mode configuration
SMS_MODE = "TEXT"  # AUTO, PDU, or TEXT
PREFERRED_MODE = "TEXT"  # Use TEXT mode - it's simpler and more reliable

# Force processing configuration
FORCE_PROCESS_ALL_MESSAGES = True  # Set to True to process all messages even if already processed
SKIP_PROCESSED_CHECK = True  # Set to True to always process messages regardless of processed status

def decode_pdu_smspdu(pdu_hex):
    """
    Decode PDU using the excellent smspdu library
    This library is known to work very well
    """
    if not SMSPDU_AVAILABLE:
        return None, None, None, None
    
    try:
        print_status(f"🔍 Using SMSPDU library for: {pdu_hex[:50]}...", "DEBUG")
        
        # Remove any whitespace and validate
        pdu_hex = pdu_hex.replace(' ', '').strip()
        if not pdu_hex:
            return None, None, None, None
        
        # Use smspdu library
        sms_data = smspdu.decode(pdu_hex)
        
        if sms_data:
            # Extract data from smspdu result
            sender = sms_data.get('sender', 'Unknown')
            content = sms_data.get('text', sms_data.get('message', ''))
            
            # Handle timestamp
            timestamp = sms_data.get('timestamp')
            if timestamp:
                if hasattr(timestamp, 'strftime'):
                    date_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    date_time = str(timestamp)
            else:
                date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            status = "REC UNREAD"
            
            print_status(f"✅ SMSPDU decode successful: From {sender} - {content[:50]}...", "SUCCESS")
            return status, sender, date_time, content
        else:
            print_status("❌ SMSPDU returned empty result", "ERROR")
            return None, None, None, None
            
    except Exception as e:
        print_status(f"⚠️ SMSPDU decode failed: {e}", "WARN")
        return None, None, None, None

def decode_pdu_professional(pdu_hex):
    """
    Decode PDU using the best available libraries
    Priority: 1. SMSPDU (excellent library), 2. smspdudecoder, 3. built-in
    """
    # Try SMSPDU library first (it's known to work very well)
    if SMSPDU_AVAILABLE:
        print_status(f"🔍 Trying SMSPDU library first for: {pdu_hex[:50]}...", "DEBUG")
        status, sender, date_time, content = decode_pdu_smspdu(pdu_hex)
        if sender and content:
            print_status(f"✅ SMSPDU decode successful: From {sender} - {content[:50]}...", "SUCCESS")
            return status, sender, date_time, content
    
    # Try built-in decoder as fallback
    print_status(f"🔍 Using built-in PDU decoder for: {pdu_hex[:50]}...", "DEBUG")
    status, sender, date_time, content = decode_pdu_message(pdu_hex)
    
    # If built-in decoder succeeds, use it
    if sender and content:
        print_status(f"✅ Built-in PDU decode: From {sender} - {content[:50]}...", "DEBUG")
        return status, sender, date_time, content
    
    # Fallback to professional library if available
    if not PROFESSIONAL_PDU_AVAILABLE:
        print_status("❌ All decoders failed", "ERROR")
        return None, None, None, None
    
    try:
        print_status(f"🔍 Trying smspdudecoder library for: {pdu_hex[:50]}...", "DEBUG")
        
        # Remove any whitespace and validate
        pdu_hex = pdu_hex.replace(' ', '').strip()
        if not pdu_hex:
            return None, None, None, None
        
        # Use professional library
        sms = read_incoming_sms(pdu_hex)
        
        if sms:
            # Handle different response formats from smspdudecoder
            if hasattr(sms, 'sender'):
                sender = sms.sender or "Unknown"
            elif hasattr(sms, 'address'):
                sender = sms.address or "Unknown"
            elif isinstance(sms, dict):
                sender = sms.get('sender') or sms.get('address') or "Unknown"
            else:
                sender = "Unknown"
            
            if hasattr(sms, 'user_data'):
                content = sms.user_data or ""
            elif hasattr(sms, 'message'):
                content = sms.message or ""
            elif isinstance(sms, dict):
                content = sms.get('user_data') or sms.get('message') or ""
            else:
                content = str(sms)
            
            if hasattr(sms, 'date_time') and sms.date_time:
                timestamp = sms.date_time.strftime("%Y-%m-%d %H:%M:%S")
            elif hasattr(sms, 'timestamp') and sms.timestamp:
                timestamp = sms.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(sms, dict) and sms.get('timestamp'):
                timestamp = sms['timestamp']
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            status = "REC UNREAD"
            
            print_status(f"✅ Professional PDU decode: From {sender} - {content[:50]}...", "DEBUG")
            return status, sender, timestamp, content
        else:
            print_status("❌ Professional library returned None, trying built-in decoder", "WARN")
            return decode_pdu_message(pdu_hex)
            
    except Exception as e:
        print_status(f"⚠️ Professional PDU decode failed: {e}, trying built-in decoder", "WARN")
        return decode_pdu_message(pdu_hex)

def decode_pdu_timestamp(timestamp_hex):
    """Decode PDU timestamp from hex format"""
    try:
        if len(timestamp_hex) < 14:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Each pair represents: YY MM DD HH MM SS TZ (swapped nibbles)
        year = int(timestamp_hex[1] + timestamp_hex[0], 16) + 2000
        month = int(timestamp_hex[3] + timestamp_hex[2], 16)
        day = int(timestamp_hex[5] + timestamp_hex[4], 16)
        hour = int(timestamp_hex[7] + timestamp_hex[6], 16)
        minute = int(timestamp_hex[9] + timestamp_hex[8], 16)
        second = int(timestamp_hex[11] + timestamp_hex[10], 16)
        
        # Validate ranges
        if not (1 <= month <= 12) or not (1 <= day <= 31) or not (0 <= hour <= 23) or not (0 <= minute <= 59) or not (0 <= second <= 59):
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
    except:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_phone_number(phone_hex, type_of_address):
    """Decode phone number from PDU format"""
    try:
        # Check if it's alphanumeric (type 0xD0)
        if type_of_address == 0xD0:
            # Alphanumeric sender (like company names)
            return decode_7bit_gsm(phone_hex)
        
        # Regular phone number - swap semi-octets
        phone = ""
        for i in range(0, len(phone_hex), 2):
            if i + 1 < len(phone_hex):
                # Swap nibbles
                phone += phone_hex[i+1] + phone_hex[i]
            else:
                phone += phone_hex[i]
        
        # Remove trailing 'F' (padding)
        phone = phone.rstrip('F').rstrip('f')
        
        # Add + for international format
        if type_of_address == 0x91:
            phone = "+" + phone
            
        return phone
    except:
        return phone_hex

def decode_7bit_gsm(hex_data):
    """Decode 7-bit GSM alphabet from hex"""
    try:
        # Convert hex to binary
        binary = bin(int(hex_data, 16))[2:].zfill(len(hex_data) * 4)
        
        # Split into 7-bit chunks
        chars = []
        for i in range(0, len(binary) - 6, 7):
            chunk = binary[i:i+7]
            if len(chunk) == 7:
                char_code = int(chunk, 2)
                if char_code > 0:  # Skip null characters
                    chars.append(chr(char_code))
        
        return ''.join(chars)
    except:
        return hex_data

def decode_ucs2_message(hex_data):
    """Decode UCS2 (UTF-16BE) message from hex"""
    try:
        bytes_data = bytes.fromhex(hex_data)
        return bytes_data.decode('utf-16be', errors='ignore')
    except:
        return hex_data

def decode_pdu_message(pdu_hex):
    """Decode complete PDU message with improved short PDU handling"""
    try:
        print_status(f"🔍 Decoding PDU: {pdu_hex[:50]}...", "DEBUG")
        
        # Remove any whitespace
        pdu_hex = pdu_hex.replace(' ', '').upper()
        
        # Check minimum length - reduce minimum requirement
        if len(pdu_hex) < 12:  # Reduced from 20 to 12 for shorter PDUs
            print_status("❌ PDU too short (minimum 12 hex chars)", "ERROR")
            return None, None, None, None
        
        pos = 0
        
        try:
            # 1. SMSC length and address (can be 00 for no SMSC)
            smsc_len = int(pdu_hex[pos:pos+2], 16)
            pos += 2
            
            # Skip SMSC if present
            if smsc_len > 0:
                pos += (smsc_len * 2)
            
            if pos >= len(pdu_hex):
                print_status("❌ PDU ended after SMSC", "ERROR")
                return None, None, None, None
            
            # 2. PDU type
            pdu_type = int(pdu_hex[pos:pos+2], 16)
            pos += 2
            
            # 3. Sender address length
            if pos >= len(pdu_hex):
                # Try to decode what we have as a simple message
                return decode_simple_short_pdu(pdu_hex)
            
            sender_len = int(pdu_hex[pos:pos+2], 16)
            pos += 2
            
            # 4. Sender address type
            if pos >= len(pdu_hex):
                return decode_simple_short_pdu(pdu_hex)
            
            sender_type = int(pdu_hex[pos:pos+2], 16)
            pos += 2
            
            # 5. Sender address (round up to even number of hex digits)
            sender_hex_len = (sender_len + 1) // 2 * 2
            if pos + sender_hex_len > len(pdu_hex):
                return decode_simple_short_pdu(pdu_hex)
            
            sender_hex = pdu_hex[pos:pos+sender_hex_len]
            sender = decode_phone_number(sender_hex, sender_type)
            pos += sender_hex_len
            
            # 6. Protocol identifier (skip if present)
            if pos + 2 <= len(pdu_hex):
                pos += 2
            
            # 7. Data coding scheme
            dcs = 0x00  # Default to GSM 7-bit
            if pos + 2 <= len(pdu_hex):
                dcs = int(pdu_hex[pos:pos+2], 16)
                pos += 2
            
            # 8. Timestamp (14 hex digits = 7 bytes) - skip if not enough data
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if pos + 14 <= len(pdu_hex):
                timestamp_hex = pdu_hex[pos:pos+14]
                timestamp = decode_pdu_timestamp(timestamp_hex)
                pos += 14
            
            # 9. User data length
            udl = 0
            if pos + 2 <= len(pdu_hex):
                udl = int(pdu_hex[pos:pos+2], 16)
                pos += 2
            
            # 10. User data header (if present)
            udh_len = 0
            if pdu_type & 0x40:  # UDHI bit set
                if pos + 2 <= len(pdu_hex):
                    udh_len = int(pdu_hex[pos:pos+2], 16)
                    pos += 2 + (udh_len * 2)  # Skip UDH
            
            # 11. Message content
            remaining_hex = pdu_hex[pos:] if pos < len(pdu_hex) else ""
            
            # Decode based on data coding scheme
            if dcs == 0x00:  # 7-bit GSM
                content = decode_7bit_gsm(remaining_hex) if remaining_hex else "Empty message"
            elif dcs == 0x08:  # UCS2
                content = decode_ucs2_message(remaining_hex) if remaining_hex else "Empty message"
            else:  # Default to UCS2 for safety
                content = decode_ucs2_message(remaining_hex) if remaining_hex else "Empty message"
            
            # Extract status (assume REC UNREAD for received messages)
            status = "REC UNREAD"
            
            print_status(f"✅ PDU decoded - Sender: {sender}, Content: {content[:50]}...", "DEBUG")
            return status, sender, timestamp, content
            
        except ValueError as e:
            print_status(f"❌ PDU hex parsing error: {e}", "ERROR")
            return decode_simple_short_pdu(pdu_hex)
        
    except Exception as e:
        print_status(f"❌ PDU decode error: {e}", "ERROR")
        return decode_simple_short_pdu(pdu_hex)

def decode_simple_short_pdu(pdu_hex):
    """Decode very short or partial PDUs"""
    try:
        print_status(f"🔍 Attempting simple decode of short PDU: {pdu_hex}", "DEBUG")
        
        # For very short PDUs, try to extract what we can
        if len(pdu_hex) >= 4:
            # Try to decode as simple text
            try:
                # Take last part as potential message content
                content_hex = pdu_hex[-8:] if len(pdu_hex) >= 8 else pdu_hex
                content = bytes.fromhex(content_hex).decode('utf-8', errors='ignore').strip()
                if not content:
                    content = f"Short PDU data: {pdu_hex}"
                
                return "REC UNREAD", "Unknown", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), content
            except:
                pass
        
        # Fallback: return PDU as-is for debugging
        return "REC UNREAD", "System", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"Raw PDU: {pdu_hex}"
        
    except Exception as e:
        print_status(f"❌ Simple decode failed: {e}", "ERROR")
        return None, None, None, None

# Cache for decoded results
@lru_cache(maxsize=1000)
def _cached_decode_ucs2(hex_string):
    """Cached version of UCS2 decoding"""
    try:
        if hex_string and all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            bytes_content = bytes.fromhex(hex_string)
            return bytes_content.decode('utf-16be')
        return hex_string
    except Exception:
        return hex_string


def notify_admins_new_sms(sender, content, timestamp):
    """Notify admins about new SMS"""
    try:
        from src.utils.config import ADMIN_CHAT_IDS, TELEGRAM_BOT_TOKEN
        import requests        
        if not ADMIN_CHAT_IDS:
            return False
        
        notification_text = (
            f"📨 <b>رسالة SMS جديدة</b>\n\n"
            f"📞 <b>من:</b> <code>{sender}</code>\n"
            f"📅 <b>التاريخ:</b> {timestamp}\n\n"
            f"📄 <b>المحتوى:</b>\n"
            f"<code>{content}</code>"
        )
        
        base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        
        for admin_id in ADMIN_CHAT_IDS:
            try:
                requests.post(f"{base_url}/sendMessage", data={
                    'chat_id': admin_id,
                    'text': notification_text,
                    'parse_mode': 'HTML'
                }, timeout=10)
            except:
                continue
        return True
    except:
        return False

def find_modem_port():
    """Find GSM modem port"""
    print_status("Searching for GSM modem...", "INFO")
    ports = list(serial.tools.list_ports.comports())
    
    for port in ports:
        try:
            with serial.Serial(port.device, 115200, timeout=2) as ser:
                ser.write(b'AT\r')
                time.sleep(0.5)
                response = ser.read_all().decode(errors='ignore')
                if 'OK' in response:
                    print_status(f"Modem found on {port.device}", "SUCCESS")
                    return port.device
        except:
            continue
    
    print_status("No GSM modem found", "ERROR")
    return None

def send_at_command(ser, command, wait=1):
    """Send AT command and get response"""
    try:
        ser.reset_input_buffer()
        ser.write(f"{command}\r".encode())
        time.sleep(wait)
        response = ""
        if ser.in_waiting:
            response = ser.read(ser.in_waiting).decode(errors='ignore')
        return response.strip()
    except Exception as e:
        print_status(f"AT command error: {e}", "ERROR")
        return ""


def delete_sms(ser, index):
    """Delete an SMS message from the modem"""
    try:
        cmd = f'AT+CMGD={index}'
        ser.write(f'{cmd}\r'.encode())
        response = ser.read_until(b'OK').decode(errors='ignore')
        
        if 'OK' in response:
            print_status(f"✅ Successfully deleted message {index}", "SUCCESS")
            return True
        else:
            print_status(f"❌ Failed to delete message {index}: {response}", "ERROR")
            return False
    except Exception as e:
        print_status(f"❌ Error deleting message {index}: {e}", "ERROR")
        return False

def delete_sms_with_retry(ser, index, max_retries=3, retry_delay=1):
    """Delete an SMS message with retry logic"""
    for attempt in range(max_retries):
        if delete_sms(ser, index):
            return True
        
        if attempt < max_retries - 1:
            print_status(f"⚠️ Retrying deletion of message {index} (attempt {attempt + 2}/{max_retries})", "WARN")
            time.sleep(retry_delay)
    
    print_status(f"❌ Failed to delete message {index} after {max_retries} attempts", "ERROR")
    return False

def process_message(ser, index, status, sender, date_time, content, force_save=False):
    """
    معالجة شاملة لجميع رسائل SMS مع ضمان عدم فقدان أي رسالة
    
    Args:
        ser: الاتصال التسلسلي للمودم
        index: فهرس الرسالة
        status: حالة الرسالة
        sender: المرسل
        date_time: تاريخ ووقت الرسالة
        content: محتوى الرسالة
        force_save: فرض الحفظ حتى لو كانت معالجة من قبل
    """
    try:
        print_status(f"\n=== 📨 معالجة الرسالة {index} ===", "INFO")
        print_status(f"📞 المرسل: {sender}", "INFO")
        print_status(f"📄 المحتوى: {content[:100]}...", "INFO")
        print_status(f"📅 التاريخ: {date_time}", "INFO")
        print_status(f"🔄 فرض الحفظ: {'نعم' if force_save else 'لا'}", "INFO")
        
        # Validate message data
        if not content or not sender:
            print_status("❌ محتوى فارغ أو مرسل غير صحيح", "ERROR")
            print_status(f"🔍 التفاصيل: المحتوى='{content}', المرسل='{sender}'", "ERROR")
            
            # Keep invalid messages for manual review
            print_status("⚠️ الاحتفاظ بالرسالة في المودم للمراجعة اليدوية", "WARN")
            return False
        
        # استخدام المحتوى كما هو (تبسيط مؤقت)
        original_content = content
          # التحقق من وجود الرسالة في قاعدة البيانات
        already_exists = message_exists(sender, content)
        
        if already_exists and not force_save:
            print_status(f"📋 الرسالة موجودة مسبقاً في قاعدة البيانات", "INFO")
            # حتى لو كانت موجودة، نتأكد من إشعار المشرفين إذا لم يتم ذلك
            if not is_message_fragment(content):
                print_status("📢 إرسال إشعار للمشرفين (احتياطي)", "INFO")
                notify_admins_new_sms(sender, content, date_time)
        else:            # حفظ الرسالة في قاعدة البيانات (حتى لو كانت موجودة مع force_save)
            save_result = save_sms(status, sender, date_time, content, force_save=force_save)
            
            if save_result:
                print_status(f"✅ تم حفظ الرسالة من {sender} بنجاح", "SUCCESS")
                
                # After successful save, notify admins
                notify_admins_new_sms(sender, content, date_time)
                
                # Try to delete the message from the modem
                if delete_sms_with_retry(ser, index):
                    print_status(f"✅ تم حذف الرسالة {index} من المودم", "SUCCESS")
                else:
                    print_status(f"⚠️ فشل حذف الرسالة {index} من المودم - ستتم المحاولة في الدورة التالية", "WARN")
                
                # إشعار المشرفين للرسائل المكتملة فقط
                if not is_message_fragment(content):
                    notify_result = notify_admins_new_sms(sender, content, date_time)
                    if notify_result:
                        print_status("� تم إشعار المشرفين بنجاح", "SUCCESS")
                    else:
                        print_status("⚠️ فشل في إشعار المشرفين", "WARN")
                else:
                    print_status(f"📋 جزء من رسالة متعددة - تأجيل الإشعار حتى الاكتمال", "INFO")
                
            else:
                print_status(f"❌ فشل في حفظ الرسالة من {sender}", "ERROR")
                return False        
        # استراتيجية بسيطة لحذف الرسائل من المودم
        # يمكن تطويرها لاحقاً
        print_status(f"📋 الاحتفاظ بالرسالة {index} في المودم", "INFO")
        
        # إحصائيات شاملة
        print_status(f"📊 إحصائيات المعالجة: المرسل={sender}, الطول={len(content)}, الحالة={status}", "INFO")
        
        return True
        
    except Exception as e:
        print_status(f"❌ خطأ في معالجة الرسالة {index}: {str(e)}", "ERROR")
        import traceback
        print_status(f"🔍 تفاصيل الخطأ: {traceback.format_exc()}", "ERROR")
        
        # في حالة الخطأ، لا نحذف الرسالة للمراجعة اليدوية
        print_status(f"⚠️ الاحتفاظ بالرسالة {index} للمراجعة اليدوية", "WARN")
        return False

def decode_sender(sender):
    """
    Enhanced sender decoder that always returns proper UTF-8 encoded sender
    Supports UCS2, UTF-8, and plain text formats
    """
    try:
        if not sender:
            return ""
            
        print_status(f"🔍 Decoding sender: {sender}", "DEBUG")
        
        # Clean sender string
        clean_sender = sender.replace('+', '').replace(' ', '').strip()
        
        # If it's already plain text (contains non-hex characters), ensure UTF-8
        if not all(c in '0123456789ABCDEFabcdef' for c in clean_sender):
            # Ensure proper UTF-8 encoding by normalizing
            try:
                # Convert to bytes and back to ensure proper UTF-8
                utf8_bytes = sender.encode('utf-8', errors='replace')
                utf8_sender = utf8_bytes.decode('utf-8').strip()
                print_status(f"✅ Plain text sender (UTF-8 normalized): {utf8_sender}", "DEBUG")
                return utf8_sender
            except Exception as e:
                print_status(f"⚠️ UTF-8 normalization failed: {e}", "DEBUG")
                return sender.strip()
        
        # Try decoding hex-encoded sender
        decoded_results = []
        
        # Method 1: UCS2/UTF-16BE decoding - for 4-char hex groups
        if len(clean_sender) % 4 == 0 and len(clean_sender) >= 4:
            try:
                hex_bytes = bytes.fromhex(clean_sender)
                # Try UTF-16BE first (UCS2)
                decoded = hex_bytes.decode('utf-16be', errors='ignore').strip()
                if decoded and len(decoded) > 0 and decoded.isprintable():
                    decoded_results.append(("UCS2/UTF-16BE", decoded))
                    print_status(f"✅ UCS2/UTF-16BE decode result: {decoded}", "DEBUG")
            except Exception as e:
                print_status(f"⚠️ UCS2/UTF-16BE decode failed: {e}", "DEBUG")        
        # Method 2: Direct UTF-8 hex decoding
        try:
            if len(clean_sender) % 2 == 0:
                hex_bytes = bytes.fromhex(clean_sender)
                decoded = hex_bytes.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                if decoded and len(decoded) > 0 and decoded.isprintable():
                    decoded_results.append(("UTF-8", decoded))
                    print_status(f"✅ UTF-8 hex decode result: {decoded}", "DEBUG")
        except Exception as e:
            print_status(f"⚠️ UTF-8 hex decode failed: {e}", "DEBUG")
        
        # Method 3: Try UTF-16LE decoding
        try:
            if len(clean_sender) % 4 == 0:
                hex_bytes = bytes.fromhex(clean_sender)
                decoded = hex_bytes.decode('utf-16le', errors='ignore').strip()
                if decoded and len(decoded) > 0 and decoded.isprintable():
                    decoded_results.append(("UTF-16LE", decoded))
                    print_status(f"✅ UTF-16LE decode result: {decoded}", "DEBUG")
        except Exception as e:
            print_status(f"⚠️ UTF-16LE decode failed: {e}", "DEBUG")
        
        # Choose the best result (prioritize longer, printable results)
        if decoded_results:
            # Sort by: 1) printable content, 2) length, 3) method priority
            method_priority = {"UCS2/UTF-16BE": 3, "UTF-8": 2, "UTF-16LE": 1}
            best_result = max(decoded_results, 
                            key=lambda x: (x[1].isprintable(), len(x[1]), method_priority.get(x[0], 0)))
            method, decoded = best_result
            
            # Final UTF-8 normalization to ensure proper database storage
            try:
                final_sender = decoded.encode('utf-8', errors='replace').decode('utf-8').strip()
                print_status(f"✅ Final decode result ({method}): {final_sender}", "SUCCESS")
                return final_sender
            except Exception:
                print_status(f"✅ Decode result ({method}): {decoded}", "SUCCESS")
                return decoded
        
        # If all decoding fails, normalize original sender to UTF-8
        try:
            utf8_fallback = sender.encode('utf-8', errors='replace').decode('utf-8').strip()
            print_status(f"⚠️ Using normalized original sender: {utf8_fallback}", "WARN")
            return utf8_fallback
        except Exception:
            print_status(f"⚠️ Returning original sender as-is: {sender}", "WARN")
            return sender.strip()
        
    except Exception as e:
        print_status(f"❌ Error decoding sender: {e}", "ERROR")
        # Always return a UTF-8 safe string
        try:
            return (sender or "").encode('utf-8', errors='replace').decode('utf-8').strip()
        except:
            return ""

def decode_message_content(content):
    """Decode message content with improved UCS2 support"""
    try:
        print_status(f"🔍 Decoding content: {content[:50]}...", "DEBUG")
        
        # If it's plain text, return as is
        if not all(c in '0123456789ABCDEFabcdef' for c in content):
            print_status(f"✅ Content is plain text", "DEBUG")
            return content
        
        # Try UCS2 decoding (UTF-16BE)
        if len(content) % 4 == 0:
            try:
                decoded = ""
                for i in range(0, len(content), 4):
                    hex_char = content[i:i+4]
                    if hex_char:
                        char_code = int(hex_char, 16)
                        if char_code != 0:  # Skip null characters
                            decoded += chr(char_code)
                
                decoded = decoded.strip()
                if decoded:
                    print_status(f"✅ UCS2 decoded content: {decoded[:100]}...", "DEBUG")
                    return decoded
                    
            except Exception as e:
                print_status(f"⚠️ UCS2 decode failed: {e}", "DEBUG")
        
        # Try simple hex to UTF-8
        try:
            bytes_content = bytes.fromhex(content)
            decoded = bytes_content.decode('utf-8', errors='ignore').strip()
            if decoded:
                print_status(f"✅ Hex decoded content: {decoded[:100]}...", "DEBUG")
                return decoded
        except Exception as e:
            print_status(f"⚠️ Hex decode failed: {e}", "DEBUG")
        
        # Return original if all decoding fails
        print_status(f"⚠️ Could not decode content, returning original", "WARN")
        return content
        
    except Exception as e:
        print_status(f"❌ Error decoding content: {e}", "ERROR")
        return content

def init_modem(ser, preferred_mode="AUTO"):
    """Initialize modem with smart mode selection (TEXT/PDU)"""
    print_status(f"\n--- Modem Initialization Sequence (Mode: {preferred_mode}) ---", "INFO")
    time.sleep(2)
    
    # Step 1: Basic setup
    print_status("Step 1: Basic modem setup...", "INFO")
    send_at_command(ser, "ATZ", wait=2)  # Reset
    send_at_command(ser, "ATE1", wait=1)  # Enable echo for debugging
    
    if "OK" not in send_at_command(ser, "AT", wait=2):
        raise Exception("Modem not responding")
    print_status("-> Modem responding to commands.", "SUCCESS")
    
    # Step 2: Determine the best SMS mode
    print_status("Step 2: Determining optimal SMS mode...", "INFO")
    
    sms_mode = "PDU"  # Default
    
    if preferred_mode == "AUTO":
        # Try TEXT mode first (simpler and often more reliable)
        print_status("-> Testing TEXT mode compatibility...", "INFO")
        text_resp = send_at_command(ser, "AT+CMGF=1", wait=2)
        if "OK" in text_resp:
            # Test if text mode works properly
            test_resp = send_at_command(ser, "AT+CMGF?", wait=1)
            if "1" in test_resp:
                sms_mode = "TEXT"
                print_status("✅ -> TEXT mode is supported and will be used", "SUCCESS")
            else:
                print_status("-> TEXT mode not fully supported, switching to PDU", "INFO")
                sms_mode = "PDU"
        else:
            print_status("-> TEXT mode not supported, using PDU mode", "INFO")
            sms_mode = "PDU"
    elif preferred_mode == "TEXT":
        sms_mode = "TEXT"
    else:  # PDU
        sms_mode = "PDU"    # Step 3: Configure SMS mode
    if sms_mode == "TEXT":
        print_status("Step 3: Configuring SMS settings (TEXT Mode)...", "INFO")
        essential_commands = [
            ("AT+CMGF=1", "Setting SMS TEXT mode"),  # 1 = Text mode
            ('AT+CPMS="SM","SM","SM"', "Setting SIM storage"),
            ("AT+CNMI=2,1,0,0,0", "Setting new message notifications"),
            ("AT+CSCS=\"UCS2\"", "Setting character set to UCS2 for Unicode/Arabic support"),
            # Configure SMS parameters to prevent splitting and handle long messages
            ("AT+CSMP=17,167,0,0", "Setting SMS parameters - no splitting, GSM alphabet"),
            ("AT+CSDH=1", "Enable detailed header info to detect concatenated SMS"),
            # Try to set concatenated SMS support
            ("AT+CMMS=2", "Enable concatenated SMS support (keep connection open)")
        ]
    else:  # PDU mode
        print_status("Step 3: Configuring SMS settings (PDU Mode)...", "INFO")
        essential_commands = [
            ("AT+CMGF=0", "Setting SMS PDU mode"),  # 0 = PDU mode
            ('AT+CPMS="SM","SM","SM"', "Setting SIM storage"),
            ("AT+CNMI=2,1,0,0,0", "Setting new message notifications"),
            ("AT+CSDH=1", "Enable detailed header info to detect concatenated SMS")
        ]
    
    for cmd, desc in essential_commands:
        print_status(f"-> {desc}...", "INFO")
        resp = send_at_command(ser, cmd, wait=2)
        if "OK" not in resp:
            print_status(f"⚠️ Warning: {cmd} failed: {resp}", "WARN")
        else:
            print_status(f"✅ -> {desc} successful.", "SUCCESS")
    
    # Step 4: Verify SMS mode
    print_status(f"Step 4: Verifying SMS {sms_mode} mode...", "INFO")
    resp = send_at_command(ser, "AT+CMGF?", wait=2)
    expected_value = "1" if sms_mode == "TEXT" else "0"
    if expected_value not in resp:
        raise Exception(f"Failed to set SMS {sms_mode} mode")
    print_status(f"✅ -> SMS {sms_mode} mode confirmed.", "SUCCESS")
    
    # Step 5: Check storage capacity
    print_status("Step 5: Checking storage status...", "INFO")
    resp = send_at_command(ser, "AT+CPMS?", wait=2)
    print_status(f"-> Storage status: {resp.strip()}", "INFO")
    
    print_status(f"✅ --- Modem Initialization Complete ({sms_mode} Mode) ---", "SUCCESS")
    
    # Store the current mode globally for later use
    global SMS_MODE
    SMS_MODE = sms_mode
    
    return True

def parse_sms_message_text_mode(response):
    """Parse SMS message from AT+CMGR response in TEXT mode"""
    if '+CMGR:' not in response:
        return None
    
    try:
        lines = [line.strip() for line in response.split('\r\n') if line.strip() and line.strip() != 'OK']
        header_line = None
        content_lines = []
        
        for i, line in enumerate(lines):
            if line.startswith('+CMGR:'):
                header_line = line
                # All following lines until OK are content
                content_lines = lines[i+1:]
                break
        
        if not header_line:
            return None
        
        # Parse header: +CMGR: "status","sender",,"timestamp"
        patterns = [
            r'\+CMGR:\s*"([^"]+)","([^"]+)",[^,]*,"([^"]*)"',  # Standard format
            r'\+CMGR:\s*"([^"]+)","([^"]+)","([^"]*)"',        # Alternative format
            r'\+CMGR:\s*([^,]+),([^,]+),[^,]*,([^,\r\n]+)'     # Unquoted format
        ]
        
        match = None
        for pattern in patterns:
            match = re.search(pattern, header_line)
            if match:
                break
        
        if not match:
            print_status(f"Could not parse SMS header: {header_line}", "WARNING")
            return None
        
        status = match.group(1).strip('"')
        sender = match.group(2).strip('"')
        timestamp = match.group(3).strip('"') if len(match.groups()) >= 3 else ""
        
        # Join all content lines
        content = '\n'.join(content_lines) if content_lines else ""
        
        return {
            'status': status,
            'sender': sender,
            'timestamp': timestamp,
            'content': content
        }
        
    except Exception as e:
        print_status(f"Error parsing SMS (text mode): {e}", "ERROR")
        return None

def parse_sms_message(response):
    """Parse SMS message from AT+CMGR response"""
    if '+CMGR:' not in response:
        return None
    
    try:
        lines = [line.strip() for line in response.split('\r\n') if line.strip()]
        header_line = None
        content_line = None
        
        for i, line in enumerate(lines):
            if line.startswith('+CMGR:'):
                header_line = line
                # Next non-empty line should be the content
                if i + 1 < len(lines) and "OK" not in lines[i+1].upper():
                    content_line = lines[i + 1]
                break
        
        if not header_line or not content_line:
            return None
        
        # Parse header: +CMGR: "status","sender",,"timestamp"
        # Handle different formats that modems might return
        patterns = [
            r'\+CMGR:\s*"([^"]+)","([^"]+)",[^,]*,"([^"]*)"',  # Standard format
            r'\+CMGR:\s*"([^"]+)","([^"]+)","([^"]*)"',        # Alternative format
            r'\+CMGR:\s*([^,]+),([^,]+),[^,]*,([^,\r\n]+)'     # Unquoted format
        ]
        
        match = None
        for pattern in patterns:
            match = re.search(pattern, header_line)
            if match:
                break
        
        if not match:
            print_status(f"Could not parse SMS header: {header_line}", "WARNING")
            return None
        
        status = match.group(1).strip('"')
        sender = match.group(2).strip('"')
        timestamp = match.group(3).strip('"') if len(match.groups()) >= 3 else ""

        # Decode content if it's a hex string (from UCS2 mode)
        try:
            # Check if it's a valid hex string
            bytes.fromhex(content_line)
            # If yes, decode from UCS2 big-endian
            decoded_content = bytes.fromhex(content_line).decode('utf-16-be')
            print_status("Message content decoded from UCS2 hex.", "DEBUG")
        except (ValueError, TypeError):
            # Not a hex string, treat as plain text (GSM)
            decoded_content = content_line
        
        return {
            'status': status,
            'sender': sender,
            'timestamp': timestamp,
            'content': decoded_content
        }
        
    except Exception as e:
        print_status(f"Error parsing SMS: {e}", "ERROR")
        return None

def process_cmgl_response(resp, processed_indices, ser):
    """Process AT+CMGL response (supports both TEXT and PDU modes)"""
    messages_processed = 0
    
    if '+CMGL:' not in resp:
        return messages_processed
    
    # Determine current SMS mode
    current_mode = SMS_MODE if 'SMS_MODE' in globals() else "PDU"
    
    try:
        print_status(f"\n=== Processing {current_mode} Messages ===", "INFO")
        
        if current_mode == "TEXT":
            # Process text mode messages
            messages_processed = process_cmgl_text_mode(resp, processed_indices, ser)
        else:
            # Process PDU mode messages
            messages_processed = process_cmgl_pdu_mode(resp, processed_indices, ser)
            
    except Exception as e:
        print_status(f"❌ Error in process_cmgl_response: {e}", "ERROR")
    
    print_status(f"📊 Processing summary: {messages_processed} messages processed this round", "INFO")
    return messages_processed

def process_cmgl_text_mode(resp, processed_indices, ser):
    """Process CMGL response in TEXT mode"""
    messages_processed = 0
    
    try:
        # Split response into individual messages
        lines = resp.strip().split('\r\n')
        i = 0
        
        while i < len(lines):
            try:
                line = lines[i].strip()
                if line.startswith('+CMGL:'):
                    print_status(f"Found TEXT message line: {line}", "DEBUG")
                      # Parse TEXT mode header: +CMGL: index,"status","sender",,"timestamp"
                    header_match = re.match(r'\+CMGL:\s*(\d+),"([^"]+)","([^"]+)",[^,]*,"([^"]*)"', line)
                    if header_match:
                        index = int(header_match.group(1))
                        status = header_match.group(2)
                        sender_raw = header_match.group(3)
                        timestamp = header_match.group(4)
                        
                        # Always decode sender to ensure proper UTF-8 encoding
                        sender = decode_sender(sender_raw)
                        print_status(f"📞 Sender decoded: '{sender_raw}' → '{sender}'", "DEBUG")
                          # Skip if already processed (only if force processing is disabled)
                        if not SKIP_PROCESSED_CHECK and index in processed_indices:
                            print_status(f"📋 TEXT message {index} already processed, skipping", "DEBUG")
                            i += 1
                            continue
                        
                        # Get message content from following lines until next +CMGL or end
                        content_lines = []
                        j = i + 1
                        while j < len(lines) and not lines[j].startswith('+CMGL:') and lines[j].strip() != 'OK':
                            if lines[j].strip():
                                content_lines.append(lines[j].strip())
                            j += 1
                        
                        content = '\n'.join(content_lines) if content_lines else ""
                          # In TEXT mode with UCS2, content might be hex-encoded
                        # Try to decode if it looks like hex
                        if content and all(c in '0123456789ABCDEFabcdef' for c in content.replace(' ', '')):
                            try:
                                # Remove spaces and try to decode as UCS2
                                hex_content = content.replace(' ', '')
                                if len(hex_content) % 4 == 0:  # Valid UCS2 hex
                                    decoded_bytes = bytes.fromhex(hex_content)
                                    decoded_content = decoded_bytes.decode('utf-16be', errors='ignore')
                                    if decoded_content.strip():
                                        content = decoded_content
                                        print_status(f"✅ Decoded UCS2 content: {content[:50]}...", "DEBUG")
                            except Exception as e:
                                print_status(f"⚠️ UCS2 decode failed, using raw content: {e}", "DEBUG")
                                # Keep original content
                        
                        print_status(f"📨 Processing TEXT message {index}:", "INFO")
                        print_status(f"  Status: {status}", "INFO")
                        print_status(f"  Sender: {sender}", "INFO")
                        print_status(f"  Content: {content[:50]}...", "INFO")
                        
                        if sender and content:
                            # Check for concatenated messages and handle them
                            is_concatenated, final_content, ref_id = detect_concatenated_message(sender, content, timestamp)
                            
                            if is_concatenated and final_content:
                                # Complete concatenated message ready
                                content = final_content
                                print_status(f"✅ Using combined concatenated message: {len(content)} chars", "SUCCESS")
                            elif is_concatenated and not final_content:
                                # Partial message, wait for more parts
                                print_status(f"📋 Partial concatenated message stored, waiting for completion", "INFO")
                                processed_indices.add(index)
                                i = j
                                continue
                              # Process the message (either single or complete concatenated)
                            if process_message(ser, index, status, sender, timestamp, content, force_save=FORCE_PROCESS_ALL_MESSAGES):
                                processed_indices.add(index)
                                messages_processed += 1
                                print_status(f"✅ Successfully processed TEXT message {index}", "SUCCESS")
                            else:
                                print_status(f"❌ Failed to process TEXT message {index}", "ERROR")
                        
                        processed_indices.add(index)
                        i = j  # Move to next message
                    else:
                        i += 1
                else:
                    i += 1
                    
            except Exception as e:
                print_status(f"❌ Error processing TEXT CMGL line: {e}", "ERROR")
                i += 1
                
    except Exception as e:
        print_status(f"❌ Error in process_cmgl_text_mode: {e}", "ERROR")
    
    return messages_processed

def process_cmgl_pdu_mode(resp, processed_indices, ser):
    """Process CMGL response in PDU mode"""
    messages_processed = 0
    
    try:
        # Split response into individual messages
        lines = resp.strip().split('\r\n')
        i = 0
        
        while i < len(lines):
            try:
                line = lines[i].strip()
                if line.startswith('+CMGL:'):
                    # Extract PDU header info
                    print_status(f"Found PDU message line: {line}", "DEBUG")
                    
                    # Parse PDU header format: +CMGL: index,status,alpha,length
                    header_match = re.match(r'\+CMGL:\s*(\d+),(\d+),.*?,(\d+)', line)
                    if header_match and i + 1 < len(lines):
                        index = int(header_match.group(1))
                        status_code = int(header_match.group(2))
                        pdu_length = int(header_match.group(3))
                        
                        # Get PDU data from next line
                        pdu_hex = lines[i + 1].strip() if i + 1 < len(lines) else ""
                          # Skip if already processed (only if force processing is disabled)
                        if not SKIP_PROCESSED_CHECK and index in processed_indices:
                            print_status(f"📋 PDU message {index} already processed, skipping", "DEBUG")
                            i += 2
                            continue
                        
                        print_status(f"📨 Processing PDU message {index}:", "INFO")
                        print_status(f"  Status Code: {status_code}", "INFO")
                        print_status(f"  PDU Length: {pdu_length}", "INFO")
                        print_status(f"  PDU Data: {pdu_hex[:50]}...", "INFO")
                          # Decode PDU message using SMSPDU library first
                        status, sender_raw, date_time, content = decode_pdu_professional(pdu_hex)
                        
                        # Always decode sender to ensure proper UTF-8 encoding
                        sender = decode_sender(sender_raw) if sender_raw else sender_raw
                        if sender_raw != sender:
                            print_status(f"📞 PDU Sender decoded: '{sender_raw}' → '{sender}'", "DEBUG")
                        
                        # Debug output for troubleshooting
                        print_status(f"📋 Decoded result: status='{status}', sender='{sender}', content='{content[:50] if content else 'None'}'", "DEBUG")
                        
                        if sender and content:
                            # Process the decoded message
                            if process_message(ser, index, status, sender, date_time, content, force_save=FORCE_PROCESS_ALL_MESSAGES):
                                processed_indices.add(index)
                                messages_processed += 1
                                print_status(f"✅ Successfully processed PDU message {index}", "SUCCESS")
                            else:
                                print_status(f"❌ Failed to process PDU message {index}", "ERROR")
                        
                        processed_indices.add(index)
                        i += 2  # Skip to next message (header + content)
                    else:
                        i += 1
                else:
                    i += 1
                    
            except Exception as e:
                print_status(f"❌ Error processing PDU CMGL line: {e}", "ERROR")
                i += 1
                
    except Exception as e:
        print_status(f"❌ Error in process_cmgl_pdu_mode: {e}", "ERROR")
    
    return messages_processed

def process_new_message_notification(ser, data, processed_indices):
    """Process new message notifications (+CMTI)"""
    print_status("\n📨 New message notification received!", "INFO")
    messages_processed = 0
    
    try:
        matches = re.finditer(r'\+CMTI:\s*"([^"]+)"\s*,\s*(\d+)', data)
        
        for match in matches:
            storage, index = match.groups()
            index = int(index)
              # Skip if already processed (only if force processing is disabled)
            if not SKIP_PROCESSED_CHECK and index in processed_indices:
                print_status(f"Message {index} already processed", "DEBUG")
                continue
            
            print_status(f"📨 Processing notification for message {index}", "INFO")
            
            # Wait briefly to ensure message is ready
            time.sleep(0.5)
            
            # Try to read the message
            resp = send_at_command(ser, f'AT+CMGR={index}', wait=2)
            if '+CMGR:' not in resp:
                print_status(f"Could not read message {index}", "ERROR")
                continue
                
            # Split response into lines and clean them
            lines = [line.strip() for line in resp.split('\r\n') if line.strip()]
            
            # Find CMGR line and content
            cmgr_line = next((line for line in lines if '+CMGR:' in line), None)
            if not cmgr_line:
                print_status(f"No CMGR header found for message {index}", "ERROR")
                continue
                
            cmgr_index = lines.index(cmgr_line)
            if len(lines) <= cmgr_index + 1:
                print_status(f"No content found for message {index}", "ERROR")
                continue
                
            header = lines[cmgr_index]
            content = lines[cmgr_index + 1]
            
            # Parse header
            header_match = re.match(r'\+CMGR:\s*"([^"]+)","([^"]+)",[^"]*"([^"]*)"', header)
            if not header_match:
                print_status(f"Could not parse header for message {index}", "ERROR")
                continue
                
            status = header_match.group(1)
            sender = header_match.group(2)
            date_time = header_match.group(3)
              # Process the message
            if process_message(ser, index, status, sender, date_time, content.strip(), force_save=FORCE_PROCESS_ALL_MESSAGES):
                processed_indices.add(index)
                messages_processed += 1
                print_status(f"✅ Successfully processed notification message {index}", "SUCCESS")
            else:
                print_status(f"❌ Failed to process notification message {index}", "ERROR")
                
    except Exception as e:
        print_status(f"❌ Error processing message notification: {e}", "ERROR")
    
    return messages_processed

def scan_all_messages(ser):
    """Scan for messages using SIM storage (like old code)"""
    print_status("Scanning for messages in SIM storage...", "INFO")
    
    # Use SIM storage like the old code
    storages_to_check = ["SM"]  # Only check SIM storage
    total_processed = 0
    
    for storage in storages_to_check:
        try:            # Set current storage
            resp = send_at_command(ser, f'AT+CPMS="{storage}","{storage}","{storage}"', wait=2)
            
            if "ERROR" in resp:
                print_status(f"Storage {storage} not available", "DEBUG")
                continue
            
            # List all messages (PDU mode: 4 = ALL messages)
            resp = send_at_command(ser, 'AT+CMGL=4', wait=3)
            
            if '+CMGL:' in resp:
                print_status(f"Found messages in {storage} storage", "SUCCESS")
                processed_count = process_cmgl_response(resp, ser)
                total_processed += processed_count
            else:
                print_status("No messages found.", "INFO")
        
        except Exception as e:
            print_status(f"Error scanning messages: {e}", "ERROR")
    
    if total_processed > 0:
        print_status(f"Finished scanning. Processed {total_processed} new messages.", "SUCCESS")

    return total_processed


# Cache for pending multi-part messages
pending_multipart_messages = {}

def is_message_fragment(content):
    """Check if message content appears to be a fragment of a larger message"""
    # Common indicators of message fragments
    fragment_indicators = [
        content.endswith('...'),  # Ends with ellipsis
        content.startswith('...'),  # Starts with ellipsis
        len(content) < 20 and not any(c.isdigit() for c in content),  # Very short non-numeric
        content.strip() in ['....', '...', '..'],  # Just dots
        # Content that looks like it was cut off mid-sentence
        not content.strip().endswith(('.', '!', '?', ':', ';')) and len(content) > 30,
    ]
    
    return any(fragment_indicators)

def check_and_combine_multipart_message(sender, content, date_time):
    """Check if message should be combined with previous fragments and combine if needed"""
    try:
        # Parse datetime to group messages by time proximity (within 2 minutes)
        from datetime import datetime, timedelta
        
        # Create a key for grouping messages (sender + approximate time)
        msg_key = f"{sender}_{date_time[:11]}"  # Use date and hour/minute only
        
        # Clean up old entries (older than 10 minutes)
        current_time = datetime.now()
        to_remove = []
        for key, data in pending_multipart_messages.items():
            if current_time - data['last_update'] > timedelta(minutes=10):
                to_remove.append(key)
        
        for key in to_remove:
            del pending_multipart_messages[key]
        
        # Check if this looks like a continuation or start of multi-part message
        if is_message_fragment(content) or msg_key in pending_multipart_messages:
            
            if msg_key not in pending_multipart_messages:
                # Start new multi-part message
                pending_multipart_messages[msg_key] = {
                    'parts': [content],
                    'last_update': current_time,
                    'sender': sender
                }
                print_status(f"📝 Started multi-part message for {sender}", "INFO")
                return content  # Return as-is for now
            else:
                # Add to existing multi-part message
                pending_multipart_messages[msg_key]['parts'].append(content)
                pending_multipart_messages[msg_key]['last_update'] = current_time
                
                # Combine all parts
                combined = ' '.join(pending_multipart_messages[msg_key]['parts'])
                
                # If this seems like the end of the message, return combined content
                if not is_message_fragment(content) or len(combined) > 500:
                    print_status(f"📝 Completed multi-part message: {len(combined)} chars", "SUCCESS")
                    del pending_multipart_messages[msg_key]  # Clean up
                    return combined
                else:
                    print_status(f"📝 Added part to multi-part message: {len(combined)} chars so far", "INFO")
                    return combined  # Return partial combination
        
        # Single message, return as-is
        return content
        
    except Exception as e:
        print_status(f"❌ Error in multi-part message handling: {e}", "ERROR")
        return content  # Return original on error

def verify_modem_connection(ser):
    """Verify modem connection and reinitialize if necessary"""
    try:
        # Send a simple command and check for response
        ser.write(b'AT\r')
        time.sleep(1)
        response = ser.read_all().decode(errors='ignore')
        if 'OK' in response:
            print_status("Modem connection verified.", "SUCCESS")
            return True
        else:
            print_status("Modem not responding, reinitializing...", "WARN")
            init_modem(ser)
            return False
    except Exception as e:
        print_status(f"Error verifying modem connection: {e}", "ERROR")
        return False

def listen_for_sms(port, preferred_mode="AUTO"):
    """Main SMS listening loop with smart mode selection (TEXT/PDU)"""
    processed_indices = set()
    error_count = 0
    poll_interval = 5  # Poll every 5 seconds
    last_cleanup = time.time()
    cleanup_interval = 300  # Clean up every 5 minutes
    
    print_status(f"🚀 Starting SMS system with preferred mode: {preferred_mode}", "INFO")
    
    while True:
        try:
            with serial.Serial(port, 115200, timeout=1) as ser:
                # Initialize modem with preferred mode
                init_modem(ser, preferred_mode)
                
                # Determine the final mode that was set
                current_mode = SMS_MODE if 'SMS_MODE' in globals() else "PDU"
                print_status(f"📱 SMS system ready - Mode: {current_mode} | SMSPDU: {SMSPDU_AVAILABLE}", "SUCCESS")
                
                # Signal system is ready
                ready_flag_path = DATA_DIR / 'sms_ready.flag'
                with open(ready_flag_path, 'w') as f:
                    f.write(f'ready-{current_mode}')
                
                # Make sure we're using SIM storage
                send_at_command(ser, 'AT+CPMS="SM","SM","SM"', wait=2)
                
                last_poll = time.time()
                error_count = 0
                
                while True:
                    try:
                        current_time = time.time()
                          # Periodic cleanup of processed indices to prevent memory growth
                        if current_time - last_cleanup >= cleanup_interval:
                            if len(processed_indices) > 500:
                                # Keep only recent 100 processed indices
                                processed_indices = set(list(processed_indices)[-100:])
                                print_status(f"🧹 Cleaned up processed indices cache", "DEBUG")
                            
                            # Also cleanup old concatenated messages
                            cleanup_old_concatenated_messages()
                            
                            last_cleanup = current_time                        # Poll for messages with reduced logging
                        if current_time - last_poll >= poll_interval:
                            # Only log polling at DEBUG level
                            print_status("📱 Checking for new messages...", "DEBUG")
                            
                            # Track message processing stats
                            messages_found = 0
                            messages_processed = 0
                            messages_deleted = 0
                            
                            # Use appropriate command based on mode
                            if current_mode == "TEXT":
                                # Text mode: 4 = ALL messages
                                resp = send_at_command(ser, 'AT+CMGL="ALL"', wait=3)
                            else:
                                # PDU mode: 4 = ALL messages
                                resp = send_at_command(ser, 'AT+CMGL=4', wait=3)
                            
                            if '+CMGL:' in resp:
                                print_status("📩 Messages found, processing...", "SUCCESS")
                                messages_count = process_cmgl_response(resp, processed_indices, ser)
                                if messages_count > 0:
                                    print_status(f"✅ Processed {messages_count} new messages", "SUCCESS")
                                # Don't log when no new messages to reduce noise
                            # Don't log "no messages found" to reduce verbosity
                            
                            last_poll = current_time
                        
                        # Check for immediate notifications
                        if ser.in_waiting:
                            data = ser.read(ser.in_waiting).decode(errors='ignore')
                            if '+CMTI:' in data:
                                messages_count = process_new_message_notification(ser, data, processed_indices)
                                if messages_count > 0:
                                    print_status(f"✅ Processed {messages_count} notification messages", "SUCCESS")
                        
                        time.sleep(0.1)
                        
                    except Exception as e:
                        print_status(f"❌ Error in polling loop: {e}", "ERROR")
                        time.sleep(1)
                        
        except Exception as e:
            error_count += 1
            print_status(f"❌ Connection error: {e}", "ERROR")
            wait_time = min(30, error_count * 5)
            print_status(f"🔄 Attempting to reconnect in {wait_time} seconds...", "WARN")
            time.sleep(wait_time)


# For backward compatibility
def listen_for_sms_with_event(port, event):
    listen_for_sms(port, "TEXT")  # Use TEXT mode by default
    event.set()

def listen_for_sms_simple(port):
    listen_for_sms(port, "TEXT")  # Use TEXT mode by default

# Concatenated message handling for TEXT mode
concatenated_messages = {}  # Store parts of concatenated messages

def detect_concatenated_message(sender, content, timestamp):
    """
    SIMPLIFIED: Process all messages immediately without concatenation delay
    Returns: (is_part_of_concatenated, combined_content_if_complete, reference_id)
    """
    try:
        # SIMPLIFIED APPROACH: Process all messages immediately
        # This ensures no messages are lost while we perfect the concatenation logic
        
        print_status(f"� Processing message directly (no concatenation delay)", "DEBUG")
        
        # Always return False to indicate this is NOT a concatenated message
        # This will cause the message to be processed immediately
        return False, content, None
        
    except Exception as e:
        print_status(f"❌ Error in message processing: {e}", "ERROR")
        # Always default to processing the message
        return False, content, None

def cleanup_old_concatenated_messages():
    """Clean up old incomplete concatenated messages"""
    try:
        current_time = datetime.now()
        to_remove = []
        
        for ref_id, data in concatenated_messages.items():
            if current_time - data['last_update'] > timedelta(minutes=10):
                to_remove.append(ref_id)
        
        for ref_id in to_remove:
            del concatenated_messages[ref_id]
            
    except Exception as e:
        print_status(f"❌ Error cleaning up concatenated messages: {e}", "ERROR")
