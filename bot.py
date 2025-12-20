import os
import json
from flask import Flask, request
import requests
import datetime
import pytz

app = Flask(__name__)

# ================== ENV ==================
TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN = 8126033106

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID", "")

TAIWAN_TZ = pytz.timezone("Asia/Taipei")

GIST_FILENAME = "10k_dog_bot_data.json"
current_gist_id = GIST_ID

# ================== Gist Schema Keys ==================
KEY_ADMINS = "admins"
KEY_THREADS_JARVIS = "allowed_threads_jarvis"
KEY_THREADS_SPARKSIGN = "allowed_threads_sparksign"
KEY_SPARKSIGN_SETTINGS = "sparksign_settings"
KEY_LOGS = "admin_logs"


# ================== Gist Data Management ==================
def get_default_data():
    now_iso = datetime.datetime.now(TAIWAN_TZ).isoformat()
    return {
        KEY_ADMINS: {
            str(SUPER_ADMIN): {
                "added_by": "system",
                "added_time": now_iso,
                "is_super": True,
            }
        },
        KEY_THREADS_JARVIS: {},
        KEY_THREADS_SPARKSIGN: {},
        KEY_SPARKSIGN_SETTINGS: {},
        KEY_LOGS: [],
    }


def _github_headers():
    return {"Authorization": f"token {GIST_TOKEN}"}


def load_data():
    """Load Gist JSON; includes safe migration for legacy keys."""
    global current_gist_id

    if not GIST_TOKEN:
        print("❌ 未設定 GIST_TOKEN")
        return get_default_data()

    try:
        headers = _github_headers()

        # Determine gist id
        if current_gist_id:
            url = f"https://api.github.com/gists/{current_gist_id}"
        else:
            # Search gists for the file
            url = "https://api.github.com/gists"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                print(f"❌ 搜尋 Gist 失敗: {r.status_code}")
                return get_default_data()

            found = None
            for gist in r.json():
                if GIST_FILENAME in gist.get("files", {}):
                    found = gist
                    break

            if not found:
                # Create new gist
                default_data = get_default_data()
                save_data(default_data)
                return default_data

            current_gist_id = found["id"]
            url = f"https://api.github.com/gists/{current_gist_id}"

        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"❌ 讀取 Gist 失敗: {r.status_code}")
            return get_default_data()

        gist_data = r.json()
        if GIST_FILENAME not in gist_data.get("files", {}):
            # File missing -> recreate default file into this gist
            default_data = get_default_data()
            save_data(default_data)
            return default_data

        content = gist_data["files"][GIST_FILENAME]["content"]
        loaded = json.loads(content) if content else {}

        # ---- Migration / normalization (no command compatibility; only data safety)
        # Legacy: allowed_threads / allowed_threads_mark -> allowed_threads_jarvis
        if KEY_THREADS_JARVIS not in loaded:
            if isinstance(loaded.get("allowed_threads_mark"), dict):
                loaded[KEY_THREADS_JARVIS] = loaded.get("allowed_threads_mark") or {}
            elif isinstance(loaded.get("allowed_threads"), dict):
                loaded[KEY_THREADS_JARVIS] = loaded.get("allowed_threads") or {}
            else:
                loaded[KEY_THREADS_JARVIS] = {}

        # Ensure SparkSign thread list exists
        if KEY_THREADS_SPARKSIGN not in loaded or not isinstance(loaded.get(KEY_THREADS_SPARKSIGN), dict):
            loaded[KEY_THREADS_SPARKSIGN] = {}

        # Ensure admins/logs exist
        if KEY_ADMINS not in loaded or not isinstance(loaded.get(KEY_ADMINS), dict):
            loaded[KEY_ADMINS] = get_default_data()[KEY_ADMINS]
        if KEY_LOGS not in loaded or not isinstance(loaded.get(KEY_LOGS), list):
            loaded[KEY_LOGS] = []
        if KEY_SPARKSIGN_SETTINGS not in loaded or not isinstance(loaded.get(KEY_SPARKSIGN_SETTINGS), dict):
            loaded[KEY_SPARKSIGN_SETTINGS] = {}

        print("✅ 從 Gist 讀取資料成功")
        return loaded

    except Exception as e:
        print(f"❌ 讀取資料錯誤: {e}")
        return get_default_data()


def save_data(data_to_save):
    """Save JSON into Gist file."""
    global current_gist_id

    if not GIST_TOKEN:
        print("❌ 未設定 GIST_TOKEN，無法儲存")
        return

    try:
        headers = _github_headers()
        files = {GIST_FILENAME: {"content": json.dumps(data_to_save, ensure_ascii=False, indent=2)}}

        if current_gist_id:
            r = requests.patch(
                f"https://api.github.com/gists/{current_gist_id}",
                headers=headers,
                json={"files": files},
                timeout=10,
            )
        else:
            r = requests.post(
                "https://api.github.com/gists",
                headers=headers,
                json={"public": False, "description": "10K DOG Bot Data", "files": files},
                timeout=10,
            )
            if r.status_code == 201:
                current_gist_id = r.json()["id"]
                print(f"✅ 創建新 Gist: {current_gist_id}")

        if r.status_code in [200, 201]:
            print("✅ 資料已儲存到 Gist")
        else:
            print(f"❌ 儲存失敗: {r.status_code}")

    except Exception as e:
        print(f"❌ 儲存錯誤: {e}")


data = load_data()


def update_data(key, value):
    data[key] = value
    save_data(data)


# ================== Data Accessors ==================
def get_admins():
    return data.get(KEY_ADMINS, {})


def get_threads(scope: str):
    if scope == "jarvis":
        return data.get(KEY_THREADS_JARVIS, {})
    if scope == "sparksign":
        return data.get(KEY_THREADS_SPARKSIGN, {})
    return {}


def get_logs():
    return data.get(KEY_LOGS, [])


# ================== Admin Ops ==================
def is_admin(user_id: int) -> bool:
    return str(user_id) in get_admins()


def is_super_admin(user_id: int) -> bool:
    return get_admins().get(str(user_id), {}).get("is_super", False)


def add_admin(admin_id: int, added_by: int) -> bool:
    admins = get_admins()
    s = str(admin_id)
    if s in admins:
        return False
    admins[s] = {
        "added_by": added_by,
        "added_time": datetime.datetime.now(TAIWAN_TZ).isoformat(),
        "is_super": False,
    }
    update_data(KEY_ADMINS, admins)
    return True


def remove_admin(admin_id: int, removed_by: int):
    admins = get_admins()
    s = str(admin_id)
    rb = str(removed_by)

    if s not in admins:
        return False, "❌ 該用戶不是管理員"
    if admins[s].get("is_super", False):
        return False, "❌ 無法刪除超級管理員"
    if rb not in admins:
        return False, "❌ 您沒有管理員權限"

    del admins[s]
    update_data(KEY_ADMINS, admins)
    return True, "✅ 已移除管理員"


# ================== Thread Ops ==================
def toggle_thread(chat_id, thread_id, add=True, scope="jarvis"):
    threads = get_threads(scope)
    key = f"{chat_id}_{thread_id}"

    if add:
        threads[key] = True
    else:
        if key not in threads:
            return False
        del threads[key]

    if scope == "jarvis":
        update_data(KEY_THREADS_JARVIS, threads)
    else:
        update_data(KEY_THREADS_SPARKSIGN, threads)
    return True


# ================== Logging ==================
def log_action(admin_id, action, target=None, details=None):
    logs = get_logs()

    admin_info = get_user_info(admin_id)
    admin_name = get_display_name(admin_info) if admin_info else str(admin_id)

    log_entry = {
        "timestamp": datetime.datetime.now(TAIWAN_TZ).isoformat(),
        "admin_id": admin_id,
        "admin_name": admin_name,
        "action": action,
        "target_id": target,
        "details": details,
    }

    if target:
        target_info = get_user_info(target)
        if target_info:
            log_entry["target_name"] = get_display_name(target_info)

    logs.append(log_entry)
    if len(logs) > 100:
        logs.pop(0)

    update_data(KEY_LOGS, logs)


# ================== Permissions ==================
def should_process(update, user_id, text):
    if "message" not in update:
        return False

    chat_id = update["message"]["chat"]["id"]

    # Private chat always allowed
    if not str(chat_id).startswith("-100"):
        return True

    # Group admin commands always allowed (new naming only)
    admin_cmds = {
        "/admin add_Jarvis",
        "/admin remove_Jarvis",
        "/admin add_SparkSign",
        "/admin remove_SparkSign",
    }
    if is_admin(user_id) and text in admin_cmds:
        return True

    # Normal functions require Jarvis-allowed thread
    thread_id = update["message"].get("message_thread_id", 0)
    return f"{chat_id}_{thread_id}" in get_threads("jarvis")


# ================== Commands / UI ==================
COMMANDS = {
    "ca": "C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "https://10kcoin.com/",
    "announcements": "https://t.me/tenkdogcrypto",
    "rules": "https://t.me/tenkdogcrypto/71",
    "jup_lock": "https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "https://t.me/tenkdogcrypto/72",
    "invitation_code": "https://t.me/tenkdogcrypto/122",
    "vote": "https://t.me/tenkdogcrypto/121",
    "linktree": "https://linktr.ee/10kdog",
    "buy": """第一段，買SOL+開Phantom:
https://t.me/tenkdogcrypto/141
第二段，用SOL買10K DOG:
https://t.me/tenkdogcrypto/142""",
    "slogan": """儘管失敗一萬次，只要贏一次，那就足夠

1 time winning is greater than 10,000 times failure

1回の勝利は10,000回の失敗に勝る

만 번 실패하더라도 단 한 번만 이겨도 족하다""",
}

HELP_TEXT = """📋 指令清單：

/start - ✅ 開啟選單
/help - 📋 顯示指令清單
/ca - 📜 合約地址
/web - 🌐 官方網站
/announcements - 📣 社群公告
/rules - 📑 社群規範
/slogan - 🗣️ 精神標語
/jup_lock - 🔐 鎖倉資訊
/pumpswap - ⛏️ 流動性礦池教學
/invitation_code - 🔗 註冊連結
/buy - 💲 購買教學
/vote - 🗳️ 投票排行網站
/linktree - ➡️ 前往linktree"""


def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📜 合約地址", "callback_data": "ca"}],
            [{"text": "🌐 官網網站", "callback_data": "web"}, {"text": "➡️ 前往linktree", "callback_data": "linktree"}],
            [{"text": "📣 社群公告", "callback_data": "announcements"}, {"text": "📑 社群規範", "callback_data": "rules"}, {"text": "🗣️ 精神標語", "callback_data": "slogan"}],
            [{"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"}, {"text": "🔗 註冊連結", "callback_data": "invitation_code"}, {"text": "💲 購買教學", "callback_data": "buy"}],
            [{"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"}, {"text": "🗳️投票排行網站", "callback_data": "vote"}],
            [{"text": "📋 指令清單", "callback_data": "help"}],
        ]
    }


def admin_menu(user_id):
    keyboard = [
        [{"text": "👥 管理員列表", "callback_data": "admin_list"}, {"text": "🔍 查詢TG UID", "callback_data": "admin_query_uid"}],
        [{"text": "➕ 新增管理員", "callback_data": "admin_add"}, {"text": "❌ 移除管理員", "callback_data": "admin_remove"}],
        [{"text": "📋 Jarvis 話題列表", "callback_data": "admin_threads_jarvis"},
         {"text": "✨ SparkSign 話題列表", "callback_data": "admin_threads_sparksign"}],
        [{"text": "🛠️ 群組指令說明", "callback_data": "admin_help"}],
    ]
    if is_super_admin(user_id):
        keyboard.append([{"text": "📊 操作紀錄", "callback_data": "admin_logs"}])

    keyboard.append([{"text": "🔙 主選單", "callback_data": "main_menu"}])
    return {"inline_keyboard": keyboard}


# ================== Telegram API helpers ==================
def send_message(chat_id, text, markup=None, thread_id=None):
    try:
        payload = {"chat_id": chat_id, "text": text}
        # allow 0 explicitly
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        if markup:
            payload["reply_markup"] = json.dumps(markup)
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=8)
    except Exception as e:
        print(f"傳送訊息錯誤: {e}")


def answer_callback(callback_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=5,
        )
    except:
        pass


def get_user_info(user_id):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": user_id},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json().get("result", {})
    except:
        pass
    return None


def get_display_name(user_info):
    if not user_info:
        return "未知用戶"
    first_name = user_info.get("first_name", "") or ""
    last_name = user_info.get("last_name", "") or ""
    username = user_info.get("username", "") or ""
    full_name = f"{first_name} {last_name}".strip()
    if full_name and username:
        return f"{full_name} (@{username})"
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return "未知用戶"


def get_chat_info(chat_id):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": chat_id},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json().get("result", {})
    except:
        pass
    return None


def get_thread_name(chat_id, thread_id):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getForumTopic",
            json={"chat_id": chat_id, "message_thread_id": thread_id},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json().get("result", {}).get("name", "未知話題")
    except:
        pass
    return "未知話題"


# ================== List renderers ==================
def get_admin_list_with_names():
    admins = get_admins()
    if not admins:
        return "👥 目前沒有管理員"

    msg = "👥 管理員列表：\n\n"
    for admin_id, info in admins.items():
        try:
            u = get_user_info(int(admin_id))
            name = get_display_name(u)
            role = "👑 超級管理員" if info.get("is_super", False) else "👤 管理員"
            msg += f"{role} - {name}\n🔢 ID: {admin_id}\n\n"
        except:
            msg += f"👤 未知用戶\n🔢 ID: {admin_id}\n\n"
    return msg


def get_thread_list_with_names(scope="jarvis"):
    threads = get_threads(scope)
    label = "📋 Jarvis" if scope == "jarvis" else "✨ SparkSign"

    if not threads:
        return f"{label} 目前沒有允許的話題"

    msg = f"{label} 允許的話題列表：\n\n"
    for thread_key in threads.keys():
        try:
            chat_id, tid = thread_key.split("_")
            tid_int = int(tid) if tid != "0" else 0

            chat_info = get_chat_info(chat_id)
            chat_title = chat_info.get("title", "未知群組") if chat_info else "未知群組"

            if tid_int == 0:
                msg += f"💬 主聊天室\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
            else:
                tname = get_thread_name(chat_id, tid_int)
                msg += f"💬 話題: {tname}\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
        except:
            msg += f"💬 話題\n🔢 識別碼: {thread_key}\n\n"
    return msg


# ================== Handlers ==================
def handle_uid_query(update, chat_id):
    try:
        user = update["message"]["forward_from"]
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "未知"
        username = f"@{user.get('username')}" if user.get("username") else "未設定"

        text = f"""🔍 用戶 UID 查詢結果

👤 姓名：{name}
🔢 UID：{user['id']}
📧 用戶名：{username}"""

        markup = {
            "inline_keyboard": [
                [{"text": "📋 複製UID", "callback_data": f"copy_{user['id']}"}],
                [{"text": "➕ 新增此用戶為管理員", "callback_data": f"add_{user['id']}"}],
                [{"text": "🔙 管理員面板", "callback_data": "admin_menu"}],
            ]
        }
        send_message(chat_id, text, markup)
    except:
        send_message(chat_id, "❌ 查詢失敗")


def handle_uid_input(text, chat_id, user_id):
    try:
        uid = int(text.strip())
        if is_super_admin(user_id):
            if add_admin(uid, user_id):
                send_message(chat_id, f"✅ 已新增管理員: {uid}")
                log_action(user_id, "add_admin", uid)
            else:
                send_message(chat_id, f"❌ 用戶 {uid} 已經是管理員")
        else:
            send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
    except ValueError:
        send_message(chat_id, "❌ 請輸入有效的數字 UID")


def handle_admin_command(text, chat_id, user_id):
    if text == "/admin":
        send_message(chat_id, "👑 Jarvis 管理員控制面板", admin_menu(user_id))

    elif text.startswith("/admin add_admin "):
        if not is_super_admin(user_id):
            send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
            return
        try:
            new_id = int(text.split(" ")[2])
            if add_admin(new_id, user_id):
                send_message(chat_id, f"✅ 已新增管理員: {new_id}")
                log_action(user_id, "add_admin", new_id)
            else:
                send_message(chat_id, f"❌ 用戶 {new_id} 已經是管理員")
        except:
            send_message(chat_id, "❌ 請提供有效的用戶ID")

    elif text.startswith("/admin remove_admin "):
        try:
            rid = int(text.split(" ")[2])
            ok, msg = remove_admin(rid, user_id)
            send_message(chat_id, msg)
            if ok:
                log_action(user_id, "remove_admin", rid)
        except:
            send_message(chat_id, "❌ 請提供有效的用戶ID")

    elif text == "/admin list_admins":
        send_message(chat_id, get_admin_list_with_names())

    elif text == "/admin list_threads":
        # Keep as Jarvis threads list (private chat use)
        send_message(chat_id, get_thread_list_with_names("jarvis"))

    elif text.startswith("/admin logs") and is_super_admin(user_id):
        logs = get_logs()[-10:]
        if not logs:
            send_message(chat_id, "📊 目前沒有操作紀錄")
        else:
            msg = "📊 最近操作紀錄：\n\n"
            for log in reversed(logs):
                t = datetime.datetime.fromisoformat(log["timestamp"]).strftime("%m/%d %H:%M")
                admin_name = log.get("admin_name", log.get("admin_id"))
                action = log.get("action")
                details = log.get("details")
                line = f"⏰ {t} | 👤 {admin_name} | {action}"
                if details:
                    line += f" | {details}"
                msg += line + "\n"
            send_message(chat_id, msg)


def handle_group_admin(text, chat_id, user_id, update):
    thread_id = update["message"].get("message_thread_id", 0)

    if text == "/admin add_Jarvis":
        if toggle_thread(chat_id, thread_id, True, "jarvis"):
            send_message(chat_id, "✅ 已允許當前話題（Jarvis）", None, thread_id)
            log_action(user_id, "add_thread_jarvis", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 操作失敗", None, thread_id)

    elif text == "/admin remove_Jarvis":
        if toggle_thread(chat_id, thread_id, False, "jarvis"):
            send_message(chat_id, "❌ 已移除話題權限（Jarvis）", None, thread_id)
            log_action(user_id, "remove_thread_jarvis", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 此話題未被允許（Jarvis）", None, thread_id)

    elif text == "/admin add_SparkSign":
        if toggle_thread(chat_id, thread_id, True, "sparksign"):
            send_message(chat_id, "✅ 已允許當前話題（SparkSign）", None, thread_id)
            log_action(user_id, "add_thread_sparksign", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 操作失敗", None, thread_id)

    elif text == "/admin remove_SparkSign":
        if toggle_thread(chat_id, thread_id, False, "sparksign"):
            send_message(chat_id, "❌ 已移除話題權限（SparkSign）", None, thread_id)
            log_action(user_id, "remove_thread_sparksign", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 此話題未被允許（SparkSign）", None, thread_id)


def handle_user_command(text, chat_id, is_private, update=None):
    clean_text = text.split("@")[0] if "@" in text else text

    thread_id = None
    if not is_private and update and "message" in update:
        thread_id = update["message"].get("message_thread_id", 0)

    if clean_text == "/start":
        send_message(chat_id, "🤖 歡迎使用 10K DOG - Jarvis", main_menu(), thread_id)
    elif clean_text == "/help":
        send_message(chat_id, HELP_TEXT, None, thread_id)
    elif clean_text.startswith("/"):
        cmd = clean_text[1:].lower().split(" ")[0]
        if cmd in COMMANDS:
            send_message(chat_id, COMMANDS[cmd], None, thread_id)


def handle_callback(data_cb, chat_id, user_id, message_thread_id=None):
    is_private = not str(chat_id).startswith("-100")

    # Admin callbacks only in private chat
    if data_cb.startswith("admin_") and not is_private:
        if message_thread_id is not None:
            send_message(chat_id, "❌ 管理員功能僅在私聊中可用", None, message_thread_id)
        return

    # Group: require Jarvis enabled thread for non-basic actions
    if not is_private:
        thread_key = f"{chat_id}_{message_thread_id or 0}"
        if thread_key not in get_threads("jarvis") and data_cb not in ("main_menu", "help"):
            send_message(chat_id, "❌ 此話題未啟用 Jarvis 功能", None, message_thread_id)
            return

    if data_cb in COMMANDS:
        send_message(chat_id, COMMANDS[data_cb], None, message_thread_id)

    elif data_cb == "help":
        send_message(chat_id, HELP_TEXT, None, message_thread_id)

    elif data_cb == "main_menu":
        send_message(chat_id, "🤖 10K DOG - Jarvis", main_menu(), message_thread_id)

    elif data_cb == "admin_menu":
        send_message(chat_id, "👑 Jarvis 管理員控制面板", admin_menu(user_id))

    elif data_cb == "admin_list":
        send_message(chat_id, get_admin_list_with_names())

    elif data_cb == "admin_query_uid":
        send_message(chat_id, "🔍 請轉發用戶訊息給我查詢 UID")

    elif data_cb == "admin_add":
        if is_super_admin(user_id):
            send_message(chat_id, "➕ 請直接輸入要新增的用戶 UID 數字")
        else:
            send_message(chat_id, "❌ 只有超級管理員可以新增管理員")

    elif data_cb == "admin_remove":
        send_message(chat_id, "❌ 請直接輸入要移除的用戶 UID 數字")

    elif data_cb == "admin_threads_jarvis":
        send_message(chat_id, get_thread_list_with_names("jarvis"))

    elif data_cb == "admin_threads_sparksign":
        send_message(chat_id, get_thread_list_with_names("sparksign"))

    elif data_cb == "admin_help":
        send_message(
            chat_id,
            "🛠️ 群組話題授權（只透過 Jarvis 操作）：\n"
            "/admin add_Jarvis - 允許當前話題（Jarvis）\n"
            "/admin remove_Jarvis - 移除當前話題（Jarvis）\n\n"
            "✨ SparkSign 話題授權（仍由 Jarvis 操作）：\n"
            "/admin add_SparkSign - 允許當前話題（SparkSign）\n"
            "/admin remove_SparkSign - 移除當前話題（SparkSign）"
        )

    elif data_cb == "admin_logs" and is_super_admin(user_id):
        logs = get_logs()[-10:]
        if not logs:
            send_message(chat_id, "📊 目前沒有操作紀錄")
        else:
            msg = "📊 最近操作紀錄：\n\n"
            for log in reversed(logs):
                t = datetime.datetime.fromisoformat(log["timestamp"]).strftime("%m/%d %H:%M")
                admin_name = log.get("admin_name", log.get("admin_id"))
                action = log.get("action")
                details = log.get("details")
                line = f"⏰ {t} | 👤 {admin_name} | {action}"
                if details:
                    line += f" | {details}"
                msg += line + "\n"
            send_message(chat_id, msg)

    elif data_cb.startswith("copy_"):
        send_message(chat_id, data_cb.replace("copy_", ""))

    elif data_cb.startswith("add_") and is_super_admin(user_id):
        try:
            uid = int(data_cb.replace("add_", ""))
            if add_admin(uid, user_id):
                send_message(chat_id, f"✅ 已新增用戶 {uid} 為管理員")
                log_action(user_id, "add_admin", uid)
            else:
                send_message(chat_id, f"❌ 用戶 {uid} 已經是管理員")
        except:
            send_message(chat_id, "❌ 操作失敗")


# ================== Routes ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = request.get_json(force=True, silent=True) or {}

        # Callback query
        if "callback_query" in update:
            cb = update["callback_query"]
            data_cb = cb["data"]
            chat_id = cb["message"]["chat"]["id"]
            user_id = cb["from"]["id"]
            is_private = not str(chat_id).startswith("-100")

            # Admin callbacks blocked in groups
            if data_cb.startswith("admin_") and not is_private:
                answer_callback(cb["id"])
                return "OK"

            thread_id = None if is_private else cb["message"].get("message_thread_id", 0)
            handle_callback(data_cb, chat_id, user_id, thread_id)
            answer_callback(cb["id"])
            return "OK"

        # Text messages
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            text = msg["text"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            is_private = not str(chat_id).startswith("-100")

            # Private: forward-from UID lookup (admins only)
            if is_private and "forward_from" in msg and not text.startswith("/") and is_admin(user_id):
                handle_uid_query(update, chat_id)
                return "OK"

            # Private: numeric UID input (admins only)
            if is_private and is_admin(user_id) and text.strip().isdigit():
                handle_uid_input(text, chat_id, user_id)
                return "OK"

            # Permission check for groups
            if not is_private and not should_process(update, user_id, text):
                return "OK"

            # Admin commands
            if is_admin(user_id) and text.startswith("/admin"):
                if is_private:
                    handle_admin_command(text, chat_id, user_id)
                else:
                    handle_group_admin(text, chat_id, user_id, update)
            else:
                handle_user_command(text, chat_id, is_private, update)

        return "OK"
    except Exception as e:
        print(f"Webhook 錯誤: {e}")
        return "OK"


@app.route("/")
def home():
    return "🤖 10K DOG - Jarvis is Running!"


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    webhook_url = f"https://{request.host}/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    return requests.get(url, timeout=10).json()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
