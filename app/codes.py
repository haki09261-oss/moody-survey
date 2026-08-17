# app/codes.py
import hashlib
import re
import secrets
from datetime import datetime

# Crockford Base32 去掉易混字符 I L O U
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_redeem_code(length: int = 6) -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"WJ-{body}"


def generate_token() -> str:
    return secrets.token_urlsafe(16)


def token_from_times(created: datetime, expires: datetime, fingerprint: str = "", salt: str = "") -> str:
    """分发链接唯一 id：md5(生成时间 + 设备信息 + 到期时间)。salt 仅用于极少数同刻碰撞兜底。"""
    raw = f"{created.isoformat()}|{fingerprint}|{expires.isoformat()}|{salt}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_degree(raw) -> int:
    """解析用户填写的眼睛度数；非法/超范围/空 → 0。取数字部分，如 '475度' → 475。
    合法范围 0–1000 且须为 25 的倍数（隐形眼镜度数规格）。"""
    if raw is None:
        return 0
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return 0
    try:
        v = int(digits)
    except ValueError:
        return 0
    return v if 0 <= v <= 1000 and v % 25 == 0 else 0


def build_display_code(redeem_code: str, tier_reached: int, degree: int) -> str:
    """业务兑换码：WJ-XXXXXX{片数}-{度数}。片数紧贴编码(无分隔)防篡改：10=10片装 / 02=2片装。"""
    pkg = "10" if (tier_reached or 1) >= 2 else "02"
    return f"{redeem_code}{pkg}-{int(degree or 0)}"


def derive_user_code(token: str, fingerprint: str) -> str:
    """用户码 = md5(token + 设备指纹) 前 8 位（大写）。纯内部身份，仅用于判资格。"""
    raw = f"{token}|{fingerprint}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8].upper()
