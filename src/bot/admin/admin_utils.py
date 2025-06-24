from src.utils.config import ADMIN_CHAT_IDS

def is_admin(chat_id: int) -> bool:
    """
    التحقق إذا كان chat_id من المشرفين (يتم التحقق فقط من ADMIN_CHAT_IDS في ملف config).
    """
    return int(chat_id) in ADMIN_CHAT_IDS
