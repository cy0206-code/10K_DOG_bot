# app.py
# 10K DOG - Jarvis (Flask) — 三檔 Gist 版本（CORE + RT_JARVIS）
# - 已移除 tg-premiumemoji 相關功能（整段刪除）
# - CORE：admins / allowed_threads_* / link_settings / link_whitelist（低頻、共享）
# - RT_JARVIS：link_violations / admin_logs（高頻、Jarvis 獨立）
# - 禁止「讀取失敗時用空 dict 覆蓋 gist」：read error 只走 stale/last_good，不會 patch 空內容
#
# ENV:
#   BOT_TOKEN
#   GIST_TOKEN
#   GIST_ID_CORE
#   GIST_ID_RT_JARVIS
#   (optional) CORE_TTL_SEC, RT_TTL_SEC, CORE_SAVE_DEBOUNCE_SEC, RT_SAVE_DEBOUNCE_SEC, CB_FAIL_THRESHOLD, CB_OPEN_SEC

import os
import json
import re
import datetime
import pytz
import threading
from time import time as _now
from flask import Flask, request
import requests

app = Flask(__name__)

# ================== ENV ==================
TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN = 8126033106

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID_CORE = os.environ.get("GIST_ID_CORE", "").strip()
GIST_ID_RT_JARVIS = os.environ.get("GIST_ID_RT_JARVIS", "").strip()

TAIWAN_TZ = pytz.timezone("Asia/Taipei")
BOT_NAME = "10K DOG - Jarvis"

# ================== Gist filenames ==================
CORE_FILENAME = "10k_dog_core.json"
RT_FILENAME = "10k_dog_runtime_jarvis.json"

# ================== Core keys ==================
KEY_ADMINS = "admins"
KEY_THREADS_JARVIS = "allowed_threads_jarvis"
KEY_THREADS_SPARKSIGN = "allowed_threads_sparksign"
KEY_LINK_SETTINGS = "link_settings"       # { chat_id: { enabled: bool, mute_days: int, third_action: "kick"|"ban" } }
KEY_LINK_WHITELIST = "link_whitelist"     # { chat_id: { user_id: {added_by, added_time} } }

# ================== Runtime keys (Jarvis) ==================
KEY_LINK_VIOLATIONS = "link_violations"   # { chat_id: { user_id: {count:int, last_time:iso} } }
KEY_LOGS = "admin_logs"                   # list

# ================== Gist Data Cache (High-Load Hardened) ==================
CORE_DATA = {}
RT_DATA = {}

CORE_CACHE = {
    "loaded_ts": 0.0,
    "etag": None,
    "dirty": False,
    "dirty_ts": 0.0,
    "last_flush_ts": 0.0,
    "last_ok_flush_ts": 0.0,
    "fail_count": 0,
    "cb_open_until": 0.0,
    "last_err": "",
}

RT_CACHE = {
    "loaded_ts": 0.0,
    "etag": None,
    "dirty": False,
    "dirty_ts": 0.0,
    "last_flush_ts": 0.0,
    "last_ok_flush_ts": 0.0,
    "fail_count": 0,
    "cb_open_until": 0.0,
    "last_err": "",
}

CORE_TTL_SEC = float(os.environ.get("CORE_TTL_SEC", "60"))
RT_TTL_SEC = float(os.environ.get("RT_TTL_SEC", "20"))

CORE_SAVE_DEBOUNCE_SEC = float(os.environ.get("CORE_SAVE_DEBOUNCE_SEC", "2.5"))
RT_SAVE_DEBOUNCE_SEC = float(os.environ.get("RT_SAVE_DEBOUNCE_SEC", "2.0"))

CB_FAIL_THRESHOLD = int(os.environ.get("CB_FAIL_THRESHOLD", "3"))
CB_OPEN_SEC = float(os.environ.get("CB_OPEN_SEC", "10"))

CORE_LOAD_LOCK = threading.Lock()
CORE_SAVE_LOCK = threading.Lock()
RT_LOAD_LOCK = threading.Lock()
RT_SAVE_LOCK = threading.Lock()


def _github_headers(extra: dict = None):
    h = {"Accept": "application/vnd.github+json"}
    if GIST_TOKEN:
        h["Authorization"] = f"token {GIST_TOKEN}"
    if extra:
        h.update(extra)
    return h


def _cb_is_open(cache: dict) -> bool:
    return _now() < float(cache.get("cb_open_until", 0) or 0)


def _cb_record_failure(cache: dict, err: str):
    cache["fail_count"] = int(cache.get("fail_count", 0) or 0) + 1
    cache["last_err"] = str(err or "")[:240]
    if cache["fail_count"] >= CB_FAIL_THRESHOLD:
        cache["cb_open_until"] = _now() + CB_OPEN_SEC


def _cb_record_success(cache: dict):
    cache["fail_count"] = 0
    cache["cb_open_until"] = 0.0
    cache["last_err"] = ""


def _now_iso():
    return datetime.datetime.now(TAIWAN_TZ).isoformat()


def get_default_core():
    return {
        KEY_ADMINS: {
            str(SUPER_ADMIN): {"added_by": "system", "added_time": _now_iso(), "is_super": True}
        },
        KEY_THREADS_JARVIS: {},
        KEY_THREADS_SPARKSIGN: {},
        KEY_LINK_SETTINGS: {},
        KEY_LINK_WHITELIST: {},
    }


def get_default_rt():
    return {
        KEY_LINK_VIOLATIONS: {},
        KEY_LOGS: [],
    }


def _ensure_defaults_core(d: dict) -> dict:
    if not isinstance(d, dict):
        d = {}

    # Threads migration fallback (just in case)
    if KEY_THREADS_JARVIS not in d:
        if isinstance(d.get("allowed_threads_mark"), dict):
            d[KEY_THREADS_JARVIS] = d.get("allowed_threads_mark") or {}
        elif isinstance(d.get("allowed_threads"), dict):
            d[KEY_THREADS_JARVIS] = d.get("allowed_threads") or {}
        else:
            d[KEY_THREADS_JARVIS] = {}

    d.setdefault(KEY_THREADS_SPARKSIGN, {})
    d.setdefault(KEY_ADMINS, get_default_core()[KEY_ADMINS])
    d.setdefault(KEY_LINK_SETTINGS, {})
    d.setdefault(KEY_LINK_WHITELIST, {})

    # Type safety
    if not isinstance(d.get(KEY_ADMINS), dict):
        d[KEY_ADMINS] = get_default_core()[KEY_ADMINS]
    if not isinstance(d.get(KEY_THREADS_JARVIS), dict):
        d[KEY_THREADS_JARVIS] = {}
    if not isinstance(d.get(KEY_THREADS_SPARKSIGN), dict):
        d[KEY_THREADS_SPARKSIGN] = {}
    if not isinstance(d.get(KEY_LINK_SETTINGS), dict):
        d[KEY_LINK_SETTINGS] = {}
    if not isinstance(d.get(KEY_LINK_WHITELIST), dict):
        d[KEY_LINK_WHITELIST] = {}

    return d


def _ensure_defaults_rt(d: dict) -> dict:
    if not isinstance(d, dict):
        d = {}
    d.setdefault(KEY_LINK_VIOLATIONS, {})
    d.setdefault(KEY_LOGS, [])

    if not isinstance(d.get(KEY_LINK_VIOLATIONS), dict):
        d[KEY_LINK_VIOLATIONS] = {}
    if not isinstance(d.get(KEY_LOGS), list):
        d[KEY_LOGS] = []

    return d


def _gist_get(gist_id: str, filename: str, cache: dict) -> dict:
    if not gist_id:
        raise RuntimeError("missing gist id")

    url = f"https://api.github.com/gists/{gist_id}"
    extra = {}
    if cache.get("etag"):
        extra["If-None-Match"] = cache["etag"]

    r = requests.get(url, headers=_github_headers(extra), timeout=12)

    if r.status_code == 304:
        return None

    if r.status_code != 200:
        raise RuntimeError(f"gist get failed: {r.status_code} {getattr(r, 'text', '')[:180]}")

    etag = r.headers.get("ETag")
    if etag:
        cache["etag"] = etag

    gist_data = r.json() or {}
    files = gist_data.get("files") or {}
    if filename not in files:
        # 不自動 patch（避免把空內容寫回），直接視為 read error，走 stale
        raise RuntimeError(f"gist missing file: {filename}")

    content = (files[filename] or {}).get("content", "") or ""
    loaded = json.loads(content) if content else {}
    return loaded


def _gist_patch(gist_id: str, filename: str, data_to_save: dict, cache: dict):
    if not gist_id:
        raise RuntimeError("missing gist id")

    files = {filename: {"content": json.dumps(data_to_save, ensure_ascii=False, indent=2)}}
    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers=_github_headers(),
        json={"files": files},
        timeout=12,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"gist patch failed: {r.status_code} {getattr(r, 'text', '')[:200]}")

    etag = r.headers.get("ETag")
    if etag:
        cache["etag"] = etag


def refresh_core(force: bool = False):
    global CORE_DATA

    if not GIST_TOKEN or not GIST_ID_CORE:
        if not CORE_DATA:
            CORE_DATA = get_default_core()
        return

    now = _now()
    if (not force) and CORE_DATA and (now - float(CORE_CACHE.get("loaded_ts", 0) or 0) < CORE_TTL_SEC):
        return

    if _cb_is_open(CORE_CACHE):
        if not CORE_DATA:
            CORE_DATA = get_default_core()
        return

    acquired = CORE_LOAD_LOCK.acquire(timeout=0.15)
    if not acquired:
        if not CORE_DATA:
            CORE_DATA = get_default_core()
        return

    try:
        now = _now()
        if (not force) and CORE_DATA and (now - float(CORE_CACHE.get("loaded_ts", 0) or 0) < CORE_TTL_SEC):
            return

        loaded = _gist_get(GIST_ID_CORE, CORE_FILENAME, CORE_CACHE)
        if loaded is None:
            CORE_CACHE["loaded_ts"] = now
            _cb_record_success(CORE_CACHE)
            return

        CORE_DATA = _ensure_defaults_core(loaded)
        CORE_CACHE["loaded_ts"] = now
        _cb_record_success(CORE_CACHE)

    except Exception as e:
        _cb_record_failure(CORE_CACHE, f"refresh_core: {e}")
        if not CORE_DATA:
            CORE_DATA = get_default_core()
    finally:
        try:
            CORE_LOAD_LOCK.release()
        except Exception:
            pass


def refresh_rt(force: bool = False):
    global RT_DATA

    if not GIST_TOKEN or not GIST_ID_RT_JARVIS:
        if not RT_DATA:
            RT_DATA = get_default_rt()
        return

    now = _now()
    if (not force) and RT_DATA and (now - float(RT_CACHE.get("loaded_ts", 0) or 0) < RT_TTL_SEC):
        return

    if _cb_is_open(RT_CACHE):
        if not RT_DATA:
            RT_DATA = get_default_rt()
        return

    acquired = RT_LOAD_LOCK.acquire(timeout=0.15)
    if not acquired:
        if not RT_DATA:
            RT_DATA = get_default_rt()
        return

    try:
        now = _now()
        if (not force) and RT_DATA and (now - float(RT_CACHE.get("loaded_ts", 0) or 0) < RT_TTL_SEC):
            return

        loaded = _gist_get(GIST_ID_RT_JARVIS, RT_FILENAME, RT_CACHE)
        if loaded is None:
            RT_CACHE["loaded_ts"] = now
            _cb_record_success(RT_CACHE)
            return

        RT_DATA = _ensure_defaults_rt(loaded)
        RT_CACHE["loaded_ts"] = now
        _cb_record_success(RT_CACHE)

    except Exception as e:
        _cb_record_failure(RT_CACHE, f"refresh_rt: {e}")
        if not RT_DATA:
            RT_DATA = get_default_rt()
    finally:
        try:
            RT_LOAD_LOCK.release()
        except Exception:
            pass


def mark_dirty_core():
    CORE_CACHE["dirty"] = True
    CORE_CACHE["dirty_ts"] = _now()


def mark_dirty_rt():
    RT_CACHE["dirty"] = True
    RT_CACHE["dirty_ts"] = _now()


def flush_core_if_due(force: bool = False):
    if not GIST_TOKEN or not GIST_ID_CORE:
        return
    if not CORE_DATA or not CORE_CACHE.get("dirty", False):
        return

    now = _now()
    if (not force) and (now - float(CORE_CACHE.get("dirty_ts", 0) or 0) < CORE_SAVE_DEBOUNCE_SEC):
        return

    if _cb_is_open(CORE_CACHE):
        return

    acquired = CORE_SAVE_LOCK.acquire(timeout=0.15)
    if not acquired:
        return

    try:
        now = _now()
        if (not force) and (now - float(CORE_CACHE.get("dirty_ts", 0) or 0) < CORE_SAVE_DEBOUNCE_SEC):
            return

        CORE_CACHE["last_flush_ts"] = now
        _gist_patch(GIST_ID_CORE, CORE_FILENAME, CORE_DATA, CORE_CACHE)
        CORE_CACHE["dirty"] = False
        CORE_CACHE["last_ok_flush_ts"] = now
        _cb_record_success(CORE_CACHE)

    except Exception as e:
        _cb_record_failure(CORE_CACHE, f"flush_core: {e}")
    finally:
        try:
            CORE_SAVE_LOCK.release()
        except Exception:
            pass


def flush_rt_if_due(force: bool = False):
    if not GIST_TOKEN or not GIST_ID_RT_JARVIS:
        return
    if not RT_DATA or not RT_CACHE.get("dirty", False):
        return

    now = _now()
    if (not force) and (now - float(RT_CACHE.get("dirty_ts", 0) or 0) < RT_SAVE_DEBOUNCE_SEC):
        return

    if _cb_is_open(RT_CACHE):
        return

    acquired = RT_SAVE_LOCK.acquire(timeout=0.15)
    if not acquired:
        return

    try:
        now = _now()
        if (not force) and (now - float(RT_CACHE.get("dirty_ts", 0) or 0) < RT_SAVE_DEBOUNCE_SEC):
            return

        RT_CACHE["last_flush_ts"] = now
        _gist_patch(GIST_ID_RT_JARVIS, RT_FILENAME, RT_DATA, RT_CACHE)
        RT_CACHE["dirty"] = False
        RT_CACHE["last_ok_flush_ts"] = now
        _cb_record_success(RT_CACHE)

    except Exception as e:
        _cb_record_failure(RT_CACHE, f"flush_rt: {e}")
    finally:
        try:
            RT_SAVE_LOCK.release()
        except Exception:
            pass


def refresh_data(force: bool = False):
    refresh_core(force=force)
    refresh_rt(force=force)


def opportunistic_flush(force: bool = False):
    # 核心低頻，但管理員操作也會改 core；RT 高頻
    flush_core_if_due(force=force)
    flush_rt_if_due(force=force)


def update_core(key, value):
    refresh_core(force=False)
    CORE_DATA[key] = value
    mark_dirty_core()


def update_rt(key, value):
    refresh_rt(force=False)
    RT_DATA[key] = value
    mark_dirty_rt()


# initial load (best effort)
refresh_data(force=True)

# ================== Data Accessors ==================
def get_admins():
    refresh_core(force=False)
    return CORE_DATA.get(KEY_ADMINS, {}) or {}


def get_threads(scope: str):
    refresh_core(force=False)
    if scope == "jarvis":
        return CORE_DATA.get(KEY_THREADS_JARVIS, {}) or {}
    if scope == "sparksign":
        return CORE_DATA.get(KEY_THREADS_SPARKSIGN, {}) or {}
    return {}


def get_logs():
    refresh_rt(force=False)
    v = RT_DATA.get(KEY_LOGS, [])
    return v if isinstance(v, list) else []


def get_link_settings_map():
    refresh_core(force=False)
    return CORE_DATA.get(KEY_LINK_SETTINGS, {}) or {}


def get_link_whitelist_map():
    refresh_core(force=False)
    return CORE_DATA.get(KEY_LINK_WHITELIST, {}) or {}


def get_link_violations_map():
    refresh_rt(force=False)
    return RT_DATA.get(KEY_LINK_VIOLATIONS, {}) or {}


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
        "added_time": _now_iso(),
        "is_super": False,
    }
    update_core(KEY_ADMINS, admins)
    return True


def remove_admin(admin_id: int, removed_by: int):
    admins = get_admins()
    s = str(admin_id)
    rb = str(removed_by)

    if s not in admins:
        return False, "❌ 該用戶不是管理員"
    if admins[s].get("is_super", False):
        return False, "❌ 無法移除此管理員"
    if rb not in admins:
        return False, "❌ 您沒有管理員權限"

    del admins[s]
    update_core(KEY_ADMINS, admins)
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
        update_core(KEY_THREADS_JARVIS, threads)
    else:
        update_core(KEY_THREADS_SPARKSIGN, threads)
    return True


# ================== Telegram API helpers ==================
def tg(method: str, payload: dict, timeout=10):
    try:
        return requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload, timeout=timeout)
    except Exception as e:
        print("tg err:", e)
        return None


def _prepare_reply_markup(markup):
    if isinstance(markup, str):
        return markup
    return json.dumps(markup, ensure_ascii=False)


def send_message(chat_id, text, markup=None, thread_id=None, parse_mode=None, entities=None, disable_preview=True):
    try:
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": bool(disable_preview)}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        if markup:
            payload["reply_markup"] = _prepare_reply_markup(markup)
        if entities:
            payload["entities"] = entities
        elif parse_mode:
            payload["parse_mode"] = parse_mode

        return tg("sendMessage", payload, timeout=8)
    except Exception as e:
        print(f"send_message err: {e}")
        return None


def edit_message_text(chat_id, message_id, text, markup=None, parse_mode=None, entities=None, disable_preview=True):
    payload = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text,
        "disable_web_page_preview": bool(disable_preview),
    }
    if markup:
        payload["reply_markup"] = _prepare_reply_markup(markup)
    if entities:
        payload["entities"] = entities
    elif parse_mode:
        payload["parse_mode"] = parse_mode
    return tg("editMessageText", payload, timeout=10)


def delete_message(chat_id, message_id):
    return tg("deleteMessage", {"chat_id": chat_id, "message_id": int(message_id)}, timeout=10)


def answer_callback(callback_id):
    try:
        tg("answerCallbackQuery", {"callback_query_id": callback_id}, timeout=5)
    except:
        pass


def get_user_info(user_id):
    try:
        r = tg("getChat", {"chat_id": user_id}, timeout=6)
        if r and r.status_code == 200:
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


def group_user_label(user_id: int) -> str:
    try:
        uinfo = get_user_info(int(user_id))
        return get_display_name(uinfo) if uinfo else "未知用戶"
    except:
        return "未知用戶"


def get_chat_info(chat_id):
    try:
        r = tg("getChat", {"chat_id": chat_id}, timeout=6)
        if r and r.status_code == 200:
            return r.json().get("result", {})
    except:
        pass
    return None


def get_thread_name(chat_id, thread_id):
    try:
        r = tg("getForumTopic", {"chat_id": chat_id, "message_thread_id": thread_id}, timeout=6)
        if r and r.status_code == 200:
            return r.json().get("result", {}).get("name", "未知話題")
    except:
        pass
    return "未知話題"


def get_chat_member_status(chat_id: int, user_id: int):
    r = tg("getChatMember", {"chat_id": chat_id, "user_id": user_id}, timeout=8)
    try:
        if r and r.status_code == 200:
            return (r.json().get("result", {}) or {}).get("status", "").lower()
    except:
        pass
    return None


def restrict_member(chat_id: int, user_id: int, until_ts: int):
    payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "until_date": int(until_ts),
        "permissions": {
            "can_send_messages": False,
            "can_send_audios": False,
            "can_send_documents": False,
            "can_send_photos": False,
            "can_send_videos": False,
            "can_send_video_notes": False,
            "can_send_voice_notes": False,
            "can_send_polls": False,
            "can_send_other_messages": False,
            "can_add_web_page_previews": False,
            "can_change_info": False,
            "can_invite_users": False,
            "can_pin_messages": False,
            "can_manage_topics": False,
        },
    }
    return tg("restrictChatMember", payload, timeout=10)


def ban_member(chat_id: int, user_id: int):
    return tg("banChatMember", {"chat_id": chat_id, "user_id": user_id}, timeout=10)


def kick_member_no_ban(chat_id: int, user_id: int):
    st = get_chat_member_status(chat_id, user_id)
    if st in ("administrator", "creator"):
        return False

    r1 = tg("banChatMember", {"chat_id": chat_id, "user_id": user_id}, timeout=10)
    ok1 = (r1 is not None and r1.status_code == 200)
    tg("unbanChatMember", {"chat_id": chat_id, "user_id": user_id}, timeout=10)
    return ok1


# ================== Logging (RT) ==================
def log_action(admin_id, action, target=None, details=None):
    logs = get_logs()

    admin_info = get_user_info(admin_id)
    admin_name = get_display_name(admin_info) if admin_info else str(admin_id)

    log_entry = {
        "timestamp": _now_iso(),
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
    if len(logs) > 200:
        logs = logs[-200:]

    update_rt(KEY_LOGS, logs)


# ================== Permissions ==================
def normalize_cmd(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    first = t.split()[0]
    return first.split("@")[0]


def should_process(update, user_id, text):
    if "message" not in update:
        return False

    chat_id = update["message"]["chat"]["id"]

    # Private chat always allowed
    if not str(chat_id).startswith("-100"):
        return True

    cmd = normalize_cmd(text)

    # Group admin commands always allowed
    admin_cmds = {
        "/admin_add_jarvis",
        "/admin_remove_jarvis",
        "/admin_add_sparksign",
        "/admin_remove_sparksign",
        "/admin_add_wl",
        "/admin_remove_wl",
    }
    if is_admin(user_id) and cmd in admin_cmds:
        return True

    # Normal functions require Jarvis-allowed thread
    thread_id = update["message"].get("message_thread_id", 0)
    return f"{chat_id}_{thread_id}" in get_threads("jarvis")


# ================== Commands / UI ==================
VOTE_LINKS = [
    ("𝘿𝙚𝙭𝙎𝙘𝙧𝙚𝙚𝙣𝙚𝙧", "https://dexscreener.com/solana/83qieesqnkd3hkymd87rbfnamtthfvbumwvvgvkdtz5w"),
    ("𝙂𝙚𝙘𝙠𝙤𝙏𝙚𝙧𝙢𝙞𝙣𝙖𝙡", "https://www.geckoterminal.com/solana/pools/83QiEeSqNKd3HkYMd87rbfnaMTThfvBUmwVVGvKdtZ5W?utm_source=coingecko&utm_medium=referral&utm_campaign=searchresults"),
    ("𝘽𝙞𝙩𝙜𝙚𝙩𝙎𝙬𝙖𝙥", "https://web3.bitget.com/zh-TC/swap/sol/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump"),
    ("𝙆𝙪𝘾𝙤𝙞𝙣𝙒𝙚𝙗𝟯", "https://www.kucoin.com/zh-hant/web3/swap?inputCurrency=2514&outputCurrency=6783142"),
    ("𝙇𝙞𝙫𝙚𝘾𝙤𝙞𝙣𝙒𝙖𝙩𝙘𝙝", "https://www.livecoinwatch.com/price/10KDOG-10KDOG"),
    ("𝘾𝙤𝙞𝙣𝙎𝙣𝙞𝙥𝙚𝙧", "https://coinsniper.net/coin/87574"),
    ("𝙏𝙤𝙥𝟭𝟬𝟬𝙏𝙤𝙠𝙚𝙣", "https://top100token.com/solana/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump"),
    ("𝘾𝙤𝙞𝙣𝘾𝙖𝙩𝙖𝙥𝙪𝙡𝙩", "https://coincatapult.com/coin/10k-dog-10k-dog"),
    ("𝘾𝙤𝙞𝙣𝙎𝙘𝙤𝙥𝙚", "https://www.coinscope.co/coin/10k-dog"),
    ("𝘾𝙤𝙞𝙣𝘽𝙤𝙤𝙢", "https://coinboom.net/coin/10k-dog"),
    ("𝙁𝙧𝙚𝙨𝙝𝘾𝙤𝙞𝙣𝙨", "https://www.freshcoins.io/coins/10k-dog"),
]

SOCIAL_MEDIA_LINKS = [
    ("𝙓", "https://x.com/10Kdogcoin"),
    ("𝙏𝙝𝙧𝙚𝙖𝙙𝙨", "https://www.threads.com/@_10kdog_"),
    ("𝙄𝙂", "https://www.instagram.com/_10kdog_/"),
    ("𝘿𝙞𝙨𝙘𝙤𝙧𝙙", "https://discord.gg/10kdog"),
    ("𝙔𝙤𝙪𝙏𝙪𝙗𝙚主頻道", "https://www.youtube.com/@10KDOGGOES1"),
    ("𝙔𝙤𝙪𝙏𝙪𝙗𝙚交易教學", "https://www.youtube.com/@10KTrading-z2k"),
    ("𝙊𝙙𝙮𝙨𝙚𝙚", "https://odysee.com/@10KDOGGOES1:e"),
]


def build_generic_keyboard(links_list, cols=2):
    rows = []
    for i in range(0, len(links_list), cols):
        chunk = links_list[i : i + cols]
        rows.append([{"text": label, "url": url} for label, url in chunk])
    return {"inline_keyboard": rows}


COMMANDS = {
    "ca": "C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "https://10kcoin.com/",
    "announcements": "https://t.me/tenkdogcrypto",
    "rules": "https://t.me/tenkdogcrypto/71",
    "jup_lock": "https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "https://t.me/tenkdogcrypto/72",
    "invitation_code": "https://t.me/tenkdogcrypto/122",
    "vote": {"text": "每日投票衝熱度的網站", "markup": build_generic_keyboard(VOTE_LINKS, 3)},
    "social_media": {"text": "官方社媒", "markup": build_generic_keyboard(SOCIAL_MEDIA_LINKS, 2)},
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
/vote - 🗳️ 每日投票衝熱度的網站
/social_media - 📌官方社媒
/linktree - ➡️ 前往linktree

以下爲管理員指令：
🛠 群組話題授權：
/admin_add_jarvis - 允許當前話題
/admin_remove_jarvis - 移除當前話題

✨ SparkSign 話題授權：
/admin_add_sparksign - 允許當前話題
/admin_remove_sparksign - 移除當前話題

🔗 白名單（群組內由管理員使用，需回覆目標用戶訊息）：
/admin_add_wl - 加入白名單
/admin_remove_wl - 移除白名單"""


def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📜 合約地址", "callback_data": "ca"}],
            [{"text": "🌐 官網網站", "callback_data": "web"}, {"text": "📌 官方社媒", "callback_data": "social_media"}, {"text": "➡️ 前往linktree", "callback_data": "linktree"}],
            [{"text": "📣 社群公告", "callback_data": "announcements"}, {"text": "📑 社群規範", "callback_data": "rules"}, {"text": "🗣️ 精神標語", "callback_data": "slogan"}],
            [{"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"}, {"text": "🔗 註冊連結", "callback_data": "invitation_code"}, {"text": "💲 購買教學", "callback_data": "buy"}],
            [{"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"}, {"text": "🗳️ 每日投票", "callback_data": "vote"}],
            [{"text": "📋 指令清單", "callback_data": "help"}],
        ]
    }


# ================== Link moderation ==================
LINK_REGEX = re.compile(r"(https?://|www\.|t\.me/|bit\.ly/|tinyurl\.com/|discord\.gg/)", re.I)


def msg_has_link(msg: dict) -> bool:
    if not isinstance(msg, dict):
        return False

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if text and LINK_REGEX.search(text):
        return True

    for key in ("entities", "caption_entities"):
        ents = msg.get(key) or []
        if not isinstance(ents, list):
            continue
        for e in ents:
            t = (e.get("type") or "").lower()
            if t in ("url", "text_link"):
                return True
    return False


def _chat_key(chat_id: int) -> str:
    return str(int(chat_id))


def get_link_settings(chat_id: int) -> dict:
    s_map = get_link_settings_map()
    ck = _chat_key(chat_id)
    s = s_map.get(ck) or {}
    if "enabled" not in s:
        s["enabled"] = True
    if "mute_days" not in s:
        s["mute_days"] = 1
    if s.get("third_action") not in ("kick", "ban"):
        s["third_action"] = "kick"
    return s


def set_link_settings(chat_id: int, new_s: dict):
    s_map = get_link_settings_map()
    ck = _chat_key(chat_id)
    s_map[ck] = {
        "enabled": bool(new_s.get("enabled", True)),
        "mute_days": int(new_s.get("mute_days", 1) or 1),
        "third_action": "ban" if new_s.get("third_action") == "ban" else "kick",
    }
    update_core(KEY_LINK_SETTINGS, s_map)


def is_whitelisted(chat_id: int, user_id: int) -> bool:
    wl = get_link_whitelist_map()
    ck = _chat_key(chat_id)
    return str(int(user_id)) in (wl.get(ck) or {})


def whitelist_add(chat_id: int, user_id: int, added_by: int) -> bool:
    wl = get_link_whitelist_map()
    ck = _chat_key(chat_id)
    wl.setdefault(ck, {})
    uid = str(int(user_id))
    if uid in wl[ck]:
        return False
    wl[ck][uid] = {"added_by": int(added_by), "added_time": _now_iso()}
    update_core(KEY_LINK_WHITELIST, wl)
    return True


def whitelist_remove(chat_id: int, user_id: int) -> bool:
    wl = get_link_whitelist_map()
    ck = _chat_key(chat_id)
    uid = str(int(user_id))
    if uid not in (wl.get(ck) or {}):
        return False
    wl[ck].pop(uid, None)
    if not wl[ck]:
        wl.pop(ck, None)
    update_core(KEY_LINK_WHITELIST, wl)
    return True


def get_violation_count(chat_id: int, user_id: int) -> int:
    vio = get_link_violations_map()
    ck = _chat_key(chat_id)
    uid = str(int(user_id))
    rec = (vio.get(ck) or {}).get(uid) or {}
    try:
        return int(rec.get("count", 0) or 0)
    except:
        return 0


def inc_violation(chat_id: int, user_id: int) -> int:
    vio = get_link_violations_map()
    ck = _chat_key(chat_id)
    uid = str(int(user_id))
    vio.setdefault(ck, {})
    rec = vio[ck].get(uid) or {}
    c = int(rec.get("count", 0) or 0) + 1
    vio[ck][uid] = {"count": c, "last_time": _now_iso()}
    update_rt(KEY_LINK_VIOLATIONS, vio)
    return c


def clear_violation(chat_id: int, user_id: int):
    vio = get_link_violations_map()
    ck = _chat_key(chat_id)
    uid = str(int(user_id))
    removed = False
    if uid in (vio.get(ck) or {}):
        vio[ck].pop(uid, None)
        if not vio[ck]:
            vio.pop(ck, None)
        update_rt(KEY_LINK_VIOLATIONS, vio)
        removed = True
    return removed


def list_violations_text(chat_id: int, limit: int = 50) -> str:
    vio = get_link_violations_map()
    ck = _chat_key(chat_id)
    m = vio.get(ck) or {}
    if not m:
        return "📌 目前沒有違規名單"

    items = []
    for uid, rec in m.items():
        try:
            items.append((int(rec.get("count", 0) or 0), str(rec.get("last_time", "")), uid))
        except:
            continue
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    items = items[: max(1, int(limit))]

    lines = ["📌 違規名單（連結違規）\n"]
    for c, t, uid in items:
        name = ""
        try:
            uinfo = get_user_info(int(uid))
            name = get_display_name(uinfo) if uinfo else ""
        except:
            name = ""
        if name:
            lines.append(f"• {name}\n  🔢 UID: {uid} | 次數: {c} | ⏰ {t}")
        else:
            lines.append(f"• 🔢 UID: {uid} | 次數: {c} | ⏰ {t}")
    return "\n".join(lines)


def whitelist_text(chat_id: int, limit: int = 60) -> str:
    wl = get_link_whitelist_map()
    ck = _chat_key(chat_id)
    m = wl.get(ck) or {}
    if not m:
        return "✅ 目前白名單為空"

    items = []
    for uid, rec in m.items():
        items.append((str(rec.get("added_time", "")), uid, rec))
    items.sort(key=lambda x: x[0], reverse=True)
    items = items[: max(1, int(limit))]

    lines = ["✅ 白名單成員\n"]
    for added_time, uid, rec in items:
        name = ""
        adder = ""
        try:
            uinfo = get_user_info(int(uid))
            name = get_display_name(uinfo) if uinfo else ""
        except:
            name = ""
        try:
            adder_info = get_user_info(int(rec.get("added_by", 0)))
            adder = get_display_name(adder_info) if adder_info else ""
        except:
            adder = ""

        if name:
            lines.append(
                f"• {name}\n"
                f"  🔢 UID: {uid}\n"
                f"  👤 加入者: {adder or rec.get('added_by', '')}\n"
                f"  ⏰ {added_time}"
            )
        else:
            lines.append(
                f"• 🔢 UID: {uid}\n"
                f"  👤 加入者: {adder or rec.get('added_by', '')}\n"
                f"  ⏰ {added_time}"
            )
    return "\n\n".join(lines)


def should_bypass_link_rule(chat_id: int, user_id: int) -> bool:
    if is_admin(user_id):
        return True
    if is_whitelisted(chat_id, user_id):
        return True
    st = get_chat_member_status(chat_id, user_id)
    if st in ("administrator", "creator"):
        return True
    return False


def apply_link_moderation(msg: dict) -> bool:
    """
    群組內處置：一律不顯 UID
    """
    try:
        chat_id = int(msg["chat"]["id"])
        user_id = int((msg.get("from") or {}).get("id"))
        if not user_id:
            return False

        if not str(chat_id).startswith("-100"):
            return False

        settings = get_link_settings(chat_id)
        if not settings.get("enabled", True):
            return False

        if not msg_has_link(msg):
            return False

        if should_bypass_link_rule(chat_id, user_id):
            return False

        try:
            delete_message(chat_id, msg.get("message_id"))
        except:
            pass

        offender = group_user_label(user_id)
        count = inc_violation(chat_id, user_id)
        thread_id = msg.get("message_thread_id", None)

        if count == 1:
            send_message(
                chat_id,
                "⚠️ 連結違規（第 1 次）\n\n"
                f"• 用戶：{offender}\n"
                "• 處置：警告\n"
                "• 提醒：未加入白名單前請勿發送連結",
                thread_id=thread_id
            )
            return True

        if count == 2:
            mute_days = int(settings.get("mute_days", 1) or 1)
            until_ts = int(_now()) + mute_days * 86400
            restrict_member(chat_id, user_id, until_ts=until_ts)
            send_message(
                chat_id,
                "🔇 連結違規（第 2 次）\n\n"
                f"• 用戶：{offender}\n"
                f"• 處置：禁言 {mute_days} 天\n"
                "• 提醒：未加入白名單前請勿發送連結",
                thread_id=thread_id
            )
            return True

        action = settings.get("third_action", "kick")
        if action == "ban":
            ban_member(chat_id, user_id)
            action_text = "封鎖"
        else:
            kick_member_no_ban(chat_id, user_id)
            action_text = "踢出群組"

        send_message(
            chat_id,
            "⛔ 連結違規（第 3 次）\n\n"
            f"• 用戶：{offender}\n"
            f"• 處置：{action_text}\n"
            "• 提醒：未加入白名單前請勿發送連結",
            thread_id=thread_id
        )

        clear_violation(chat_id, user_id)
        return True

    except Exception as e:
        print("[LINK_MOD_ERR]", e)
        return False


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
            msg += f"👤 管理員 - {name}\n🔢 ID: {admin_id}\n\n"
        except:
            msg += f"👤 管理員 - 未知用戶\n🔢 ID: {admin_id}\n\n"
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


# ================== Admin UI: sessions / lock / panels ==================
SESS = {}  # { user_id: {waiting_for, expires, return_panel, active_panel_mid, active_chat_id} }
SESSION_TTL = 180

ACTIVE_SETTING = {"user_id": None, "expires": 0}
SETTING_LOCK_TTL = 180


def _get_sess(user_id: int):
    s = SESS.get(user_id)
    if not s:
        s = {"waiting_for": None, "expires": 0, "return_panel": None, "active_panel_mid": None, "active_chat_id": None}
        SESS[user_id] = s

    if s.get("expires", 0) and _now() > s["expires"]:
        s["waiting_for"] = None
        s["expires"] = 0
        s["return_panel"] = None
    return s


def set_wait(user_id: int, key: str, return_panel: str):
    s = _get_sess(user_id)
    s["waiting_for"] = key
    s["return_panel"] = return_panel
    s["expires"] = _now() + SESSION_TTL


def clear_wait(user_id: int):
    s = _get_sess(user_id)
    s["waiting_for"] = None
    s["return_panel"] = None
    s["expires"] = 0


def _lock_expired() -> bool:
    return ACTIVE_SETTING["expires"] <= _now()


def try_acquire_setting_lock(user_id: int) -> bool:
    if ACTIVE_SETTING["user_id"] is None or _lock_expired():
        ACTIVE_SETTING["user_id"] = user_id
        ACTIVE_SETTING["expires"] = _now() + SETTING_LOCK_TTL
        return True
    return ACTIVE_SETTING["user_id"] == user_id


def refresh_setting_lock(user_id: int):
    if ACTIVE_SETTING["user_id"] == user_id:
        ACTIVE_SETTING["expires"] = _now() + SETTING_LOCK_TTL


def release_setting_lock(user_id: int):
    if ACTIVE_SETTING["user_id"] == user_id:
        ACTIVE_SETTING["user_id"] = None
        ACTIVE_SETTING["expires"] = 0


def disable_panel(chat_id: int, mid: int, reason: str = "已完成設定"):
    edit_message_text(
        chat_id,
        mid,
        f"✅ {reason}\n\n此面板已關閉，請使用最新面板操作。",
        disable_preview=True
    )


MAX_PANEL_TEXT = 3800


def _safe_text(s: str) -> str:
    s = s or ""
    if len(s) <= MAX_PANEL_TEXT:
        return s
    return s[:MAX_PANEL_TEXT] + "\n\n…（內容過長已截斷）"


def sub_panel_markup(back_cb: str):
    return {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": back_cb}]]}


def show_subpanel(chat_id: int, mid: int, title: str, body: str, back_cb: str):
    text = f"{title}\n\n{_safe_text(body)}"
    send_or_edit_panel(chat_id, mid, text, sub_panel_markup(back_cb))


def _managed_chat_ids():
    ids = set()

    for k in get_threads("jarvis").keys():
        try:
            c, _ = k.split("_", 1)
            ids.add(int(c))
        except:
            pass
    for k in get_threads("sparksign").keys():
        try:
            c, _ = k.split("_", 1)
            ids.add(int(c))
        except:
            pass

    for ck in get_link_settings_map().keys():
        try:
            ids.add(int(ck))
        except:
            pass
    for ck in get_link_whitelist_map().keys():
        try:
            ids.add(int(ck))
        except:
            pass
    for ck in get_link_violations_map().keys():
        try:
            ids.add(int(ck))
        except:
            pass

    ids = {i for i in ids if str(i).startswith("-100")}
    return sorted(list(ids))


def _chat_title(chat_id: int) -> str:
    if not chat_id:
        return "（未選擇群組）"
    info = get_chat_info(chat_id)
    return (info.get("title") if info else None) or str(chat_id)


def _pick_default_chat_id(chats: list) -> int:
    prefer_keywords = ["10k", "萬倍", "金狗", "dog"]
    scored = []
    for cid in chats:
        title = (_chat_title(cid) or "").lower()
        score = sum(1 for kw in prefer_keywords if kw in title)
        scored.append((score, cid))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return int(scored[0][1]) if scored else 0


def _get_active_chat_id(user_id: int) -> int:
    s = _get_sess(user_id)
    if s.get("active_chat_id"):
        return int(s["active_chat_id"])
    chats = _managed_chat_ids()
    if chats:
        s["active_chat_id"] = _pick_default_chat_id(chats)
        return int(s["active_chat_id"])
    return 0


def admin_main_panel():
    return {"inline_keyboard": [
        [{"text": "👑 管理員設定", "callback_data": "p_admin"}],
        [{"text": "🛠️ 群組設定", "callback_data": "p_group"}],
        [{"text": "📊 操作紀錄", "callback_data": "p_logs"}],
    ]}


def admin_admin_panel(user_id: int):
    kb = [
        [{"text": "➕ 新增管理員", "callback_data": "a_add"}, {"text": "❌ 移除管理員", "callback_data": "a_remove"}],
        [{"text": "🔍 查詢TG UID", "callback_data": "a_query_uid"}, {"text": "👥 管理員列表", "callback_data": "a_list"}],
        [{"text": "🔙 返回", "callback_data": "p_main"}],
    ]
    return {"inline_keyboard": kb}


def admin_group_panel(user_id: int):
    chat_id = _get_active_chat_id(user_id)
    title = _chat_title(chat_id)
    s = get_link_settings(chat_id) if chat_id else {"enabled": False, "mute_days": 1, "third_action": "kick"}
    enabled = "✅" if s.get("enabled") else "❌"
    third = "KICK" if s.get("third_action") == "kick" else "BAN"
    mute_days = int(s.get("mute_days", 1) or 1)

    kb = []
    kb.append([{"text": f"🏷️ 目前群組：{title}", "callback_data": "g_chat_select"}])

    kb.append([
        {"text": f"🔗 連結：{enabled}", "callback_data": "g_toggle_link"},
        {"text": f"🔇 禁言：{mute_days}天", "callback_data": "g_set_mute_days"},
    ])
    kb.append([
        {"text": f"👢 第三次：{third}", "callback_data": "g_toggle_third"},
        {"text": "📌 違規名單", "callback_data": "g_vio_list"},
        {"text": "🧹 移除違規", "callback_data": "g_vio_remove"},
    ])
    kb.append([
        {"text": "✅ 白名單", "callback_data": "g_wl_list"},
        {"text": "➕ 加白名單", "callback_data": "g_wl_add"},
    ])
    kb.append([
        {"text": "❌ 移白名單", "callback_data": "g_wl_remove"},
        {"text": "🛠️ 指令說明", "callback_data": "g_help"},
    ])
    kb.append([
        {"text": "📋 Jarvis 話題", "callback_data": "g_threads_jarvis"},
        {"text": "✨ SparkSign 話題", "callback_data": "g_threads_sparksign"},
    ])

    kb.append([{"text": "🔙 返回", "callback_data": "p_main"}])
    return {"inline_keyboard": kb}


def chat_select_panel(user_id: int):
    chats = _managed_chat_ids()
    if not chats:
        return {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "p_group"}]]}

    rows = []
    for cid in chats[:12]:
        rows.append([{"text": _chat_title(cid), "callback_data": f"g_chat_set:{cid}"}])
    rows.append([{"text": "🔙 返回", "callback_data": "p_group"}])
    return {"inline_keyboard": rows}


def send_or_edit_panel(chat_id: int, mid: int, text: str, markup: dict):
    edit_message_text(chat_id, mid, text, markup=markup, disable_preview=True)


def send_command_response(chat_id, payload, thread_id=None):
    if isinstance(payload, dict):
        return send_message(
            chat_id,
            payload.get("text", ""),
            payload.get("markup"),
            thread_id,
            parse_mode=payload.get("parse_mode"),
            entities=payload.get("entities"),
        )
    return send_message(chat_id, payload, None, thread_id)


# ================== Handlers ==================
def handle_uid_query(update, chat_id):
    msg = (update or {}).get("message") or {}
    fwd = msg.get("forward_from")
    if not fwd:
        send_message(
            chat_id,
            "❌ 查詢不到 UID。\n\n"
            "常見原因：對方開啟「轉發訊息隱私」，Telegram 不會提供 forward_from。\n\n"
            "替代方式：\n"
            "1) 請對方私訊我任意一句話（我可直接取得 UID）\n"
            "2) 群組內：回覆對方訊息後輸入 /admin_add_wl 或 /admin_remove_wl"
        )
        return

    try:
        name = f"{fwd.get('first_name', '')} {fwd.get('last_name', '')}".strip() or "未知"
        username = f"@{fwd.get('username')}" if fwd.get("username") else "未設定"

        text = f"""🔍 用戶 UID 查詢結果

👤 姓名：{name}
🔢 UID：{fwd['id']}
📧 用戶名：{username}"""

        markup = {
            "inline_keyboard": [
                [{"text": "📋 複製UID", "callback_data": f"copy_{fwd['id']}"}],
                [{"text": "➕ 新增此用戶為管理員", "callback_data": f"add_{fwd['id']}"}],
                [{"text": "✅ 加入白名單", "callback_data": f"wladd_{fwd['id']}"}],
                [{"text": "❌ 移除白名單", "callback_data": f"wlrm_{fwd['id']}"}],
                [{"text": "🔙 返回", "callback_data": "p_admin"}],
            ]
        }
        send_message(chat_id, text, markup)
    except Exception:
        send_message(chat_id, "❌ 查詢失敗（訊息格式或 Telegram 限制）")


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
        res = send_message(chat_id, "👑 Jarvis 管理員控制面板", admin_main_panel())
        try:
            mid = res.json()["result"]["message_id"] if res and res.status_code == 200 else None
            _get_sess(user_id)["active_panel_mid"] = mid
        except:
            pass


def _delete_group_admin_cmd(chat_id: int, update: dict):
    try:
        mid = int(((update or {}).get("message") or {}).get("message_id"))
        if mid:
            delete_message(chat_id, mid)
    except:
        pass


def handle_group_admin(text, chat_id, user_id, update):
    cmd = normalize_cmd(text)
    thread_id = (update.get("message") or {}).get("message_thread_id", 0)
    admin_name = group_user_label(user_id)

    _delete_group_admin_cmd(chat_id, update)

    if cmd == "/admin_add_jarvis":
        if toggle_thread(chat_id, thread_id, True, "jarvis"):
            send_message(chat_id, "✅ 已允許當前話題（Jarvis）", thread_id=thread_id)
            log_action(user_id, "add_thread_jarvis", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 操作失敗", thread_id=thread_id)
        return

    if cmd == "/admin_remove_jarvis":
        if toggle_thread(chat_id, thread_id, False, "jarvis"):
            send_message(chat_id, "✅ 已移除話題權限（Jarvis）", thread_id=thread_id)
            log_action(user_id, "remove_thread_jarvis", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 此話題未被允許（Jarvis）", thread_id=thread_id)
        return

    if cmd == "/admin_add_sparksign":
        if toggle_thread(chat_id, thread_id, True, "sparksign"):
            send_message(chat_id, "✅ 已允許當前話題（SparkSign）", thread_id=thread_id)
            log_action(user_id, "add_thread_sparksign", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 操作失敗", thread_id=thread_id)
        return

    if cmd == "/admin_remove_sparksign":
        if toggle_thread(chat_id, thread_id, False, "sparksign"):
            send_message(chat_id, "✅ 已移除話題權限（SparkSign）", thread_id=thread_id)
            log_action(user_id, "remove_thread_sparksign", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 此話題未被允許（SparkSign）", thread_id=thread_id)
        return

    if cmd == "/admin_add_wl":
        rep = (update.get("message") or {}).get("reply_to_message") or {}
        target = (rep.get("from") or {}).get("id")
        if not target:
            send_message(
                chat_id,
                "❌ 白名單加入失敗\n\n"
                "請先「回覆」目標用戶的訊息\n"
                "再輸入：\n"
                "• /admin_add_wl",
                thread_id=thread_id
            )
            return

        target_name = group_user_label(int(target))
        ok = whitelist_add(chat_id, int(target), int(user_id))
        if ok:
            send_message(
                chat_id,
                "✅ 已加入白名單\n\n"
                f"• 用戶：{target_name}\n"
                f"• 操作者：{admin_name}",
                thread_id=thread_id
            )
            log_action(user_id, "wl_add", target=int(target), details={"chat_id": int(chat_id)})
        else:
            send_message(
                chat_id,
                "⚠️ 白名單已存在\n\n"
                f"• 用戶：{target_name}",
                thread_id=thread_id
            )
        return

    if cmd == "/admin_remove_wl":
        rep = (update.get("message") or {}).get("reply_to_message") or {}
        target = (rep.get("from") or {}).get("id")
        if not target:
            send_message(
                chat_id,
                "❌ 白名單移除失敗\n\n"
                "請先「回覆」目標用戶的訊息\n"
                "再輸入：\n"
                "• /admin_remove_wl",
                thread_id=thread_id
            )
            return

        target_name = group_user_label(int(target))
        ok = whitelist_remove(chat_id, int(target))
        if ok:
            send_message(
                chat_id,
                "✅ 已移除白名單\n\n"
                f"• 用戶：{target_name}\n"
                f"• 操作者：{admin_name}",
                thread_id=thread_id
            )
            log_action(user_id, "wl_remove", target=int(target), details={"chat_id": int(chat_id)})
        else:
            send_message(
                chat_id,
                "⚠️ 白名單不存在\n\n"
                f"• 用戶：{target_name}",
                thread_id=thread_id
            )
        return


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
            send_command_response(chat_id, COMMANDS[cmd], thread_id)


def handle_callback(data_cb, chat_id, user_id, message_thread_id=None):
    is_private = not str(chat_id).startswith("-100")

    # Group callbacks
    if not is_private:
        thread_key = f"{chat_id}_{message_thread_id or 0}"
        if thread_key not in get_threads("jarvis") and data_cb not in ("main_menu", "help"):
            send_message(chat_id, "❌ 此話題未啟用 Jarvis 功能", None, message_thread_id)
            return

        if data_cb in COMMANDS:
            send_command_response(chat_id, COMMANDS[data_cb], message_thread_id)
        elif data_cb == "help":
            send_message(chat_id, HELP_TEXT, None, message_thread_id)
        elif data_cb == "main_menu":
            send_message(chat_id, "🤖 10K DOG - Jarvis", main_menu(), message_thread_id)
        return

    # Private callbacks: admin-only
    if not is_admin(int(user_id)):
        send_message(int(chat_id), "❌ 您沒有管理員權限")
        return

    s = _get_sess(int(user_id))
    mid = s.get("active_panel_mid")
    if not mid:
        return

    # navigation
    if data_cb == "p_main":
        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        send_or_edit_panel(chat_id, mid, "👑 Jarvis 管理員控制面板", admin_main_panel())
        return

    if data_cb == "p_admin":
        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        send_or_edit_panel(chat_id, mid, "👑 管理員設定", admin_admin_panel(int(user_id)))
        return

    if data_cb == "p_group":
        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        send_or_edit_panel(chat_id, mid, "🛠️ 群組設定", admin_group_panel(int(user_id)))
        return

    # submenu: logs
    if data_cb == "p_logs":
        logs = (get_logs() or [])[-12:]
        if not logs:
            show_subpanel(chat_id, mid, "📊 操作紀錄", "目前沒有操作紀錄", "p_main")
        else:
            msg = "📊 最近操作紀錄：\n\n"
            for log in reversed(logs):
                try:
                    t = datetime.datetime.fromisoformat(log["timestamp"]).strftime("%m/%d %H:%M")
                except:
                    t = log.get("timestamp", "")
                admin_name = log.get("admin_name", log.get("admin_id"))
                action = log.get("action")
                details = log.get("details")
                line = f"⏰ {t} | 👤 {admin_name} | {action}"
                if details:
                    line += f" | {details}"
                msg += line + "\n"
            show_subpanel(chat_id, mid, "📊 操作紀錄", msg, "p_main")
        return

    # ---- Admin Settings actions ----
    if data_cb == "a_list":
        show_subpanel(chat_id, mid, "👥 管理員列表", get_admin_list_with_names(), "p_admin")
        return

    if data_cb == "a_query_uid":
        send_message(chat_id, "🔍 請轉發用戶訊息給我查詢 UID")
        return

    if data_cb == "a_add":
        if not is_super_admin(int(user_id)):
            send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
            return
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "admin_add_uid", "p_admin")
        send_message(chat_id, "➕ 請直接輸入要新增的用戶 UID 數字")
        return

    if data_cb == "a_remove":
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "admin_remove_uid", "p_admin")
        send_message(chat_id, "❌ 請直接輸入要移除的用戶 UID 數字")
        return

    # ---- Group Settings actions ----
    if data_cb == "g_chat_select":
        send_or_edit_panel(chat_id, mid, "🏷️ 選擇群組", chat_select_panel(int(user_id)))
        return

    if data_cb.startswith("g_chat_set:"):
        try:
            cid = int(data_cb.split(":", 1)[1])
            _get_sess(int(user_id))["active_chat_id"] = cid
            send_or_edit_panel(chat_id, mid, "🛠️ 群組設定", admin_group_panel(int(user_id)))
        except:
            pass
        return

    if data_cb == "g_toggle_link":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組")
            return
        conf = get_link_settings(cid)
        conf["enabled"] = not bool(conf.get("enabled", True))
        set_link_settings(cid, conf)
        log_action(int(user_id), "link_toggle_enabled", details={"chat_id": cid, "enabled": conf["enabled"]})
        send_or_edit_panel(chat_id, mid, "🛠️ 群組設定", admin_group_panel(int(user_id)))
        return

    if data_cb == "g_toggle_third":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組")
            return
        conf = get_link_settings(cid)
        conf["third_action"] = "ban" if conf.get("third_action") == "kick" else "kick"
        set_link_settings(cid, conf)
        log_action(int(user_id), "link_toggle_third", details={"chat_id": cid, "third_action": conf["third_action"]})
        send_or_edit_panel(chat_id, mid, "🛠️ 群組設定", admin_group_panel(int(user_id)))
        return

    if data_cb == "g_set_mute_days":
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "mute_days", "p_group")
        send_message(chat_id, "🔇 請輸入「第二次違規」禁言天數（整數，例如 1 / 3 / 7）")
        return

    if data_cb == "g_wl_list":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            show_subpanel(chat_id, mid, "✅ 白名單列表", "❌ 尚未選擇群組", "p_group")
            return
        show_subpanel(chat_id, mid, "✅ 白名單列表", whitelist_text(cid), "p_group")
        return

    if data_cb == "g_vio_list":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            show_subpanel(chat_id, mid, "📌 違規名單列表", "❌ 尚未選擇群組", "p_group")
            return
        show_subpanel(chat_id, mid, "📌 違規名單列表", list_violations_text(cid), "p_group")
        return

    if data_cb == "g_vio_remove":
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "vio_remove_uid", "p_group")
        send_message(chat_id, "🧹 請輸入要從違規名單移除的 UID（數字）")
        return

    if data_cb == "g_wl_add":
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "wl_add_uid", "p_group")
        send_message(chat_id, "➕ 請輸入要加入白名單的 UID（數字）")
        return

    if data_cb == "g_wl_remove":
        if not try_acquire_setting_lock(int(user_id)):
            holder = ACTIVE_SETTING["user_id"]
            send_message(chat_id, f"⛔ 目前有其他管理員正在設定（UID: {holder}），請稍後再試。")
            return
        refresh_setting_lock(int(user_id))
        set_wait(int(user_id), "wl_remove_uid", "p_group")
        send_message(chat_id, "❌ 請輸入要移除白名單的 UID（數字）")
        return

    if data_cb == "g_threads_jarvis":
        show_subpanel(chat_id, mid, "📋 Jarvis 話題列表", get_thread_list_with_names("jarvis"), "p_group")
        return

    if data_cb == "g_threads_sparksign":
        show_subpanel(chat_id, mid, "✨ SparkSign 話題列表", get_thread_list_with_names("sparksign"), "p_group")
        return

    if data_cb == "g_help":
        show_subpanel(
            chat_id,
            mid,
            "🛠️ 群組設定說明",
            "1) 先用「🏷️ 目前群組」選擇要管理的群組\n"
            "2) 🔗 連結：開/關 連結違規處置\n"
            "3) 🔇 禁言：設定第 2 次違規的禁言天數\n"
            "4) 👢 第三次：切換第 3 次違規處置（踢出/封鎖）\n"
            "5) ✅ 白名單：可用面板輸入 UID 加/移白名單；群組內也可回覆訊息用 /admin_add_wl\n"
            "6) 📌 違規名單：查看/移除（輸入 UID）\n",
            "p_group",
        )
        return

    # ---- UID query quick actions ----
    if data_cb.startswith("copy_"):
        try:
            uid = int(data_cb.split("_", 1)[1])
            send_message(chat_id, f"✅ UID：<code>{uid}</code>", parse_mode="HTML", disable_preview=True)
        except:
            pass
        return

    if data_cb.startswith("add_"):
        try:
            uid = int(data_cb.split("_", 1)[1])
            if not is_super_admin(int(user_id)):
                send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
                return
            if add_admin(uid, int(user_id)):
                send_message(chat_id, f"✅ 已新增管理員：{uid}")
                log_action(int(user_id), "add_admin", target=uid)
            else:
                send_message(chat_id, f"⚠️ 該用戶已是管理員：{uid}")
        except:
            pass
        return

    if data_cb.startswith("wladd_"):
        try:
            uid = int(data_cb.split("_", 1)[1])
            cid = _get_active_chat_id(int(user_id))
            if not cid:
                send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
                return
            ok = whitelist_add(cid, uid, int(user_id))
            if ok:
                send_message(chat_id, f"✅ 已加入白名單：{uid}\n群組：{_chat_title(cid)}")
                log_action(int(user_id), "wl_add", target=uid, details={"chat_id": cid})
            else:
                send_message(chat_id, f"⚠️ 白名單已存在：{uid}")
        except:
            pass
        return

    if data_cb.startswith("wlrm_"):
        try:
            uid = int(data_cb.split("_", 1)[1])
            cid = _get_active_chat_id(int(user_id))
            if not cid:
                send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
                return
            ok = whitelist_remove(cid, uid)
            if ok:
                send_message(chat_id, f"✅ 已移除白名單：{uid}\n群組：{_chat_title(cid)}")
                log_action(int(user_id), "wl_remove", target=uid, details={"chat_id": cid})
            else:
                send_message(chat_id, f"⚠️ 白名單不存在：{uid}")
        except:
            pass
        return

    # unknown callback
    return


# ================== Private text input (panel waiting_for) ==================
def handle_private_waiting_text(chat_id: int, user_id: int, text: str):
    s = _get_sess(int(user_id))
    state = s.get("waiting_for")
    if not state:
        return False

    refresh_setting_lock(int(user_id))

    # ---- admin add/remove by uid ----
    if state == "admin_add_uid":
        if not is_super_admin(int(user_id)):
            send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
            clear_wait(int(user_id))
            release_setting_lock(int(user_id))
            return True
        try:
            uid = int(text.strip())
            if add_admin(uid, int(user_id)):
                send_message(chat_id, f"✅ 已新增管理員：{uid}")
                log_action(int(user_id), "add_admin", target=uid)
            else:
                send_message(chat_id, f"⚠️ 該用戶已是管理員：{uid}")
        except:
            send_message(chat_id, "❌ 請輸入有效的 UID 數字")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        # keep panel as-is; admin can press buttons again
        return True

    if state == "admin_remove_uid":
        try:
            uid = int(text.strip())
            ok, msg = remove_admin(uid, int(user_id))
            send_message(chat_id, msg)
            if ok:
                log_action(int(user_id), "remove_admin", target=uid)
        except:
            send_message(chat_id, "❌ 請輸入有效的 UID 數字")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        return True

    # ---- group settings: mute days ----
    if state == "mute_days":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
            clear_wait(int(user_id))
            release_setting_lock(int(user_id))
            return True
        try:
            v = int(float(text.strip()))
            if v <= 0:
                v = 1
            conf = get_link_settings(cid)
            conf["mute_days"] = v
            set_link_settings(cid, conf)
            send_message(chat_id, f"✅ 已設定禁言天數：{v} 天\n群組：{_chat_title(cid)}")
            log_action(int(user_id), "link_set_mute_days", details={"chat_id": cid, "mute_days": v})
        except:
            send_message(chat_id, "❌ 請輸入整數天數，例如 1 / 3 / 7")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        return True

    # ---- violations remove by uid ----
    if state == "vio_remove_uid":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
            clear_wait(int(user_id))
            release_setting_lock(int(user_id))
            return True
        try:
            uid = int(text.strip())
            ok = clear_violation(cid, uid)
            if ok:
                send_message(chat_id, f"✅ 已移除違規：{uid}\n群組：{_chat_title(cid)}")
                log_action(int(user_id), "vio_remove", target=uid, details={"chat_id": cid})
            else:
                send_message(chat_id, f"⚠️ 違規名單沒有此 UID：{uid}")
        except:
            send_message(chat_id, "❌ 請輸入有效的 UID 數字")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        return True

    # ---- whitelist add/remove by uid ----
    if state == "wl_add_uid":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
            clear_wait(int(user_id))
            release_setting_lock(int(user_id))
            return True
        try:
            uid = int(text.strip())
            ok = whitelist_add(cid, uid, int(user_id))
            if ok:
                send_message(chat_id, f"✅ 已加入白名單：{uid}\n群組：{_chat_title(cid)}")
                log_action(int(user_id), "wl_add", target=uid, details={"chat_id": cid})
            else:
                send_message(chat_id, f"⚠️ 白名單已存在：{uid}")
        except:
            send_message(chat_id, "❌ 請輸入有效的 UID 數字")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        return True

    if state == "wl_remove_uid":
        cid = _get_active_chat_id(int(user_id))
        if not cid:
            send_message(chat_id, "❌ 尚未選擇群組（到 🛠️ 群組設定 選擇）")
            clear_wait(int(user_id))
            release_setting_lock(int(user_id))
            return True
        try:
            uid = int(text.strip())
            ok = whitelist_remove(cid, uid)
            if ok:
                send_message(chat_id, f"✅ 已移除白名單：{uid}\n群組：{_chat_title(cid)}")
                log_action(int(user_id), "wl_remove", target=uid, details={"chat_id": cid})
            else:
                send_message(chat_id, f"⚠️ 白名單不存在：{uid}")
        except:
            send_message(chat_id, "❌ 請輸入有效的 UID 數字")
            return True

        clear_wait(int(user_id))
        release_setting_lock(int(user_id))
        return True

    # fallback: unknown state
    clear_wait(int(user_id))
    release_setting_lock(int(user_id))
    return True


# ================== Web routes ==================
@app.get("/")
def root():
    return {
        "status": "ok",
        "bot": BOT_NAME,
        "core_ok": (CORE_CACHE.get("last_err") == ""),
        "rt_ok": (RT_CACHE.get("last_err") == ""),
    }


@app.get("/set_tg_webhook")
def set_tg_webhook():
    host = request.headers.get("x-forwarded-host") or request.host
    scheme = request.headers.get("x-forwarded-proto") or "https"
    url = f"{scheme}://{host}/tg-webhook"
    r = tg("setWebhook", {"url": url, "drop_pending_updates": True}, timeout=10)
    try:
        return r.json() if r is not None else {"ok": False, "url": url}
    except:
        return {"ok": False, "url": url}


@app.post("/tg-webhook")
def tg_webhook():
    try:
        update = request.get_json(force=True, silent=True) or {}

        # best-effort refresh
        refresh_data(force=False)

        # opportunistic flush: do not block too long
        opportunistic_flush(force=False)

        # ========== callback_query ==========
        if "callback_query" in update:
            cb = update["callback_query"]
            data_cb = (cb.get("data") or "").strip()
            answer_callback(cb.get("id"))

            msg = cb.get("message") or {}
            chat_id = int((msg.get("chat") or {}).get("id"))
            user_id = int((cb.get("from") or {}).get("id") or 0)
            thread_id = msg.get("message_thread_id", 0)

            handle_callback(data_cb, chat_id, user_id, message_thread_id=thread_id)

            opportunistic_flush(force=False)
            return {"ok": True}

        # ========== message ==========
        if "message" in update:
            msg = update["message"]
            chat_id = int((msg.get("chat") or {}).get("id"))
            user_id = int((msg.get("from") or {}).get("id") or 0)
            is_private = not str(chat_id).startswith("-100")
            text = (msg.get("text") or "").strip()

            # group: link moderation first
            if not is_private:
                try:
                    apply_link_moderation(msg)
                except:
                    pass

                # group admin commands / normal commands only if allowed
                if user_id and should_process(update, user_id, text):
                    if is_admin(user_id) and normalize_cmd(text) in {
                        "/admin_add_jarvis", "/admin_remove_jarvis",
                        "/admin_add_sparksign", "/admin_remove_sparksign",
                        "/admin_add_wl", "/admin_remove_wl",
                    }:
                        handle_group_admin(text, chat_id, user_id, update)
                    else:
                        if text:
                            handle_user_command(text, chat_id, is_private=False, update=update)

                opportunistic_flush(force=False)
                return {"ok": True}

            # private
            if not user_id:
                return {"ok": True}

            # UID query: forwarded msg (admin only)
            if is_admin(user_id):
                if msg.get("forward_from") and (text == "" or text.lower().startswith("/uid")):
                    handle_uid_query(update, chat_id)

            # panel waiting input
            if is_admin(user_id) and text:
                if handle_private_waiting_text(chat_id, user_id, text):
                    opportunistic_flush(force=False)
                    return {"ok": True}

            # /admin panel open
            if text:
                if text == "/admin":
                    handle_admin_command(text, chat_id, user_id)
                    opportunistic_flush(force=False)
                    return {"ok": True}

                # normal user commands
                handle_user_command(text, chat_id, is_private=True, update=update)

            opportunistic_flush(force=False)
            return {"ok": True}

        # ignore other update types
        opportunistic_flush(force=False)
        return {"ok": True}

    except Exception as e:
        print("[TG_WEBHOOK_ERR]", e)
        return {"ok": True}


# ================== WSGI entry ==================
if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
