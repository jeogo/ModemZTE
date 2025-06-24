"""
نظام فك التشفير المتقدم والمضمون
يدعم جميع أنواع الترميز والتشفير مع آليات أمان متعددة
"""

import re
import chardet
import unicodedata
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
from dataclasses import dataclass
import logging
from functools import lru_cache
import hashlib
import time

# إعداد نظام السجل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EncodingType(Enum):
    """أنواع الترميز المدعومة"""
    PLAIN_TEXT = "plain_text"
    HEX_UCS2 = "hex_ucs2"
    HEX_UTF8 = "hex_utf8"
    BASE64 = "base64"
    GSM_7BIT = "gsm_7bit"
    UNKNOWN = "unknown"

class Language(Enum):
    """اللغات المدعومة"""
    ARABIC = "arabic"
    ENGLISH = "english"
    FRENCH = "french"
    MIXED = "mixed"
    UNKNOWN = "unknown"

class MessageType(Enum):
    """أنواع الرسائل"""
    RECHARGE_NOTIFICATION = "recharge_notification"
    BANK_NOTIFICATION = "bank_notification"
    SERVICE_MESSAGE = "service_message"
    PERSONAL_MESSAGE = "personal_message"
    UNKNOWN = "unknown"

@dataclass
class DecodingResult:
    """نتيجة فك التشفير"""
    success: bool
    original_text: str
    decoded_text: str
    encoding_type: EncodingType
    confidence: float
    language: Language
    message_type: MessageType
    extracted_data: Dict
    processing_time: float
    errors: List[str]

class AdvancedDecoder:
    """فاك تشفير متقدم ومضمون"""
    
    def __init__(self):
        self.cache = {}
        self.statistics = {
            'total_processed': 0,
            'successful_decodes': 0,
            'failed_decodes': 0,
            'cache_hits': 0
        }
        
        # أنماط الكشف المتقدمة
        self.patterns = self._initialize_patterns()
        
        # قاموس الكلمات للكشف عن اللغة
        self.language_keywords = self._initialize_language_keywords()
        
        # أنماط استخراج البيانات
        self.extraction_patterns = self._initialize_extraction_patterns()
    
    def _initialize_patterns(self) -> Dict:
        """تهيئة أنماط الكشف"""
        return {
            'hex_ucs2': re.compile(r'^[0-9A-Fa-f]+$'),
            'hex_utf8': re.compile(r'^[0-9A-Fa-f]+$'),
            'base64': re.compile(r'^[A-Za-z0-9+/]*={0,2}$'),
            'phone_number': re.compile(r'^(\+|00)?[1-9]\d{1,14}$'),
            'service_code': re.compile(r'^\d{2,5}$'),
            'arabic_text': re.compile(r'[\u0600-\u06FF]'),
            'english_text': re.compile(r'[a-zA-Z]'),
            'french_keywords': re.compile(r'\b(le|la|de|et|vous|avez|avec|succès)\b', re.IGNORECASE)
        }
    
    def _initialize_language_keywords(self) -> Dict:
        """تهيئة كلمات مفتاحية للغات"""
        return {
            Language.ARABIC: [
                'تم', 'رصيد', 'شحن', 'مبلغ', 'دينار', 'ريال', 'تاريخ', 'الساعة',
                'حساب', 'رقم', 'عملية', 'نجحت', 'فشلت', 'بنك', 'بطاقة'
            ],
            Language.FRENCH: [
                'vous', 'avez', 'rechargé', 'succès', 'compte', 'solde', 'montant',
                'avec', 'date', 'heure', 'opération', 'réussie', 'échoué', 'banque'
            ],
            Language.ENGLISH: [
                'account', 'balance', 'amount', 'recharge', 'successful', 'failed',
                'date', 'time', 'operation', 'bank', 'card', 'message', 'notification'
            ]
        }
    
    def _initialize_extraction_patterns(self) -> Dict:
        """تهيئة أنماط استخراج البيانات"""
        return {
            'amounts': [
                # Arabic patterns
                r'مبلغ\s*:?\s*(\d+(?:[.,]\d{2})?)\s*(?:دج|ريال|ر\.س|دينار)',
                r'(\d+(?:[.,]\d{2})?)\s*(?:دج|ريال|ر\.س|دينار)',
                
                # French patterns  
                r'rechargé\s+(\d+(?:[.,]\d{2})?)\s*(?:DZD|DA|EUR)',
                r'montant\s*:?\s*(\d+(?:[.,]\d{2})?)\s*(?:DZD|DA|EUR)',
                r'(\d+(?:[.,]\d{2})?)\s*(?:DZD|DA|EUR)',
                
                # English patterns
                r'amount\s*:?\s*(\d+(?:[.,]\d{2})?)\s*(?:SAR|USD|EUR)',
                r'(\d+(?:[.,]\d{2})?)\s*(?:SAR|USD|EUR)',
                
                # Generic patterns
                r'(\d+(?:[.,]\d{2})?)'
            ],
            'dates': [
                # DD/MM/YYYY format
                r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
                
                # French date patterns
                r'le\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
                
                # Arabic date patterns  
                r'(?:بتاريخ|في)\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
                
                # ISO format
                r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})'
            ],
            'times': [
                # 24-hour format
                r'(\d{1,2}):(\d{2})(?::(\d{2}))?',
                
                # 12-hour format with AM/PM
                r'(\d{1,2}):(\d{2})\s*([AP]M)',
                
                # Arabic time patterns
                r'الساعة\s+(\d{1,2}):(\d{2})',
                
                # French time patterns
                r'à\s+(\d{1,2})[h:](\d{2})'
            ]
        }
    
    @lru_cache(maxsize=1000)
    def decode_message(self, raw_message: Union[str, bytes]) -> DecodingResult:
        """فك تشفير رسالة مع تخزين مؤقت"""
        start_time = time.time()
        self.statistics['total_processed'] += 1
        
        # تحويل إلى نص إذا لزم الأمر
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8', errors='replace')
        
        # فحص التخزين المؤقت
        cache_key = hashlib.md5(raw_message.encode()).hexdigest()
        if cache_key in self.cache:
            self.statistics['cache_hits'] += 1
            return self.cache[cache_key]
        
        # بدء عملية فك التشفير
        result = self._decode_message_internal(raw_message, start_time)
        
        # حفظ في التخزين المؤقت
        self.cache[cache_key] = result
        
        # تنظيف التخزين المؤقت إذا كان كبيراً
        if len(self.cache) > 10000:
            # احتفظ بآخر 5000 نتيجة
            cache_items = list(self.cache.items())
            self.cache = dict(cache_items[-5000:])
        
        return result
    
    def _decode_message_internal(self, raw_message: str, start_time: float) -> DecodingResult:
        """المعالجة الداخلية لفك التشفير"""
        errors = []
        decoded_text = raw_message
        encoding_type = EncodingType.PLAIN_TEXT
        confidence = 0.0
        
        try:
            # 1. كشف نوع الترميز
            encoding_type, confidence = self._detect_encoding_type(raw_message)
            logger.info(f"Detected encoding: {encoding_type} with confidence: {confidence}")
            
            # 2. فك التشفير حسب النوع
            decoded_text = self._decode_by_type(raw_message, encoding_type)
            
            # 3. تنظيف النص
            decoded_text = self._clean_text(decoded_text)
            
            # 4. كشف اللغة
            language = self._detect_language(decoded_text)
            
            # 5. كشف نوع الرسالة
            message_type = self._detect_message_type(decoded_text)
            
            # 6. استخراج البيانات
            extracted_data = self._extract_data(decoded_text, language)
            
            processing_time = time.time() - start_time
            
            # تحديث الإحصائيات
            if decoded_text and decoded_text != raw_message:
                self.statistics['successful_decodes'] += 1
            else:
                self.statistics['failed_decodes'] += 1
            
            return DecodingResult(
                success=True,
                original_text=raw_message,
                decoded_text=decoded_text,
                encoding_type=encoding_type,
                confidence=confidence,
                language=language,
                message_type=message_type,
                extracted_data=extracted_data,
                processing_time=processing_time,
                errors=errors
            )
            
        except Exception as e:
            errors.append(f"Decoding error: {str(e)}")
            logger.error(f"Decoding failed: {e}")
            self.statistics['failed_decodes'] += 1
            
            return DecodingResult(
                success=False,
                original_text=raw_message,
                decoded_text=raw_message,
                encoding_type=EncodingType.UNKNOWN,
                confidence=0.0,
                language=Language.UNKNOWN,
                message_type=MessageType.UNKNOWN,
                extracted_data={},
                processing_time=time.time() - start_time,
                errors=errors
            )
    
    def _detect_encoding_type(self, text: str) -> Tuple[EncodingType, float]:
        """كشف نوع الترميز مع درجة الثقة"""
        confidence_scores = {}
        
        # فحص HEX UCS2/UTF16
        if self.patterns['hex_ucs2'].match(text) and len(text) % 4 == 0:
            # محاولة فك تشفير عينة
            try:
                sample = text[:min(20, len(text))]
                bytes_content = bytes.fromhex(sample)
                decoded_sample = bytes_content.decode('utf-16be')
                if any(ord(c) > 127 for c in decoded_sample):  # يحتوي على أحرف غير ASCII
                    confidence_scores[EncodingType.HEX_UCS2] = 0.9
                else:
                    confidence_scores[EncodingType.HEX_UCS2] = 0.6
            except:
                confidence_scores[EncodingType.HEX_UCS2] = 0.1
        
        # فحص HEX UTF8
        if self.patterns['hex_utf8'].match(text) and len(text) % 2 == 0:
            try:
                sample = text[:min(20, len(text))]
                bytes_content = bytes.fromhex(sample)
                decoded_sample = bytes_content.decode('utf-8')
                confidence_scores[EncodingType.HEX_UTF8] = 0.7
            except:
                confidence_scores[EncodingType.HEX_UTF8] = 0.1
        
        # فحص Base64
        if self.patterns['base64'].match(text) and len(text) % 4 == 0:
            try:
                import base64
                decoded_sample = base64.b64decode(text[:20]).decode('utf-8')
                confidence_scores[EncodingType.BASE64] = 0.8
            except:
                confidence_scores[EncodingType.BASE64] = 0.1
        
        # نص عادي
        if any(c.isalpha() for c in text):
            confidence_scores[EncodingType.PLAIN_TEXT] = 0.5
            # زيادة الثقة إذا كان يحتوي على أحرف عربية أو لاتينية
            if self.patterns['arabic_text'].search(text):
                confidence_scores[EncodingType.PLAIN_TEXT] = 0.8
            elif self.patterns['english_text'].search(text):
                confidence_scores[EncodingType.PLAIN_TEXT] = 0.7
        
        # اختيار النوع بأعلى ثقة
        if confidence_scores:
            best_type = max(confidence_scores, key=confidence_scores.get)
            return best_type, confidence_scores[best_type]
        
        return EncodingType.UNKNOWN, 0.0
    
    def _decode_by_type(self, text: str, encoding_type: EncodingType) -> str:
        """فك التشفير حسب النوع"""
        if encoding_type == EncodingType.PLAIN_TEXT:
            return text
        
        elif encoding_type == EncodingType.HEX_UCS2:
            return self._decode_hex_ucs2(text)
        
        elif encoding_type == EncodingType.HEX_UTF8:
            return self._decode_hex_utf8(text)
        
        elif encoding_type == EncodingType.BASE64:
            return self._decode_base64(text)
        
        else:
            return text
    
    def _decode_hex_ucs2(self, hex_text: str) -> str:
        """فك تشفير HEX UCS2/UTF-16BE مع آليات أمان متعددة"""
        try:
            # المحاولة الأساسية
            bytes_content = bytes.fromhex(hex_text)
            decoded = bytes_content.decode('utf-16be')
            return decoded.replace('\x00', '').strip()
            
        except Exception as e:
            logger.warning(f"Primary UCS2 decode failed: {e}")
            
            # محاولة بديلة: فك تشفير جزئي
            try:
                return self._decode_hex_segments(hex_text)
            except Exception as e2:
                logger.error(f"Segment decode failed: {e2}")
                return hex_text
    
    def _decode_hex_segments(self, hex_text: str) -> str:
        """فك تشفير hex بالقطع (fallback method)"""
        result = []
        
        # تقسيم النص إلى قطع 4 أحرف (2 بايت)
        for i in range(0, len(hex_text), 4):
            segment = hex_text[i:i+4]
            if len(segment) == 4:
                try:
                    bytes_segment = bytes.fromhex(segment)
                    char_value = int.from_bytes(bytes_segment, 'big')
                    
                    # فحص النطاقات المختلفة
                    if 0x0600 <= char_value <= 0x06FF:  # Arabic
                        result.append(bytes_segment.decode('utf-16be'))
                    elif char_value <= 0x7F:  # ASCII
                        result.append(chr(char_value))
                    elif 0x0020 <= char_value <= 0x007E:  # Printable ASCII
                        result.append(chr(char_value))
                    else:
                        # محاولة فك تشفير عام
                        try:
                            result.append(bytes_segment.decode('utf-16be'))
                        except:
                            result.append(f'[{segment}]')  # الاحتفاظ بالنص الأصلي
                            
                except Exception:
                    result.append(f'[{segment}]')
        
        return ''.join(result)
    
    def _decode_hex_utf8(self, hex_text: str) -> str:
        """فك تشفير HEX UTF-8"""
        try:
            bytes_content = bytes.fromhex(hex_text)
            return bytes_content.decode('utf-8')
        except Exception as e:
            logger.warning(f"UTF-8 hex decode failed: {e}")
            return hex_text
    
    def _decode_base64(self, base64_text: str) -> str:
        """فك تشفير Base64"""
        try:
            import base64
            decoded_bytes = base64.b64decode(base64_text)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            logger.warning(f"Base64 decode failed: {e}")
            return base64_text
    
    def _clean_text(self, text: str) -> str:
        """تنظيف النص من الأحرف غير المرغوبة"""
        if not text:
            return text
        
        # إزالة أحرف التحكم (عدا الأسطر الجديدة والتبويب)
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # تطبيع المسافات
        cleaned = ' '.join(cleaned.split())
        
        # تطبيع الأحرف العربية
        cleaned = self._normalize_arabic_text(cleaned)
        
        return cleaned.strip()
    
    def _normalize_arabic_text(self, text: str) -> str:
        """تطبيع النص العربي"""
        # توحيد أشكال الألف
        text = re.sub('[إأآا]', 'ا', text)
        
        # توحيد الياء
        text = re.sub('[يى]', 'ي', text)
        
        # إزالة التشكيل
        text = re.sub('[\u064B-\u065F\u0670]', '', text)
        
        # تطبيع Unicode
        text = unicodedata.normalize('NFKC', text)
        
        return text
    
    def _detect_language(self, text: str) -> Language:
        """كشف لغة النص"""
        if not text:
            return Language.UNKNOWN
        
        language_scores = {}
        
        # فحص الأحرف العربية
        arabic_chars = len(self.patterns['arabic_text'].findall(text))
        if arabic_chars > 0:
            language_scores[Language.ARABIC] = arabic_chars / len(text)
        
        # فحص الأحرف الإنجليزية
        english_chars = len(self.patterns['english_text'].findall(text))
        if english_chars > 0:
            language_scores[Language.ENGLISH] = english_chars / len(text)
        
        # فحص الكلمات الفرنسية
        french_matches = len(self.patterns['french_keywords'].findall(text))
        if french_matches > 0:
            language_scores[Language.FRENCH] = french_matches * 0.1
        
        # فحص الكلمات المفتاحية
        for language, keywords in self.language_keywords.items():
            keyword_count = sum(1 for keyword in keywords if keyword in text.lower())
            if keyword_count > 0:
                if language in language_scores:
                    language_scores[language] += keyword_count * 0.05
                else:
                    language_scores[language] = keyword_count * 0.05
        
        # اختيار اللغة بأعلى نقاط
        if language_scores:
            if len(language_scores) > 1:
                return Language.MIXED
            else:
                return max(language_scores, key=language_scores.get)
        
        return Language.UNKNOWN
    
    def _detect_message_type(self, text: str) -> MessageType:
        """كشف نوع الرسالة"""
        text_lower = text.lower()
        
        # رسائل التعبئة
        recharge_keywords = ['rechargé', 'recharge', 'شحن', 'رصيد', 'تعبئة', 'مبلغ']
        if any(keyword in text_lower for keyword in recharge_keywords):
            return MessageType.RECHARGE_NOTIFICATION
        
        # رسائل البنوك
        bank_keywords = ['bank', 'banque', 'بنك', 'حساب', 'عملية', 'transaction']
        if any(keyword in text_lower for keyword in bank_keywords):
            return MessageType.BANK_NOTIFICATION
        
        # رسائل الخدمة
        service_keywords = ['service', 'info', 'alert', 'notification', 'خدمة', 'تنبيه']
        if any(keyword in text_lower for keyword in service_keywords):
            return MessageType.SERVICE_MESSAGE
        
        return MessageType.PERSONAL_MESSAGE
    
    def _extract_data(self, text: str, language: Language) -> Dict:
        """استخراج البيانات من النص"""
        extracted = {
            'amounts': [],
            'dates': [],
            'times': [],
            'phone_numbers': [],
            'currencies': []
        }
        
        # استخراج المبالغ
        for pattern in self.extraction_patterns['amounts']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    amount = float(match.group(1).replace(',', '.'))
                    extracted['amounts'].append(amount)
                except (ValueError, IndexError):
                    continue
        
        # استخراج التواريخ
        for pattern in self.extraction_patterns['dates']:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    if len(match.groups()) >= 3:
                        day, month, year = match.groups()[:3]
                        extracted['dates'].append(f"{day}/{month}/{year}")
                except IndexError:
                    continue
        
        # استخراج الأوقات
        for pattern in self.extraction_patterns['times']:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    if len(match.groups()) >= 2:
                        hour, minute = match.groups()[:2]
                        extracted['times'].append(f"{hour}:{minute}")
                except IndexError:
                    continue
        
        # استخراج أرقام الهواتف
        phone_matches = re.finditer(r'(\+?[1-9]\d{1,14})', text)
        for match in phone_matches:
            phone = match.group(1)
            if self.patterns['phone_number'].match(phone):
                extracted['phone_numbers'].append(phone)
        
        # استخراج العملات
        currency_matches = re.finditer(r'\b(DZD|SAR|USD|EUR|ريال|دينار|ر\.س|دج)\b', text, re.IGNORECASE)
        for match in currency_matches:
            extracted['currencies'].append(match.group(1))
        
        return extracted
    
    def get_statistics(self) -> Dict:
        """الحصول على إحصائيات الأداء"""
        total = self.statistics['total_processed']
        return {
            'total_processed': total,
            'successful_decodes': self.statistics['successful_decodes'],
            'failed_decodes': self.statistics['failed_decodes'],
            'success_rate': (self.statistics['successful_decodes'] / max(total, 1)) * 100,
            'cache_hits': self.statistics['cache_hits'],
            'cache_hit_rate': (self.statistics['cache_hits'] / max(total, 1)) * 100,
            'cache_size': len(self.cache)
        }
    
    def clear_cache(self):
        """مسح التخزين المؤقت"""
        self.cache.clear()
        logger.info("Cache cleared")

# وظائف مساعدة للاستخدام السريع
def decode_message_quick(message: str) -> DecodingResult:
    """فك تشفير سريع لرسالة واحدة"""
    decoder = AdvancedDecoder()
    return decoder.decode_message(message)

def batch_decode_messages(messages: List[str]) -> List[DecodingResult]:
    """فك تشفير مجموعة من الرسائل"""
    decoder = AdvancedDecoder()
    results = []
    
    for message in messages:
        result = decoder.decode_message(message)
        results.append(result)
    
    return results

def test_decoder_system():
    """اختبار شامل لنظام فك التشفير"""
    print("🧪 اختبار نظام فك التشفير المتقدم")
    
    test_messages = [
        # نص عربي عادي
        "تم شحن رصيدكم بمبلغ 500 دج بتاريخ 15/06/2023 الساعة 14:30",
        
        # نص فرنسي
        "Vous avez rechargé 1400.00 DZD avec succès le 10/06/2025 14:30:00",
        
        # رقم هاتف
        "+213776863561",
        
        # نص مشفر hex (مثال)
        "062A0645002006450648064A062806480020006200350030003000200062062A06270646064A",
        
        # نص إنجليزي
        "Your account balance is 250.00 SAR as of 20/06/2023 15:45",
    ]
    
    decoder = AdvancedDecoder()
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n--- اختبار {i} ---")
        print(f"النص الأصلي: {message}")
        
        result = decoder.decode_message(message)
        
        print(f"النجاح: {result.success}")
        print(f"النص المفكوك: {result.decoded_text}")
        print(f"نوع الترميز: {result.encoding_type.value}")
        print(f"اللغة: {result.language.value}")
        print(f"نوع الرسالة: {result.message_type.value}")
        print(f"الثقة: {result.confidence:.2f}")
        print(f"وقت المعالجة: {result.processing_time:.4f} ثانية")
        
        if result.extracted_data:
            print("البيانات المستخرجة:")
            for key, value in result.extracted_data.items():
                if value:
                    print(f"  {key}: {value}")
        
        if result.errors:
            print(f"الأخطاء: {result.errors}")
    
    # عرض الإحصائيات
    print(f"\n📊 إحصائيات الأداء:")
    stats = decoder.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    test_decoder_system()
