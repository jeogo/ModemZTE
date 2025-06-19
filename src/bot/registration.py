import re
from src.utils.db import get_user_by_telegram_id, save_or_update_user
from src.utils.logger import print_status
from .verification_ui import send_main_menu

class RegistrationHandler:
    def __init__(self, bot):
        self.bot = bot
        self.pending_registrations = {}  # telegram_id: {'step': ..., 'data': {...}}
        print_status("✅ تم تهيئة نظام التسجيل", "SUCCESS")

    def start_registration(self, telegram_id):
        """بدء عملية تسجيل مستخدم جديد"""
        try:
            # التحقق من وجود تسجيل سابق
            existing_user = get_user_by_telegram_id(str(telegram_id))
            if existing_user and existing_user[2] and existing_user[3]:
                print_status(f"ℹ️ المستخدم مسجل مسبقاً: {telegram_id}", "INFO")
                return "أنت مسجل بالفعل ويمكنك استخدام البوت."

            self.pending_registrations[telegram_id] = {'step': 'full_name', 'data': {}}
            print_status(f"📝 بدء تسجيل مستخدم جديد: {telegram_id}", "INFO")
            return (
                "مرحباً بك في نظام استقبال الرسائل! 👋\n"
                "للتسجيل، يرجى إدخال اسمك الكامل (بالأحرف العربية أو اللاتينية):"
            )
        except Exception as e:
            print_status(f"❌ خطأ في بدء التسجيل: {e}", "ERROR")
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
                    print_status(f"❌ اسم قصير جداً: {text}", "WARNING")
                    return "الاسم قصير جداً. يجب أن يحتوي على 3 أحرف على الأقل:"
                
                if not self.is_valid_name(text):
                    print_status(f"❌ اسم غير صالح: {text}", "WARNING")
                    return (
                        "❌ الاسم غير صالح. يجب أن يحتوي على أحرف عربية أو إنجليزية فقط.\n"
                        "يرجى إدخال اسمك الكامل مرة أخرى:"
                    )
                
                data['username'] = text.strip()
                reg['step'] = 'phone_number'
                print_status(f"✅ تم حفظ الاسم: {data['username']}", "SUCCESS")
                return (
                    "✅ تم حفظ الاسم بنجاح!\n"
                    "الآن، يرجى إدخال رقم هاتفك (مثال: 05xxxxxxxx):"
                )

            elif step == 'phone_number':
                if not self.is_valid_phone(text):
                    print_status(f"❌ رقم هاتف غير صالح: {text}", "WARNING")
                    return (
                        "❌ رقم الهاتف غير صالح.\n"
                        "يجب أن يبدأ بـ 05 أو 06 أو 07 ويتكون من 10 أرقام.\n"
                        "مثال: 05xxxxxxxx\n"
                        "يرجى المحاولة مرة أخرى:"
                    )

                data['phone_number'] = text.strip()
                # حفظ أو تحديث المستخدم
                if save_or_update_user(str(telegram_id), data['username'], data['phone_number']):
                    print_status(f"✅ تم تسجيل المستخدم بنجاح: {telegram_id} - {data['username']} - {data['phone_number']}", "SUCCESS")
                    self.pending_registrations.pop(telegram_id)
                    msg = (
                        "🎉 تم تسجيلك بنجاح!\n\n"
                        f"الاسم: {data['username']}\n"
                        f"رقم الهاتف: {data['phone_number']}\n\n"
                        "يمكنك الآن استقبال الرسائل. استمتع باستخدام البوت! 🌟"
                    )
                    try:
                        self.bot.send_message(chat_id=telegram_id, text=msg)
                        # إظهار القائمة الرئيسية بعد نجاح التسجيل
                        send_main_menu(self.bot, telegram_id)
                    except Exception as e:
                        print_status(f"خطأ في إرسال رسالة التأكيد: {e}", "ERROR")
                    return msg
                else:
                    print_status(f"❌ فشل في حفظ بيانات المستخدم: {telegram_id}", "ERROR")
                    return "❌ عذراً، حدث خطأ في حفظ بياناتك. يرجى المحاولة مرة أخرى لاحقاً."

            return "عذراً، حدث خطأ غير متوقع. يرجى إرسال /start للبدء من جديد."

        except Exception as e:
            print_status(f"❌ خطأ في معالجة التسجيل: {e}", "ERROR")
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
            is_reg = user is not None and user[2] and user[3]  # username and phone_number
            print_status(f"التحقق من تسجيل المستخدم {telegram_id}: {'✅ مسجل' if is_reg else '❌ غير مسجل'}", "DEBUG")
            return is_reg
        except Exception as e:
            print_status(f"❌ خطأ في التحقق من تسجيل المستخدم: {e}", "ERROR")
            return False
