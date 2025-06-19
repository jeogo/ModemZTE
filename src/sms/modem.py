import serial
import serial.tools.list_ports
import time
import re
from datetime import datetime
from src.utils.db import save_sms, message_exists
from src.utils.logger import print_status
from src.utils.paths import DATA_DIR
from functools import lru_cache

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

def verify_modem_connection(ser):
    """Verify modem is still responding and in text mode"""
    try:
        # Check if modem responds
        resp = send_at_command(ser, "AT", wait=1, show_debug=False)
        if "OK" not in resp:
            return False
            
        # Verify text mode is active
        resp = send_at_command(ser, "AT+CMGF?", show_debug=False)
        if "1" not in resp:
            print_status("Text mode lost, resetting...", "WARN")
            send_at_command(ser, "AT+CMGF=1")
            
        return True
    except Exception:
        return False

def decode_service_number(number):
    """Decode service numbers that are often all digits"""
    try:
        # If it's UCS2 encoded
        if all(c in '0123456789ABCDEFabcdef' for c in number):
            bytes_number = bytes.fromhex(number)
            decoded = bytes_number.decode('utf-16be')
            # Clean up and get just the digits
            digits = ''.join(c for c in decoded if c.isdigit())
            if digits:
                return digits
        return number
    except Exception as e:
        print_status(f"Error decoding service number: {e}", "ERROR")
        return number

def decode_ucs2_text(hex_string):
    """Decode UCS2 (UTF-16BE) hex string to readable text"""
    try:
        if hex_string and all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            bytes_content = bytes.fromhex(hex_string)
            return bytes_content.decode('utf-16be')
        return hex_string
    except Exception as e:
        print_status(f"Error decoding UCS2 text: {e}", "ERROR")
        return hex_string

def decode_ucs2_phone(phone_number):
    """Decode UCS2 encoded phone number back to normal format"""
    try:
        if all(c in '0123456789ABCDEFabcdef' for c in phone_number):
            # Convert from UCS2 hex to string
            bytes_number = bytes.fromhex(phone_number)
            decoded = bytes_number.decode('utf-16be')
            # Remove any null characters
            decoded = decoded.replace('\x00', '')
            return decoded
        return phone_number
    except Exception as e:
        print_status(f"Error decoding phone number: {e}", "ERROR")
        return phone_number

def decode_message_content(content, dcs=None):
    """Decode message content based on data coding scheme and content pattern"""
    try:
        # If content looks like hex (UCS2 encoded)
        if all(c in '0123456789ABCDEFabcdef' for c in content):
            # Try to decode as UTF-16BE (common for Arabic)
            try:
                bytes_content = bytes.fromhex(content)
                return bytes_content.decode('utf-16be')
            except:
                pass
            
            # Try UTF-8
            try:
                bytes_content = bytes.fromhex(content)
                return bytes_content.decode('utf-8')
            except:
                pass
        
        # For GSM 7-bit or ASCII content
        return content
    except Exception as e:
        print_status(f"Error decoding message: {e}", "ERROR")
        return content

def send_at_command(ser, command, wait=0.3, show_debug=False):
    """Send AT command and return response with optimized timing"""
    if show_debug:
        print_status(f"Sending command: {command}", "DEBUG")
    
    ser.write(f"{command}\r".encode())
    
    # Quick initial sleep for most commands
    time.sleep(0.1)
    
    resp = b''
    start_time = time.time()
    max_wait = wait  # Maximum time to wait for response
    
    while (time.time() - start_time) < max_wait:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            resp += chunk
            
            # If we got an OK or ERROR, we can return early
            if b'OK\r\n' in resp or b'ERROR\r\n' in resp:
                break
                
            # Short sleep between reads
            time.sleep(0.05)
            
    response = resp.decode(errors='ignore')
    if show_debug:
        print_status(f"Response: {response}", "DEBUG")
    return response

def fetch_message_pdu(ser, index):
    """Fetch message in PDU mode"""
    # Switch to PDU mode
    send_at_command(ser, "AT+CMGF=0")
    resp = send_at_command(ser, f'AT+CMGR={index}')
    # Switch back to text mode
    send_at_command(ser, "AT+CMGF=1")
    return resp

def fetch_message_text(ser, index):
    """Fetch message in text mode"""
    return send_at_command(ser, f'AT+CMGR={index}')

def fetch_message_raw(ser, index):
    """Fetch raw message data"""
    return send_at_command(ser, f'AT+CMGR={index},1')

def try_decode_methods(text):
    """Try different decoding methods and return all successful results"""
    results = []
    
    # Method 1: Direct UTF-16BE (UCS2)
    try:
        if all(c in '0123456789ABCDEFabcdef' for c in text):
            bytes_text = bytes.fromhex(text)
            decoded = bytes_text.decode('utf-16be')
            results.append(('UTF-16BE', decoded))
    except Exception as e:
        print_status(f"UTF-16BE decode failed: {e}", "DEBUG")

    # Method 2: UTF-8
    try:
        if all(c in '0123456789ABCDEFabcdef' for c in text):
            bytes_text = bytes.fromhex(text)
            decoded = bytes_text.decode('utf-8')
            results.append(('UTF-8', decoded))
    except Exception as e:
        print_status(f"UTF-8 decode failed: {e}", "DEBUG")

    # Method 3: GSM 7-bit
    try:
        # Try to decode as GSM 7-bit if it looks like it might be
        if any(c.isalpha() for c in text):
            decoded = text  # GSM 7-bit is usually readable as is
            results.append(('GSM-7', decoded))
    except Exception as e:
        print_status(f"GSM-7 decode failed: {e}", "DEBUG")

    # Method 4: ASCII
    try:
        if all(ord(c) < 128 for c in text):
            results.append(('ASCII', text))
    except Exception as e:
        print_status(f"ASCII decode failed: {e}", "DEBUG")

    return results

def is_service_name(text):
    """Check if the text looks like a service name (e.g. 'Mobilis', 'Djezzy')"""
    # Common service names in Algeria
    service_names = {
        'mobilis', 'djezzy', 'ooredoo', 'algerie', 'nedjma', 
        'mms', 'sms', 'info', 'service', 'bank', 'alert',
        'notification', 'marketing'
    }
    
    # Check if any word in the text matches known service names
    text_words = set(text.lower().split())
    return bool(text_words & service_names) or text.isalpha()

def decode_sender(sender):
    """Enhanced sender decoder that handles phone numbers, service names, and brands"""
    try:
        original = sender
        print_status(f"Decoding sender: {sender}", "DEBUG")
        
        # If it's not hex encoded, might be a direct service name
        if not all(c in '0123456789ABCDEFabcdef' for c in sender):
            if is_service_name(sender):
                print_status(f"Direct service name detected: {sender}", "DEBUG")
                return sender
            return sender
        
        # Try decoding as UTF-16BE
        try:
            bytes_sender = bytes.fromhex(sender)
            decoded = bytes_sender.decode('utf-16be').replace('\x00', '').strip()
            
            # If it's all digits, it's likely a phone number
            if decoded.replace('+', '').isdigit():
                print_status(f"Phone number detected: {decoded}", "DEBUG")
                return decoded
                
            # If it looks like a service name
            if is_service_name(decoded):
                print_status(f"Service name detected: {decoded}", "DEBUG")
                return decoded
                
            # If it contains both letters and numbers
            if any(c.isalpha() for c in decoded) and any(c.isdigit() for c in decoded):
                print_status(f"Mixed sender name detected: {decoded}", "DEBUG")
                return decoded
                
            print_status(f"UTF-16BE decoded sender: {decoded}", "DEBUG")
            return decoded
            
        except Exception as e:
            print_status(f"UTF-16BE decode failed: {e}", "DEBUG")
        
        # Try decoding as plain hex for short codes
        try:
            # Look for patterns like service numbers (e.g. "600", "700")
            plain_digits = ''.join(chr(int(sender[i:i+2], 16)) for i in range(0, len(sender), 2))
            if plain_digits.isdigit() and len(plain_digits) <= 4:
                print_status(f"Service number detected: {plain_digits}", "DEBUG")
                return plain_digits
        except Exception as e:
            print_status(f"Plain hex decode failed: {e}", "DEBUG")
        
        # If all decoding fails, return original
        return original
        
    except Exception as e:
        print_status(f"Error decoding sender: {e}", "ERROR")
        return sender

def decode_mixed_content(hex_content):
    """Decode content that may contain mixed languages and numbers"""
    try:
        # If not hex content, return as is
        if not all(c in '0123456789ABCDEFabcdef' for c in hex_content):
            return hex_content
            
        # Convert hex to bytes
        bytes_content = bytes.fromhex(hex_content)
        
        # First try full UTF-16BE decode
        try:
            decoded = bytes_content.decode('utf-16be')
            # Clean up any null bytes
            decoded = decoded.replace('\x00', '')
            if any(ord(c) > 128 for c in decoded):  # Has non-ASCII chars
                return decoded.strip()
        except Exception as e:
            print_status(f"Full UTF-16BE decode failed: {e}", "DEBUG")
        
        # If full decode fails, try segment by segment
        result = []
        for i in range(0, len(hex_content), 4):
            try:
                hex_char = hex_content[i:i+4]
                if not hex_char:
                    continue
                    
                byte_char = bytes.fromhex(hex_char)
                char_value = int.from_bytes(byte_char, 'big')
                
                # Arabic range
                if 0x0600 <= char_value <= 0x06FF:
                    decoded_char = byte_char.decode('utf-16be')
                # ASCII range
                elif char_value <= 0x7F:
                    decoded_char = chr(char_value)
                else:
                    decoded_char = byte_char.decode('utf-16be')
                
                result.append(decoded_char)
            except Exception as e:
                print_status(f"Segment decode failed: {e}", "DEBUG")
                continue
                
        decoded_text = ''.join(result)
        return decoded_text.strip()
        
    except Exception as e:
        print_status(f"Error in mixed content decode: {e}", "ERROR")
        return hex_content

def decode_message_content(content):
    """Decode message content with improved mixed language support"""
    try:
        # Strip any whitespace
        content = content.strip()
        
        # Try different decode methods
        decoded_results = []
        
        # 1. Try mixed content decoder
        mixed_decoded = decode_mixed_content(content)
        if mixed_decoded != content:  # If something was decoded
            decoded_results.append(('MIXED', mixed_decoded))
            print_status(f"Mixed decode: {mixed_decoded}", "DEBUG")
        
        # 2. Try straight UTF-16BE
        if all(c in '0123456789ABCDEFabcdef' for c in content):
            try:
                bytes_content = bytes.fromhex(content)
                utf16_decoded = bytes_content.decode('utf-16be')
                decoded_results.append(('UTF-16BE', utf16_decoded))
                print_status(f"UTF-16BE decode: {utf16_decoded}", "DEBUG")
            except Exception as e:
                print_status(f"UTF-16BE decode failed: {e}", "DEBUG")
        
        # Score results and pick best
        best_decoded = content
        best_score = -1
        
        for method, decoded in decoded_results:
            # Score the decoded text
            score = 0
            score += sum(2 for c in decoded if c.isprintable())  # Printable chars
            score += sum(3 for c in decoded if c.isalpha())      # Letters
            score += sum(2 for c in decoded if c.isdigit())      # Numbers
            score += sum(2 for c in decoded if c in ' ,.!?()-:') # Punctuation
            score -= sum(1 for c in decoded if not c.isprintable())  # Bad chars
            
            print_status(f"{method} decode score: {score}", "DEBUG")
            
            if score > best_score:
                best_score = score
                best_decoded = decoded
        
        return best_decoded.strip()
        
    except Exception as e:
        print_status(f"Error in content decode: {e}", "ERROR")
        return content

def process_message(ser, index, stat, sender, date, content):
    """معالجة وحفظ رسالة واحدة دائماً حتى لو كانت مكررة"""
    try:
        print_status(f"\n=== بدء معالجة الرسالة ===", "INFO")
        print_status(f"المرسل الأصلي: {sender}", "DEBUG")
        print_status(f"المحتوى الأصلي: {content}", "DEBUG")
        print_status(f"التاريخ: {date}", "DEBUG")
        
        # فك تشفير المرسل والمحتوى
        decoded_sender = decode_sender(sender)
        print_status(f"المرسل بعد فك التشفير: {decoded_sender}", "DEBUG")
        
        decoded_content = decode_mixed_content(content.strip())
        print_status(f"المحتوى بعد فك التشفير: {decoded_content}", "DEBUG")
        
        # تحقق سريع من صحة البيانات
        if not decoded_content or not decoded_sender:
            print_status("محتوى الرسالة أو المرسل فارغ", "ERROR")
            return False
        
        # حفظ في قاعدة البيانات دائماً
        saved = save_sms(stat, decoded_sender, date, decoded_content)
        if not saved:
            print_status("فشل في حفظ الرسالة في قاعدة البيانات", "ERROR")
            return False
        print_status("✅ تم حفظ الرسالة في قاعدة البيانات", "SUCCESS")
        
        # حذف من الشريحة بعد التأكد من الحفظ
        resp = send_at_command(ser, f'AT+CMGD={index}', wait=0.2)
        if 'OK' not in resp:
            print_status("فشل في حذف الرسالة من الشريحة", "ERROR")
            return False

        print_status("✅ تم معالجة الرسالة بنجاح", "SUCCESS")
        return True
    except Exception as e:
        print_status(f"خطأ في معالجة الرسالة: {e}", "ERROR")
        return False

def find_modem_port():
    """Find available GSM modem by testing COM ports"""
    print_status("\n=== Searching for GSM Modem ===", "INFO")
    ports = serial.tools.list_ports.comports()
    checked = set()
    
    if not ports:
        print_status("No COM ports found!", "ERROR")
        return None
    
    print_status(f"Found {len(ports)} COM ports to check", "INFO")
    # Sort ports by device name to ensure consistent checking order
    ports = sorted(ports, key=lambda x: x.device)
    
    for port in ports:
        if port.device in checked:
            continue
        checked.add(port.device)
        try:
            # Check if port is already in use
            try:
                ser = serial.Serial(port.device, 115200, timeout=1)
            except serial.SerialException as e:
                if "could not open port" in str(e).lower():
                    print_status(f"Port {port.device} is in use, skipping", "DEBUG")
                    continue
                raise e
                
            # Test modem presence
            ser.write(b'AT\r')
            time.sleep(0.5)
            response = ser.read(100).decode(errors='ignore')
            ser.close()
            
            if 'OK' in response:
                # Double check port is free after closing
                time.sleep(0.5)
                try:
                    ser = serial.Serial(port.device, 115200, timeout=1)
                    ser.close()
                    return port.device
                except:
                    print_status(f"Port {port.device} became busy, skipping", "DEBUG")
                    continue
                    
        except Exception as e:
            if "access is denied" not in str(e).lower():
                print_status(f"Error checking port {port.device}: {e}", "DEBUG")
            continue
    return None

def init_modem(ser):
    """Initialize modem settings with verification"""
    print_status("\n=== MODEM INITIALIZATION ===", "INFO")
    time.sleep(2)
    
    # Basic communication test
    print_status("1. Testing modem communication...", "INFO")
    send_at_command(ser, "AT")  # Echo on for debugging
    send_at_command(ser, "ATZ")  # Reset modem
    send_at_command(ser, "ATE1")  # Echo on for debugging
    if "OK" not in send_at_command(ser, "AT", wait=2):
        raise Exception("Modem not responding to AT command")
    print_status("✓ Modem responding", "SUCCESS")
    
    # Essential modem setup with verification
    commands = [
        ("AT+CMGF=1", "Setting text mode"),
        ('AT+CSCS="UCS2"', "Setting character set"),
        ("AT+CSDH=1", "Enabling detailed headers"),
        ("AT+CSMP=17,167,0,8", "Setting message parameters"),
        ('AT+CPMS="SM","SM","SM"', "Setting storage"),
        ("AT+CNMI=2,1,0,0,0", "Setting new message indications")
    ]
    
    for cmd, desc in commands:
        print_status(f"‣ {desc}...", "INFO")
        resp = send_at_command(ser, cmd, wait=2)
        if "OK" not in resp:
            print_status(f"Warning: Unexpected response to {cmd}: {resp}", "WARN")
        else:
            print_status(f"✓ {desc} successful", "SUCCESS")
    
    # Verify text mode is active
    resp = send_at_command(ser, "AT+CMGF?", wait=2)
    if "1" not in resp:
        raise Exception("Failed to set text mode")

def process_cmgl_response(resp, processed_indices, ser):
    """Process AT+CMGL response and handle any messages found"""
    if '+CMGL:' in resp:
        print_status("\n=== Processing Messages ===", "INFO")
        # Split response into individual messages
        lines = resp.strip().split('\r\n')
        i = 0
        while i < len(lines):
            try:
                line = lines[i]
                if line.startswith('+CMGL:'):
                    # Extract header info
                    print_status(f"Found message line: {line}", "DEBUG")
                    header_match = re.match(r'\+CMGL:\s*(\d+),"([^"]+)","([^"]+)",.*?"([^"]*)"', line)
                    if header_match and i + 1 < len(lines):
                        index = int(header_match.group(1))
                        status = header_match.group(2)
                        sender = header_match.group(3)
                        date_time = header_match.group(4)
                        content = lines[i + 1]
                        
                        print_status(f"Message details:", "INFO")
                        print_status(f"  Index: {index}", "INFO")
                        print_status(f"  Status: {status}", "INFO")
                        print_status(f"  Sender: {sender}", "INFO")
                        print_status(f"  Date: {date_time}", "INFO")
                        
                        # Process every message we find, regardless of status
                        print_status(f"\n📨 Found message at index {index}:", "INFO")
                        if process_message(ser, index, status, sender, date_time, content):
                            processed_indices.add(index)
                            print_status(f"Successfully processed message {index}", "SUCCESS")
                        else:
                            print_status(f"Failed to process message {index}", "ERROR")
                        
                        i += 2  # Skip the content line
                    else:
                        i += 1
                else:
                    i += 1
            except Exception as e:
                print_status(f"Error processing CMGL line: {e}", "ERROR")
                i += 1

def process_new_message_notification(ser, data, processed_indices):
    """Process new message notifications"""
    print_status("\n📨 New message notification received!", "INFO")
    matches = re.finditer(r'\+CMTI:\s*"([^"]+)"\s*,\s*(\d+)', data)
    
    for match in matches:
        storage, index = match.groups()
        index = int(index)
        
        # Wait briefly to ensure message is ready
        time.sleep(0.5)
        
        # Try to read the message
        resp = send_at_command(ser, f'AT+CMGR={index}', wait=2)
        if '+CMGR:' not in resp:
            continue
            
        # Split response into lines and clean them
        lines = [line.strip() for line in resp.split('\r\n') if line.strip()]
        
        # Find CMGR line and content
        cmgr_line = next((line for line in lines if '+CMGR:' in line), None)
        if not cmgr_line:
            continue
            
        cmgr_index = lines.index(cmgr_line)
        if len(lines) <= cmgr_index + 1:
            continue
            
        header = lines[cmgr_index]
        content = lines[cmgr_index + 1]
        
        # Parse header
        header_match = re.match(r'\+CMGR:\s*"([^"]+)","([^"]+)",[^"]*"([^"]*)"', header)
        if not header_match:
            continue
            
        status = header_match.group(1)
        sender = header_match.group(2)
        date_time = header_match.group(3)
        
        # Always process the message
        if process_message(ser, index, status, sender, date_time, content.strip()):
            processed_indices.add(index)
            print_status(f"Successfully processed notification message {index}", "SUCCESS")

def listen_for_sms(port):
    """Main SMS listening loop with improved reliability"""
    processed_indices = set()
    error_count = 0
    last_verification = 0
    verification_interval = 30  # Check modem every 30 seconds
    poll_interval = 1  # Poll more frequently
    
    while True:
        try:
            with serial.Serial(port, 115200, timeout=1) as ser:
                init_modem(ser)
                print_status("🟢 Modem initialized and ready", "INFO")
                last_poll = time.time()
                error_count = 0
                
                # Set preferred storage to both SIM and ME
                try:
                    resp = send_at_command(ser, 'AT+CPMS="SM","SM","SM"', wait=2)
                    if 'ERROR' in resp:
                        print_status("Falling back to ME storage...", "INFO")
                        resp = send_at_command(ser, 'AT+CPMS="ME","ME","ME"', wait=2)
                except Exception as e:
                    print_status(f"Storage setup error: {e}", "ERROR")
                
                while True:
                    try:
                        current_time = time.time()
                        
                        # Periodically verify modem connection
                        if current_time - last_verification >= verification_interval:
                            if not verify_modem_connection(ser):
                                print_status("Modem not responding, reconnecting...", "WARN")
                                raise Exception("Modem connection lost")
                            last_verification = current_time
                        
                        # Poll for messages more frequently
                        if current_time - last_poll >= poll_interval:
                            # Clear any pending input
                            if ser.in_waiting:
                                ser.read(ser.in_waiting)
                                
                            print_status("\n📥 Checking for messages...", "INFO")
                            
                            # Get current storage info
                            cpms_resp = send_at_command(ser, 'AT+CPMS?', wait=2)
                            print_status(f"Storage status: {cpms_resp}", "DEBUG")
                            
                            # Poll for all messages with longer wait time
                            resp = send_at_command(ser, 'AT+CMGL="ALL"', wait=3)
                            if '+CMGL:' in resp:
                                print_status("Found messages, processing...", "INFO")
                                before = len(processed_indices)
                                process_cmgl_response(resp, processed_indices, ser)
                                after = len(processed_indices)
                                print_status(f"Processed {after - before} new messages", "INFO")
                            
                            # Cleanup processed_indices periodically
                            if len(processed_indices) > 1000:
                                processed_indices = set(list(sorted(processed_indices))[-500:])
                                
                            last_poll = current_time
                        
                        # Check for immediate notifications
                        if ser.in_waiting:
                            data = ser.read(ser.in_waiting).decode(errors='ignore')
                            if '+CMTI:' in data:
                                print_status("New message notification received!", "INFO")
                                before = len(processed_indices)
                                process_new_message_notification(ser, data, processed_indices)
                                after = len(processed_indices)
                                print_status(f"Processed {after - before} new messages from notification", "INFO")
                        
                        time.sleep(0.1)  # Short sleep for responsiveness
                        
                    except Exception as e:
                        print_status(f"Error in polling loop: {e}", "ERROR")
                        if "Modem connection lost" in str(e):
                            raise
                        time.sleep(1)
                        
        except Exception as e:
            error_count += 1
            print_status(f"Connection error: {e}", "ERROR")
            wait_time = min(30, error_count * 5)
            print_status(f"Attempting to reconnect in {wait_time} seconds...", "WARN")
            time.sleep(wait_time)
            continue

def listen_for_sms_with_event(port, got_first_sms_event):
    """Main SMS listening loop with minimal logging and ready flag."""
    import os
    import time
    import serial
    
    processed_indices = set()
    error_count = 0
    poll_interval = 5
    first_sms_processed = False
    sms_ready_flag = DATA_DIR / 'sms_ready.flag'
    messages_found = 0
    
    # Remove any old ready flag
    if os.path.exists(sms_ready_flag):
        os.remove(sms_ready_flag)
    
    print_status("\n📱 Step 1: Starting SMS modem initialization...", "INFO")
    print_status(f"📱 Using port: {port}", "INFO")

    while True:
        try:
            with serial.Serial(port, 115200, timeout=1) as ser:
                # Initialize modem with debug output
                init_modem(ser)
                print_status("✓ Modem initialized successfully!", "SUCCESS")
                
                # Test immediate message check
                print_status("\n📱 Testing immediate message check...", "INFO")
                test_resp = send_at_command(ser, 'AT+CMGL="ALL"', wait=3)
                print_status(f"Initial message check response: {test_resp}", "DEBUG")
                
                # Write ready flag after initialization
                with open(sms_ready_flag, 'w') as f:
                    f.write('ready')
                
                print_status("\n===============================", "SUCCESS")
                print_status("✓ SMS SYSTEM READY AND ACTIVE", "SUCCESS")
                print_status("✓ Starting message polling...", "SUCCESS")
                print_status("===============================\n", "SUCCESS")
                
                last_poll = time.time()
                
                while True:
                    try:
                        current_time = time.time()
                        if current_time - last_poll >= poll_interval:
                            print_status("\n📱 Polling for new messages...", "INFO")
                            
                            # First verify modem is still responsive
                            if not verify_modem_connection(ser):
                                raise Exception("Modem not responding")
                            
                            # Check for messages
                            resp = send_at_command(ser, 'AT+CMGL="ALL"', wait=3)
                            print_status(f"Poll response: {resp}", "DEBUG")
                            
                            if '+CMGL:' in resp:
                                print_status("Found messages in response!", "SUCCESS")
                                before = len(processed_indices)
                                process_cmgl_response(resp, processed_indices, ser)
                                after = len(processed_indices)
                                if after > before:
                                    messages_found += (after - before)
                                    print_status(f"✓ Processed {after - before} new messages", "SUCCESS")
                                    print_status(f"Total messages found: {messages_found}", "INFO")
                                    if not first_sms_processed:
                                        got_first_sms_event.set()
                                        first_sms_processed = True
                            
                            last_poll = current_time
                        
                        # Check for immediate notifications
                        if ser.in_waiting:
                            data = ser.read(ser.in_waiting).decode(errors='ignore')
                            print_status(f"Received data: {data}", "DEBUG")
                            if '+CMTI:' in data:
                                print_status("\n📨 New message notification received!", "INFO")
                                process_new_message_notification(ser, data, processed_indices)
                        
                        time.sleep(0.1)
                        
                    except Exception as e:
                        print_status(f"Error in polling loop: {str(e)}", "ERROR")
                        if "Modem connection lost" in str(e):
                            raise
                        time.sleep(1)
        except Exception as e:
            error_count += 1
            print_status(f"Connection error: {str(e)}", "ERROR")
            time.sleep(min(30, error_count * 5))
            continue