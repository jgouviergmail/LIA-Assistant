"""Deterministic, conservative access-secret exclusion before persistence.

This is not a classifier of all private information. Medical/banking messages
remain personal archive content unless they contain an identifiable access secret.
"""

import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlsplit

FILTER_VERSION = 1
_ACCESS = re.compile(
    r"(?:\botp(?=\b|\d)|one[ -]?time(?: password| code)?|verification code|security code|login code|"
    r"access code|authentication code|code (?:de |d['’])?(?:connexion|vérification|sécurité|accès|authentification)|"
    r"einmalpasswort|bestätigungscode|sicherheitscode|anmeldecode|"
    r"código (?:de )?(?:verificación|seguridad|acceso)|codice (?:di )?(?:verifica|accesso|sicurezza)|"
    r"(?:your|votre|dein|tu|il tuo)\s+(?:code|código|codice)\s*(?:is|est|ist|es|è|[:=])|"
    r"验证码|驗證碼|动态密码|动态口令)",
    re.IGNORECASE,
)
_RECOVERY = re.compile(
    r"(?:recovery (?:code|key)|backup code|code (?:de )?(?:récupération|secours)|"
    r"wiederherstellungscode|código de recuperación|codice di recupero|恢复码|備用碼)",
    re.IGNORECASE,
)
_PASSWORD = re.compile(
    r"(?:password|mot de passe|passwort|contraseña|password temporanea|密码)"
    r"(?:\s+\w+){0,2}\s*(?:[:：=]|(?:is|est|ist|es|è)\s*:)\s*\S{4,}",
    re.IGNORECASE,
)
_LOGIN_LINK = re.compile(
    r"(?:sign[ -]?in|log[ -]?in|connexion|connectez|réinitialis|reset.{0,20}password|"
    r"anmeld|restablec|accedi|登录|登入).{0,180}https?://\S+",
    re.IGNORECASE | re.DOTALL,
)
_PASSWORD_PLAIN = re.compile(
    r"(?:password|mot de passe|passwort|contraseña|密码)\s+(?:is|est|ist|es|è)\s+([^\s,;。]{6,128})",
    re.IGNORECASE,
)
_PASSWORD_ADVICE = frozenset(
    {"important", "confidential", "strong", "private", "personnel", "robuste", "secret"}
)
_URL_SCAN_CHARS = 2048
_URL = re.compile(rf"https?://[^\s]{{1,{_URL_SCAN_CHARS}}}", re.IGNORECASE)
_AUTH_PATHS = frozenset(
    {
        "login",
        "signin",
        "sign-in",
        "auth",
        "reset",
        "recover",
        "magic",
        "password-reset",
        "reset-password",
    }
)
_AUTH_KEYS = frozenset(
    {"token", "code", "key", "access_token", "auth_token", "login_token", "reset_token"}
)


def _auth_url(raw: str) -> bool:
    try:
        parts = urlsplit(raw)
    except ValueError:
        return False
    if parts.password:
        return True
    path = unquote(parts.path).casefold()
    actions = {segment.partition(".")[0] for segment in path.split("/")}
    if not actions & _AUTH_PATHS:
        return False
    if len(raw) >= _URL_SCAN_CHARS:
        return True
    try:
        pairs = parse_qsl(parts.query, max_num_fields=32)
    except ValueError:
        return True
    if any(key.casefold() in _AUTH_KEYS and value for key, value in pairs):
        return True
    return bool(actions & {"reset", "recover", "magic"} and len(path.rsplit("/", 1)[-1]) >= 8)


def _has_auth_url(text: str) -> bool:
    return any(_auth_url(match.group()) for match in _URL.finditer(text))


def _plain_password(text: str) -> bool:
    match = _PASSWORD_PLAIN.search(text)
    return bool(match and match.group(1).rstrip(".!?").casefold() not in _PASSWORD_ADVICE)


_CODE = re.compile(r"(?<!\d)(?:\d[\s-]?){4,10}(?!\d)")
_RECOVERY_VALUE = re.compile(r"[:：=]\s*[\w-]{6,}")

_ALPHA_CODE = re.compile(r"(?:[:=：]|\b(?:is|est|ist|es|è)\b)\s*[A-Z0-9]{4,12}\b")
_MIXED_CODE = re.compile(r"\b(?=[A-Z0-9]{4,12}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+\b")
_INVISIBLE = str.maketrans("", "", "\u200b\u200c\u200d\u2060\ufeff")


def _has_access_code(text: str) -> bool:
    for match in _ACCESS.finditer(text):
        window = text[max(0, match.start() - 40) : match.end() + 96]
        if _CODE.search(window) or _ALPHA_CODE.search(window) or _MIXED_CODE.search(window):
            return True
    return False


def contains_access_secret(body: str) -> bool:
    text = unicodedata.normalize("NFKC", body).translate(_INVISIBLE)
    return bool(
        _has_access_code(text)
        or (_RECOVERY.search(text) and _RECOVERY_VALUE.search(text))
        or _PASSWORD.search(text)
        or _LOGIN_LINK.search(text)
        or _has_auth_url(text)
        or _plain_password(text)
    )
