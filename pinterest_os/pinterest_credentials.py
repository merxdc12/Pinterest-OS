"""Explicit Linux Secret Service credential storage (never a plaintext fallback)."""
import json
import re
from datetime import datetime, timezone
from .pinterest_import import _account

SERVICE = "ITHutir-PinterestOS-PinterestAPI"
FIELDS = ("access_token","app_secret","refresh_token","expires_at")

def identity(username, app_id):
    account = _account(username)
    if not re.fullmatch(r"[0-9]{1,30}", app_id.strip()):
        raise ValueError("Введіть цифровий App ID.")
    return account + ":" + app_id.strip()

def backend():
    try:
        from keyring.backends.SecretService import Keyring
        if Keyring.priority <= 0:
            raise RuntimeError()
        return Keyring()
    except Exception:
        raise ValueError("Linux Keyring (Secret Service) недоступний. Розблокуйте сховище; незахищене збереження заборонено.") from None

def validated(record):
    if not isinstance(record,dict): raise ValueError("Некоректний запис ключів.")
    data = {}
    for field in FIELDS:
        value=record.get(field,"")
        if not isinstance(value,str): raise ValueError("Некоректний запис ключів.")
        value=value.strip()
        if len(value)>16384 or (field!="expires_at" and any(c.isspace() for c in value)):
            raise ValueError("Ключ містить неприпустимі символи.")
        data[field]=value
    if not data["access_token"]: raise ValueError("Введіть Access Token.")
    if data["expires_at"]:
        try:
            stamp=datetime.fromisoformat(data["expires_at"])
            if stamp.tzinfo is None: raise ValueError()
            data["expires_at"]=stamp.isoformat()
        except ValueError:
            raise ValueError("Термін дії: YYYY-MM-DDTHH:MM+01:00 (із часовим поясом).") from None
    return data

def load(username,app_id,store=None):
    key=identity(username,app_id)
    store=store if store is not None else backend()
    try: raw=store.get_password(SERVICE,key)
    except Exception: raise ValueError("Не вдалося прочитати Linux Keyring. Перевірте його доступність.") from None
    if raw is None: return None
    try: return validated(json.loads(raw))
    except (ValueError,TypeError): raise ValueError("Збережений запис пошкоджений. Введіть ключі повторно.") from None

def save(username,app_id,record,store=None):
    key=identity(username,app_id)
    data=validated(record)
    store=store if store is not None else backend()
    try:
        store.set_password(SERVICE,key,json.dumps(data))
        if store.get_password(SERVICE,key)!=json.dumps(data): raise RuntimeError()
    except Exception: raise ValueError("Не вдалося підтвердити збереження у Linux Keyring. Перевірте його стан.") from None

def delete(username,app_id,store=None):
    key=identity(username,app_id)
    store=store if store is not None else backend()
    try:
        if store.get_password(SERVICE,key) is not None:
            store.delete_password(SERVICE,key)
        if store.get_password(SERVICE,key) is not None: raise RuntimeError()
    except Exception: raise ValueError("Не вдалося видалити ключі з Linux Keyring.") from None

def ensure_current(data, now=None):
    data=validated(data)
    now=now or datetime.now(timezone.utc)
    if data["expires_at"] and datetime.fromisoformat(data["expires_at"])<=now:
        raise ValueError("Access Token прострочений. Отримайте новий маркер і збережіть його.")
    return data["access_token"]
