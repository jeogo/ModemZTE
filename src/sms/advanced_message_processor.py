from typing import Optional, Dict, Any, List, Tuple
import chardet
import re
from datetime import datetime

class EncodingDetector:
    @staticmethod
    def detect_encoding(text: bytes) -> str:
        """
        Detects the encoding of the given text using chardet
        """
        try:
            result = chardet.detect(text)
            if result and result['confidence'] > 0.7:
                return result['encoding']
        except Exception:
            pass
        return 'utf-8'

class MultiLayerDecoder:
    @staticmethod
    def decode_message(text: bytes, encoding: Optional[str] = None) -> str:
        """
        Attempts to decode the message using multiple encoding layers
        Returns the decoded text or original text if decoding fails
        """
        if isinstance(text, str):
            return text
            
        encodings = [
            encoding,
            'utf-8',
            'utf-16',
            'windows-1256',
            'iso-8859-6',
            'cp1256',
            'ascii'
        ]
        
        for enc in encodings:
            if not enc:
                continue
            try:
                return text.decode(enc)
            except Exception:
                continue
                
        # If all attempts fail, try auto-detection
        try:
            detected_encoding = EncodingDetector.detect_encoding(text)
            return text.decode(detected_encoding)
        except Exception:
            # Last resort: try to decode as utf-8 with replace option
            return text.decode('utf-8', errors='replace')

class DateTimeExtractor:
    """Extract date and time from Arabic/English SMS messages"""
    
    PATTERNS = [
        # تاريخ وقت عربي (13/05/2023, 15:30)
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*[،,]?\s*(\d{1,2}):(\d{2})(?:\s*[AP]M)?',
        # وقت تاريخ عربي (15:30, 13/05/2023)
        r'(\d{1,2}):(\d{2})(?:\s*[AP]M)?\s*[،,]?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',
        # نمط إضافي للتواريخ العربية
        r'بتاريخ\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*(?:الساعة)?\s*(\d{1,2}):(\d{2})',
    ]
    
    @classmethod
    def extract(cls, text: str) -> Optional[datetime]:
        for pattern in cls.PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 5:
                        if len(groups[2]) == 2:  # تحويل سنة من YY إلى YYYY
                            year = 2000 + int(groups[2])
                        else:
                            year = int(groups[2])
                            
                        return datetime(
                            year=year,
                            month=int(groups[1]),
                            day=int(groups[0]),
                            hour=int(groups[3]),
                            minute=int(groups[4])
                        )
                except (ValueError, IndexError):
                    continue
        return None

class AmountExtractor:
    """Extract amount values from Arabic/English SMS messages"""
    
    PATTERNS = [
        # أنماط المبالغ المالية (100.00 ر.س، SR 100، 100 SAR)
        r'(?:ر\.?س\.?\s*)?(\d+(?:\.\d{2})?)\s*(?:ر\.?س\.?)?',
        r'(\d+(?:\.\d{2})?)\s*SAR',
        r'SR\s*(\d+(?:\.\d{2})?)',
        # أنماط إضافية بالعربية
        r'مبلغ\s*(\d+(?:\.\d{2})?)\s*(?:ر\.?س\.?)?',
        r'(?:تم إيداع|إيداع)\s*(\d+(?:\.\d{2})?)\s*(?:ر\.?س\.?)?',
    ]
    
    @classmethod
    def extract(cls, text: str) -> Optional[float]:
        for pattern in cls.PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

class MessageProcessor:
    def __init__(self):
        self.decoder = MultiLayerDecoder()
        self.processed_cache = {}
    
    def process_message(self, raw_message: bytes) -> Dict[str, Any]:
        """
        Process an SMS message with advanced features:
        - Multi-layer decoding
        - Text cleaning and normalization
        - Date/time extraction
        - Amount extraction
        - Caching of results
        """
        # Check cache first
        message_hash = hash(raw_message)
        if message_hash in self.processed_cache:
            return self.processed_cache[message_hash]
            
        try:
            # Detect encoding and decode
            encoding = EncodingDetector.detect_encoding(raw_message)
            decoded_text = self.decoder.decode_message(raw_message, encoding)
            
            # Clean and normalize text
            cleaned_text = self._clean_text(decoded_text)
            
            # Extract information
            datetime_obj = DateTimeExtractor.extract(cleaned_text)
            amount = AmountExtractor.extract(cleaned_text)
            
            result = {
                'original': raw_message,
                'decoded': decoded_text,
                'cleaned': cleaned_text,
                'encoding': encoding,
                'datetime': datetime_obj,
                'amount': amount,
                'processed_at': datetime.now(),
                'success': True
            }
            
            # Cache the result
            self.processed_cache[message_hash] = result
            return result
            
        except Exception as e:
            error_result = {
                'original': raw_message,
                'decoded': None,
                'cleaned': None,
                'encoding': None,
                'datetime': None,
                'amount': None,
                'processed_at': datetime.now(),
                'success': False,
                'error': str(e)
            }
            return error_result
    
    def _clean_text(self, text: str) -> str:
        """
        Enhanced text cleaning with Arabic support
        """
        if not text:
            return text
            
        # Remove control characters while preserving newlines
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Remove extra whitespace while preserving single spaces
        text = ' '.join(text.split())
        
        # Normalize Arabic characters
        text = self._normalize_arabic(text)
        
        return text.strip()
    
    def _normalize_arabic(self, text: str) -> str:
        """
        Normalize Arabic text (تطبيع النص العربي)
        """
        # Convert modified Alef to simple Alef
        text = re.sub('[إأآا]', 'ا', text)
        
        # Convert Teh Marbuta to Heh
        text = text.replace('ة', 'ه')
        
        # Remove Tashkeel (التشكيل)
        text = re.sub('[\u064B-\u065F\u0670]', '', text)
        
        return text

# Example usage:
"""
processor = MessageProcessor()
result = processor.process_message(sms_bytes)
if result['success']:
    print(f"Amount: {result['amount']}")
    print(f"DateTime: {result['datetime']}")
    print(f"Cleaned Text: {result['cleaned']}")
"""
