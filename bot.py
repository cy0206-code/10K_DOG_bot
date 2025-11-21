import os
import json
from flask import Flask, request
import requests
import datetime
import pytz

app = Flask(__name__)

# 從環境變數讀取 Token
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN 環境變數未設定")

# 超級管理員 ID
SUPER_ADMIN = 8126033106

# 資料儲存檔案
DATA_FILE = "/tmp/admin_data.json"

# ========== 資料管理函數 ==========
def load_data():
    """載入資料檔案"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                print(f"成功載入資料：{len(loaded_data.get('admins', {}))} 管理員, {len(loaded_data.get('allowed_threads', {}))} 話題")
                return loaded_data
    except Exception as e:
        print(f"載入資料錯誤：{e}")
    
    # 預設資料結構
    default_data = {
        "admins": {
            str(SUPER_ADMIN): {
                "added_by": "system",
                "added_time": datetime.datetime.now().isoformat(),
                "is_super": True
            }
        },
        "allowed_threads": {},
        "admin_logs": []
    }
    save_data(default_data)
    print("創建新的預設資料檔案")
    return default_data

def save_data(data):
    """保存資料到檔案"""
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"資料已保存：{len(data.get('admins', {}))} 管理員, {len(data.get('allowed_threads', {}))} 話題")
    except Exception as e:
        print(f"儲存資料錯誤：{e}")

# 載入初始資料
try:
    data = load_data()
except Exception as e:
    print(f"初始化資料錯誤：{e}")
    data = {"admins": {}, "allowed_threads": {}, "admin_logs": []}

# 台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

# ========== 資料存取函數 ==========
def get_admins():
    """獲取管理員列表"""
    return data.get("admins", {})

def get_allowed_threads():
    """獲取允許的話題列表"""
    return data.get("allowed_threads", {})

def get_admin_logs():
    """獲取操作紀錄"""
    return data.get("admin_logs", [])

def update_data(key, value):
    """更新資料並保存"""
    data[key] = value
    save_data(data)

# ========== 權限檢查函數 ==========
def is_admin(user_id):
    """檢查是否為管理員"""
    return str(user_id) in get_admins()

def is_super_admin(user_id):
    """檢查是否為超級管理員"""
    admin_info = get_admins().get(str(user_id), {})
    return admin_info.get('is_super', False)

# ========== 管理員管理函數 ==========
def add_admin(admin_id, added_by, is_super=False):
    """新增管理員"""
    try:
        admin_id_str = str(admin_id)
        admins = get_admins()
        if admin_id_str not in admins:
            admins[admin_id_str] = {
                "added_by": added_by,
                "added_time": datetime.datetime.now(TAIWAN_TZ).isoformat(),
                "is_super": is_super
            }
            update_data("admins", admins)
            return True
        return False
    except Exception as e:
        print(f"新增管理員錯誤：{e}")
        return False

def remove_admin(admin_id):
    """移除管理員"""
    try:
        admin_id_str = str(admin_id)
        admins = get_admins()
        if admin_id_str in admins and not admins[admin_id_str].get('is_super', False):
            del admins[admin_id_str]
            update_data("admins", admins)
            return True
        return False
    except Exception as e:
        print(f"移除管理員錯誤：{e}")
        return False

# ========== 話題管理函數 ==========
def add_thread(chat_id, thread_id, user_id):
    """新增允許的話題"""
    try:
        thread_key = f"{chat_id}_{thread_id}"
        allowed_threads = get_allowed_threads()
        allowed_threads[thread_key] = True
        update_data("allowed_threads", allowed_threads)
        return True
    except Exception as e:
        print(f"新增話題錯誤：{e}")
        return False

def remove_thread(chat_id, thread_id):
    """移除允許的話題"""
    try:
        thread_key = f"{chat_id}_{thread_id}"
        allowed_threads = get_allowed_threads()
        if thread_key in allowed_threads:
            del allowed_threads[thread_key]
            update_data("allowed_threads", allowed_threads)
            return True
        return False
    except Exception as e:
        print(f"移除話題錯誤：{e}")
        return False

# ========== 操作紀錄函數 ==========
def log_admin_action(admin_id, action, target_id=None, details=None):
    """記錄管理員操作"""
    try:
        taiwan_time = datetime.datetime.now(TAIWAN_TZ)
        log_entry = {
            'timestamp': taiwan_time.isoformat(),
            'admin_id': admin_id,
            'action': action,
            'target_id': target_id,
            'details': details
        }
        admin_logs = get_admin_logs()
        admin_logs.append(log_entry)
        if len(admin_logs) > 500:
            admin_logs.pop(0)
        update_data("admin_logs", admin_logs)
    except Exception as e:
        print(f"記錄操作錯誤：{e}")

# ========== 權限檢查函數 ==========
def should_process_message(update, user_id, message_text):
    """檢查訊息是否應該被處理"""
    try:
        chat_id = update['message']['chat']['id']
        
        # 私聊永遠允許
        if not str(chat_id).startswith('-100'):
            return True
        
        # 群組中檢查話題權限
        thread_id = update['message'].get('message_thread_id', 0)
        thread_key = f"{chat_id}_{thread_id}"
        
        # 管理員的管理指令永遠允許
        if (is_admin(user_id) and 
            message_text in ['/admin add_thread', '/admin remove_thread']):
            return True
        
        # 一般指令需要話題已被允許
        return thread_key in get_allowed_threads()
    except Exception as e:
        print(f"權限檢查錯誤：{e}")
        return False

# ========== 命令定義 ==========
COMMANDS = {
    "ca": "C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "https://10kcoin.com/",
    "announcements": "https://t.me/tenkdogcrypto",
    "rules": "https://t.me/tenkdogcrypto/71",
    "jup_lock": "https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "https://t.me/tenkdogcrypto/72",
    "invitation_code": "https://t.me/tenthousandcommunity/10405",
    "x": "https://x.com/10000timesto1",
    "dc": "https://discord.com/invite/10kdog",
    "threads": "https://www.threads.com/@_10kdog_?igshid=NTc4MTIwNjQ2YQ=="    
}

# ========== 按鈕選單函數 ==========
def create_reply_markup():
    """創建一般用戶按鈕選單"""
    keyboard = [
        [{"text": "📜 合約地址", "callback_data": "ca"}],
        [{"text": "🌐 官網網站", "callback_data": "web"}, {"text": "📣 社群公告", "callback_data": "announcements"}, {"text": "📑 社群規範", "callback_data": "rules"}],
        [{"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"}, {"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"}, {"text": "🔗 註冊連結", "callback_data": "invitation_code"}],
        [{"text": "𝕏 twitter推特", "callback_data": "x"}, {"text": "💬 Discord", "callback_data": "dc"}, {"text": "@ Threads", "callback_data": "threads"}],
        [{"text": "📋 所有可用指令", "callback_data": "help"}]
    ]
    return {"inline_keyboard": keyboard}

def create_private_admin_markup(user_id):
    """創建管理員私聊按鈕選單"""
    keyboard = [
        [{"text": "👥 管理員列表", "callback_data": "private_list_admins"}, {"text": "🔍 查詢TG UID", "callback_data": "private_query_uid"}],
        [{"text": "➕ 新增管理員", "callback_data": "private_add_admin_input"}, {"text": "❌ 移除管理員", "callback_data": "private_remove_admin_input"}],
        [{"text": "📋 話題列表", "callback_data": "private_list_threads"}, {"text": "🛠️ 群組指令說明", "callback_data": "private_group_commands"}],
    ]
    
    if is_super_admin(user_id):
        keyboard.append([{"text": "📊 操作紀錄", "callback_data": "private_view_logs"}])
    
    keyboard.append([{"text": "🔙 主選單", "callback_data": "private_back_to_main"}])
    
    return {"inline_keyboard": keyboard}

# ========== 群組管理指令處理 ==========
def handle_group_admin_command(message_text, chat_id, user_id, update):
    """處理群組中的管理指令"""
    try:
        thread_id = update['message'].get('message_thread_id', 0)
        
        if message_text == '/admin add_thread':
            if add_thread(chat_id, thread_id, user_id):
                send_message(chat_id, "✅ 已允許當前話題", None, thread_id)
                log_admin_action(user_id, "add_thread", details=f"{chat_id}_{thread_id}")
            else:
                send_message(chat_id, "❌ 允許話題失敗", None, thread_id)
                
        elif message_text == '/admin remove_thread':
            if remove_thread(chat_id, thread_id):
                send_message(chat_id, "❌ 已移除當前話題權限", None, thread_id)
                log_admin_action(user_id, "remove_thread", details=f"{chat_id}_{thread_id}")
            else:
                send_message(chat_id, "❌ 此話題未被允許", None, thread_id)
        
        elif message_text == '/admin':
            pass  # 靜默處理
            
    except Exception as e:
        print(f"群組管理指令錯誤：{e}")

# ========== 列表顯示函數 ==========
def get_admin_list_with_names():
    """獲取管理員列表（含名稱）"""
    try:
        admins = get_admins()
        if not admins:
            return "👥 目前沒有管理員"
        
        admin_list = "👥 管理員列表：\n\n"
        for admin_id, admin_info in admins.items():
            try:
                user_info = get_user_info(int(admin_id))
                first_name = user_info.get('first_name', '')
                last_name = user_info.get('last_name', '')
                username = user_info.get('username', '')
                
                full_name = f"{first_name} {last_name}".strip() or "未知用戶"
                username_display = f"(@{username})" if username else "(無用戶名)"
                role = "👑 超級管理員" if admin_info.get('is_super', False) else "👤 管理員"
                
                # 格式化時間
                added_time = admin_info.get('added_time', '未知時間')
                try:
                    added_dt = datetime.datetime.fromisoformat(added_time).astimezone(TAIWAN_TZ)
                    time_str = added_dt.strftime("%Y/%m/%d %H:%M")
                except:
                    time_str = added_time
                
                admin_list += f"{role} - {full_name} {username_display}\n"
                admin_list += f"🔢 ID: `{admin_id}`\n"
                admin_list += f"⏰ 新增時間: {time_str}\n\n"
            except:
                admin_list += f"👤 未知用戶\n🔢 ID: `{admin_id}`\n\n"
        
        return admin_list
    except Exception as e:
        print(f"獲取管理員列表錯誤：{e}")
        return "❌ 獲取管理員列表失敗"

def get_thread_list_with_names():
    """獲取話題列表（含名稱）"""
    try:
        allowed_threads = get_allowed_threads()
        if not allowed_threads:
            return "📋 目前沒有允許的話題"
        
        thread_list = "📋 允許的話題列表：\n\n"
        for thread_key in allowed_threads.keys():
            try:
                chat_id, thread_id = thread_key.split('_')
                thread_id = int(thread_id) if thread_id != '0' else 0
                
                chat_info = get_chat_info(chat_id)
                chat_title = chat_info.get('title', '未知群組') if chat_info else '未知群組'
                
                if thread_id == 0:
                    thread_list += f"💬 主聊天室\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
                else:
                    thread_name = get_thread_name(chat_id, thread_id) or "未知話題"
                    thread_list += f"💬 話題: {thread_name}\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
            except Exception as e:
                print(f"處理話題 {thread_key} 錯誤: {e}")
                thread_list += f"💬 話題\n🔢 識別碼: {thread_key}\n\n"
        
        return thread_list
    except Exception as e:
        print(f"獲取話題列表錯誤：{e}")
        return "❌ 獲取話題列表失敗"

def get_help_text():
    """獲取統一的幫助文字"""
    return """📋 指令清單：

/start - ✅ 開啟選單
/help - 📋 顯示指令清單
/ca - 📜 合約地址
/web - 🌐 官方網站
/announcements - 📣 社群公告
/rules - 📑 社群規範
/jup_lock - 🔐 鎖倉資訊
/pumpswap - ⛏️ 流動性礦池教學
/invitation_code - 🔗 註冊連結
/x - 𝕏 Twitter推特
/dc - 💬 Discord社群
/threads - @ Threads"""

# ========== Telegram API 輔助函數 ==========
def get_user_info(user_id):
    """獲取用戶資訊"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChat"
        payload = {"chat_id": user_id}
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get('result', {})
    except Exception as e:
        print(f"獲取用戶資訊錯誤：{e}")
    return None

def get_chat_info(chat_id):
    """獲取聊天資訊"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChat"
        payload = {"chat_id": chat_id}
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get('result', {})
    except Exception as e:
        print(f"獲取聊天資訊錯誤：{e}")
    return None

def get_thread_name(chat_id, thread_id):
    """獲取話題名稱"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getForumTopic"
        payload = {"chat_id": chat_id, "message_thread_id": thread_id}
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get('result', {}).get('name', '未知話題')
    except Exception as e:
        print(f"獲取話題名稱錯誤：{e}")
    return '未知話題'

def send_message(chat_id, text, reply_markup=None, thread_id=None):
    """發送訊息"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': None  # 避免 Markdown 解析問題
        }
        if thread_id:
            payload['message_thread_id'] = thread_id
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        
        response = requests.post(url, json=payload, timeout=5)
        print(f"發送訊息到 {chat_id} (thread: {thread_id}) - 狀態: {response.status_code}")
    except Exception as e:
        print(f"發送訊息錯誤：{e}")

def answer_callback_query(callback_query_id):
    """回答回調查詢"""
    try:
        url = f'https://api.telegram.org/bot{TOKEN}/answerCallbackQuery'
        payload = {'callback_query_id': callback_query_id}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"回答回調查詢錯誤：{e}")

# ========== 私聊管理員命令處理 ==========
def handle_private_admin_command(message_text, chat_id, user_id):
    """處理私聊中的管理員命令"""
    try:
        if message_text.startswith('/admin add_admin '):
            parts = message_text.split(' ')
            if len(parts) > 2:
                try:
                    new_admin_id = int(parts[2])
                    if add_admin(new_admin_id, user_id):
                        send_message(chat_id, f"✅ 已新增管理員: {new_admin_id}")
                        log_admin_action(user_id, "add_admin", target_id=new_admin_id)
                    else:
                        send_message(chat_id, f"❌ 用戶 {new_admin_id} 已經是管理員")
                except ValueError:
                    send_message(chat_id, "❌ 請提供有效的用戶ID")
                    
        elif message_text.startswith('/admin remove_admin '):
            parts = message_text.split(' ')
            if len(parts) > 2:
                try:
                    remove_admin_id = int(parts[2])
                    if remove_admin(remove_admin_id):
                        send_message(chat_id, f"❌ 已移除管理員: {remove_admin_id}")
                        log_admin_action(user_id, "remove_admin", target_id=remove_admin_id)
                    else:
                        send_message(chat_id, "❌ 該用戶不是管理員或是超級管理員")
                except ValueError:
                    send_message(chat_id, "❌ 請提供有效的用戶ID")
                    
        elif message_text == '/admin list_admins':
            admin_list = get_admin_list_with_names()
            send_message(chat_id, admin_list)
            
        elif message_text == '/admin list_threads':
            thread_list = get_thread_list_with_names()
            send_message(chat_id, thread_list)
            
        elif message_text == '/admin commands':
            commands_help = "🛠️ 群組管理指令：\n/admin add_thread - 允許話題\n/admin remove_thread - 移除話題"
            send_message(chat_id, commands_help)
            
        elif message_text == '/admin myid':
            send_message(chat_id, f"🔢 您的 User ID 是: `{user_id}`")
            
    except Exception as e:
        print(f"私聊管理員命令錯誤：{e}")
        send_message(chat_id, "❌ 命令處理失敗，請稍後再試")

def handle_super_admin_commands(message_text, chat_id, user_id):
    """處理超級管理員命令"""
    try:
        if message_text.startswith('/admin logs'):
            parts = message_text.split(' ')
            count = int(parts[2]) if len(parts) > 2 else 10
            
            admin_logs = get_admin_logs()
            logs = admin_logs[-count:] if count <= len(admin_logs) else admin_logs
            if not logs:
                send_message(chat_id, "📊 目前沒有操作紀錄")
            else:
                log_text = "📊 最近管理操作紀錄：\n\n"
                for log in reversed(logs):
                    try:
                        taiwan_time = datetime.datetime.fromisoformat(log['timestamp']).astimezone(TAIWAN_TZ)
                        time_str = taiwan_time.strftime("%m/%d %H:%M")
                        
                        log_text += f"⏰ 時間: {time_str}\n"
                        log_text += f"👤 管理員: {log['admin_id']}\n"
                        log_text += f"📝 操作: {log['action']}\n"
                        
                        if log['target_id']:
                            log_text += f"🎯 目標: {log['target_id']}\n"
                        if log['details']:
                            log_text += f"📋 詳情: {log['details']}\n"
                        
                        log_text += "─" * 20 + "\n\n"
                    except:
                        continue
                send_message(chat_id, log_text)
    except Exception as e:
        print(f"超級管理員命令錯誤：{e}")
        send_message(chat_id, "❌ 操作紀錄查詢失敗")

# ========== UID 查詢處理 ==========
def handle_uid_query(update, chat_id):
    """處理 UID 查詢"""
    try:
        forwarded_user = update['message']['forward_from']
        forwarded_user_id = forwarded_user['id']
        forwarded_first_name = forwarded_user.get('first_name', '')
        forwarded_last_name = forwarded_user.get('last_name', '')
        forwarded_username = forwarded_user.get('username', '')
        
        full_name = f"{forwarded_first_name} {forwarded_last_name}".strip() or "未知"
        
        user_info = f"""🔍 用戶 UID 查詢結果

👤 姓名：{full_name}
🔢 UID：`{forwarded_user_id}`
📧 用戶名：@{forwarded_username if forwarded_username else '未設定'}"""

        copy_keyboard = {
            "inline_keyboard": [
                [{"text": "📋 複製UID", "callback_data": f"copy_uid_{forwarded_user_id}"}],
                [{"text": "➕ 新增此用戶為管理員", "callback_data": f"add_this_user_{forwarded_user_id}"}],
                [{"text": "🔙 返回管理員面板", "callback_data": "private_back_to_admin"}]
            ]
        }
        
        send_message(chat_id, user_info, copy_keyboard)
        
    except Exception as e:
        print(f"UID查詢錯誤：{e}")
        send_message(chat_id, "❌ 查詢失敗，請確保轉發的是用戶訊息且隱私設定允許")

def handle_uid_query_buttons(callback_data, chat_id, user_id):
    """處理 UID 查詢按鈕"""
    try:
        if callback_data.startswith('copy_uid_'):
            uid_to_copy = callback_data.replace('copy_uid_', '')
            send_message(chat_id, uid_to_copy)  # 只顯示純數字
            
        elif callback_data.startswith('add_this_user_'):
            if is_super_admin(user_id):
                uid_to_add = int(callback_data.replace('add_this_user_', ''))
                if add_admin(uid_to_add, user_id):
                    send_message(chat_id, f"✅ 已新增用戶 {uid_to_add} 為管理員")
                    log_admin_action(user_id, "add_admin", target_id=uid_to_add)
                else:
                    send_message(chat_id, f"❌ 用戶 {uid_to_add} 已經是管理員")
            else:
                send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
                
    except Exception as e:
        print(f"UID按鈕處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# ========== 私聊管理員按鈕處理 ==========
def handle_private_admin_button(callback_data, chat_id, user_id):
    """處理私聊中的管理員按鈕"""
    try:
        if callback_data == 'private_list_admins':
            admin_list = get_admin_list_with_names()
            send_message(chat_id, admin_list)
            
        elif callback_data == 'private_query_uid':
            help_text = "🔍 查詢用戶 UID：請轉發用戶訊息給我"
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_add_admin_input':
            help_text = "➕ 新增管理員：請直接貼上 UID 數字"
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_remove_admin_input':
            help_text = "❌ 移除管理員：請直接貼上 UID 數字"
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_list_threads':
            thread_list = get_thread_list_with_names()
            send_message(chat_id, thread_list)
            
        elif callback_data == 'private_group_commands':
            commands_help = "🛠️ 群組指令：\n/admin add_thread - 允許話題\n/admin remove_thread - 移除話題"
            send_message(chat_id, commands_help)
            
        elif callback_data == 'private_view_logs' and is_super_admin(user_id):
            handle_super_admin_commands('/admin logs 10', chat_id, user_id)
            
        elif callback_data == 'private_back_to_main':
            send_message(chat_id, "🐾 歡迎使用10K DOG 官方BOT", create_reply_markup())
            
        elif callback_data == 'private_back_to_admin':
            menu_text = "👑 管理員控制面板"
            markup = create_private_admin_markup(user_id)
            send_message(chat_id, menu_text, markup)
            
    except Exception as e:
        print(f"管理員按鈕處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# ========== 管理員 UID 輸入處理 ==========
def handle_admin_uid_input(message_text, chat_id, user_id):
    """處理管理員輸入的 UID"""
    try:
        uid_text = message_text.strip()
        
        if not uid_text.isdigit():
            send_message(chat_id, "❌ 請輸入有效的數字 UID")
            return
        
        target_uid = int(uid_text)
        
        if add_admin(target_uid, user_id):
            send_message(chat_id, f"✅ 已新增管理員: {target_uid}")
            log_admin_action(user_id, "add_admin", target_id=target_uid)
        else:
            send_message(chat_id, f"❌ 用戶 {target_uid} 已經是管理員")
                
    except Exception as e:
        print(f"管理員UID輸入處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# ========== 一般用戶命令處理 ==========
def handle_user_commands(message_text, chat_id, user_id, is_private, update):
    """處理一般用戶命令"""
    try:
        if message_text == '/start':
            welcome_text = "🐾 歡迎使用10K DOG 官方BOT\n請選擇下方按鈕或輸入指令獲取資訊！"
            send_message(chat_id, welcome_text, create_reply_markup())
            
        elif message_text == '/help':
            help_text = get_help_text()
            send_message(chat_id, help_text)
            
        elif message_text.startswith('/'):
            command = message_text[1:].lower().split(' ')[0]
            if command in COMMANDS:
                # 在群組中需要正確的 thread_id
                thread_id = None
                if not is_private and 'message' in update:
                    thread_id = update['message'].get('message_thread_id')
                send_message(chat_id, COMMANDS[command], None, thread_id)
                
    except Exception as e:
        print(f"一般用戶命令錯誤：{e}")

# ========== 主 Webhook 處理 ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    """主 Webhook 處理函數"""
    try:
        update = request.get_json()
        
        # 處理回調查詢
        if 'callback_query' in update:
            return handle_callback_query(update)
        
        # 處理文字訊息
        elif 'message' in update and 'text' in update['message']:
            return handle_text_message(update)
        
        return 'OK'
    except Exception as e:
        print(f"webhook 錯誤：{e}")
        return 'OK'

def handle_callback_query(update):
    """處理回調查詢"""
    callback_data = update['callback_query']['data']
    chat_id = update['callback_query']['message']['chat']['id']
    user_id = update['callback_query']['from']['id']
    is_private = not str(chat_id).startswith('-100')
    
    # 在群組中需要正確的 thread_id
    thread_id = None
    if not is_private:
        thread_id = update['callback_query']['message'].get('message_thread_id')
    
    if callback_data in COMMANDS:
        send_message(chat_id, COMMANDS[callback_data], None, thread_id)
    elif callback_data == 'help':
        send_message(chat_id, get_help_text(), None, thread_id)
    elif is_private and callback_data.startswith('private_'):
        handle_private_admin_button(callback_data, chat_id, user_id)
    elif is_private and (callback_data.startswith('copy_uid_') or callback_data.startswith('add_this_user_')):
        handle_uid_query_buttons(callback_data, chat_id, user_id)
    
    answer_callback_query(update['callback_query']['id'])
    return 'OK'

def handle_text_message(update):
    """處理文字訊息"""
    message_text = update['message']['text']
    chat_id = update['message']['chat']['id']
    user_id = update['message']['from']['id']
    is_private = not str(chat_id).startswith('-100')
    
    # UID 查詢處理
    if ('forward_from' in update['message'] and 
        not message_text.startswith('/') and is_admin(user_id)):
        handle_uid_query(update, chat_id)
        return 'OK'
    
    # 權限檢查
    if not is_private and not should_process_message(update, user_id, message_text):
        return 'OK'
    
    # 管理員命令
    if is_admin(user_id) and message_text.startswith('/admin'):
        if is_private:
            handle_private_admin_message(message_text, chat_id, user_id)
        else:
            handle_group_admin_command(message_text, chat_id, user_id, update)
    
    # 一般用戶命令
    else:
        handle_user_commands(message_text, chat_id, user_id, is_private, update)
    
    return 'OK'

def handle_private_admin_message(message_text, chat_id, user_id):
    """處理私聊中的管理員訊息"""
    if message_text == '/admin':
        menu_text = "👑 管理員控制面板"
        markup = create_private_admin_markup(user_id)
        send_message(chat_id, menu_text, markup)
    elif message_text.startswith('/admin '):
        if is_super_admin(user_id) and message_text.startswith('/admin logs'):
            handle_super_admin_commands(message_text, chat_id, user_id)
        else:
            handle_private_admin_command(message_text, chat_id, user_id)
    elif message_text.strip().isdigit():
        handle_admin_uid_input(message_text, chat_id, user_id)

# ========== 設定命令和 Webhook ==========
def set_bot_commands():
    """設定機器人命令清單"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
        commands_list = []
        
        for cmd, description in [
            ("ca", "📜 合約地址"), ("web", "🌐 官方網站"), ("announcements", "📣 社群公告"),
            ("rules", "📑 社群規範"), ("jup_lock", "🔐 鎖倉資訊"), ("pumpswap", "⛏️ 流動性礦池教學"),
            ("invitation_code", "🔗 註冊連結"), ("x", "𝕏 推特"), ("dc", "💬 Discord"),
            ("threads", "@ Threads"), ("start", "✅ 開啟選單"), ("help", "📋 指令清單")
        ]:
            commands_list.append({"command": cmd, "description": description})
        
        payload = {"commands": commands_list}
        requests.post(url, json=payload, timeout=5)
        print("✅ 命令清單設定完成")
    except Exception as e:
        print(f"設定命令清單錯誤：{e}")

@app.route('/')
def home():
    return "🤖 10K DOG Bot is Running!"

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f"https://{request.host}/webhook"
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
        response = requests.get(url, timeout=5)
        set_bot_commands()
        return response.json()
    except Exception as e:
        print(f"設定 webhook 錯誤：{e}")
        return {"error": str(e)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)