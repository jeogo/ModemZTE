import re
from src.utils.db import get_user_by_telegram_id, save_or_update_user
from src.utils.logger import print_status
from .verification_ui import send_main_menu

class RegistrationHandler:
    def __init__(self, bot):
        self.bot = bot
        self.pending_registrations = {}  # telegram_id: {'step': ..., 'data': {...}}
        print_status("تم تهيئة نظام التسجيل بنجاح", "SUCCESS")

    def start_registration(self, telegram_id):
        """بدء عملية تسجيل مستخدم جديد"""
        try:
            # التحقق من وجود تسجيل سابق
            existing_user = get_user_by_telegram_id(str(telegram_id))
            if existing_user and existing_user.get('username') and existing_user.get('phone_number'):
                print_status(f"ℹ️ المستخدم مسجل مسبقاً: {telegram_id}", "INFO")
                return "أنت مسجل بالفعل ويمكنك استخدام البوت."

            self.pending_registrations[telegram_id] = {'step': 'full_name', 'data': {}}
            print_status(f"بدء تسجيل مستخدم جديد: {telegram_id}", "INFO")
            return (
                "🤖 **مرحباً بك في نظام التحقق من العمليات!**\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "📝 **للتسجيل، نحتاج بعض المعلومات البسيطة**\n\n"
                "👤 **الخطوة الأولى: الاسم الكامل**\n"
                "أدخل اسمك الكامل (بالأحرف العربية أو اللاتينية)\n\n"
                "✅ **أمثلة صحيحة:**\n"                "📋 `أحمد محمد الطيب`\n"
                "📋 `Ahmed Mohamed`\n"
                "📋 `فاطمة الزهراء`\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 **نصيحة:** تأكد من كتابة اسمك بوضوح ودقة"
            )
        except Exception as e:
            print_status(f"خطأ في بدء التسجيل: {e}", "ERROR")
            return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى لاحقاً."

    def handle_registration(self, telegram_id, text):
        """معالجة خطوات التسجيل"""
        try:
            reg = self.pending_registrations.get(telegram_id)
            if not reg:
                return self.start_registration(telegram_id)

            step = reg['step']
            data = reg['data']
            
            print_status(f"معالجة خطوة التسجيل '{step}' للمستخدم {telegram_id}", "DEBUG")

            if step == 'full_name':
                if not text or len(text.strip()) < 3:
                    print_status(f"اسم قصير جداً: {text}", "WARNING")
                    return "الاسم قصير جداً. يجب أن يحتوي على 3 أحرف على الأقل:"
                
                if not self.is_valid_name(text):
                    print_status(f"اسم غير صالح: {text}", "WARNING")
                    return (
                        "الاسم غير صالح. يجب أن يحتوي على أحرف عربية أو إنجليزية فقط.\n"
                        "يرجى إدخال اسمك الكامل مرة أخرى:"
                    )
                
                data['username'] = text.strip()
                reg['step'] = 'phone_number'
                print_status(f"تم حفظ الاسم: {data['username']}", "SUCCESS")
                return (
                    "✅ **تم حفظ الاسم بنجاح!**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📱 **الخطوة الثانية: رقم الهاتف**\n\n"
                    "أدخل رقم هاتفك المحمول (10 أرقام)\n\n"
                    "📋 **الصيغة المطلوبة:**\n"
                    "• يجب أن يبدأ بـ 05 أو 06 أو 07\n"
                    "• يتكون من 10 أرقام بالضبط\n\n"
                    "✅ **أمثلة صحيحة:**\n"                    "📱 `0551234567`\n"
                    "📱 `0661234567`\n"
                    "📱 `0771234567`\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 **نصيحة:** تأكد من كتابة الرقم بدون مسافات أو رموز"
                )

            elif step == 'phone_number':
                if not self.is_valid_phone(text):
                    print_status(f"رقم هاتف غير صالح: {text}", "WARNING")
                    return (
                        "رقم الهاتف غير صالح.\n"
                        "يجب أن يبدأ بـ 05 أو 06 أو 07 ويتكون من 10 أرقام.\n"
                        "مثال: 05xxxxxxxx\n"
                        "يرجى المحاولة مرة أخرى:"
                    )

                data['phone_number'] = text.strip()
                # حفظ أو تحديث المستخدم
                if save_or_update_user(str(telegram_id), data['username'], data['phone_number']):
                    print_status(f"تم تسجيل المستخدم بنجاح: {telegram_id} - {data['username']} - {data['phone_number']}", "SUCCESS")
                    self.pending_registrations.pop(telegram_id)
                    msg = (
                        "🎉 **تم تسجيلك بنجاح!**\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 **الاسم:** {data['username']}\n"
                        f"📱 **رقم الهاتف:** {data['phone_number']}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "🤖 **مرحباً بك في النظام!**\n\n"
                        "🔰 **يمكنك الآن:**\n"
                        "✅ التحقق من عمليات تعبئة الرصيد\n"
                        "📊 عرض تقارير العمليات\n"
                        "🆘 التواصل مع الدعم الفني\n\n"
                        "*click /start*"
                    )
                    try:
                        self.bot.send_message(chat_id=telegram_id, text=msg)
                        # الملاحظة: ستظهر القائمة الرئيسية تلقائياً بعد اكتمال التسجيل
                    except Exception as e:
                        print_status(f"خطأ في إرسال رسالة التأكيد: {e}", "ERROR")
                    return msg
                else:
                    print_status(f"فشل في حفظ بيانات المستخدم: {telegram_id}", "ERROR")
                    return "عذراً، حدث خطأ في حفظ بياناتك. يرجى المحاولة مرة أخرى لاحقاً."

            return "عذراً، حدث خطأ غير متوقع. يرجى إرسال /start للبدء من جديد."

        except Exception as e:
            print_status(f"خطأ في معالجة التسجيل: {e}", "ERROR")
            return "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى لاحقاً."

    def is_valid_name(self, name):
        """التحقق من صحة الاسم (أحرف عربية أو إنجليزية، 3 أحرف على الأقل)"""
        name = name.strip()
        if not name or len(name) < 3:
            return False
        return bool(re.match(r'^[\u0600-\u06FFa-zA-Z\s]{3,}$', name))

    def is_valid_phone(self, phone):
        """التحقق من صحة رقم الهاتف (يبدأ بـ 05/06/07 ويتكون من 10 أرقام)"""
        phone = phone.strip()
        if not phone or len(phone) != 10:
            return False
        return bool(re.match(r'^(05|06|07)\d{8}$', phone))

    def is_registered(self, telegram_id):
        """التحقق مما إذا كان المستخدم مسجلاً بالفعل"""
        try:
            user = get_user_by_telegram_id(str(telegram_id))
            if user is None:
                is_reg = False
            else:
                # user is a dictionary now
                username = user.get('username')
                phone_number = user.get('phone_number')
                is_reg = username is not None and phone_number is not None
            
            print_status(f"التحقق من تسجيل المستخدم {telegram_id}: {'مسجل' if is_reg else 'غير مسجل'}", "DEBUG")
            return is_reg
        except Exception as e:
            print_status(f"خطأ في التحقق من تسجيل المستخدم: {e}", "ERROR")
            return False
