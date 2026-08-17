# tests/test_codes.py
import re

from app.codes import generate_redeem_code, generate_token

REDEEM_RE = re.compile(r"^WJ-[0-9A-HJKMNP-TV-Z]{6}$")


def test_redeem_code_format():
    code = generate_redeem_code()
    assert REDEEM_RE.match(code), code


def test_redeem_code_no_ambiguous_chars():
    for _ in range(200):
        code = generate_redeem_code()
        body = code[3:]
        assert not set(body) & set("ILOU")


def test_redeem_code_unique_enough():
    codes = {generate_redeem_code() for _ in range(1000)}
    assert len(codes) > 990  # 极低碰撞概率


def test_token_urlsafe_length():
    token = generate_token()
    assert len(token) >= 20
    assert "/" not in token and "+" not in token


def test_token_from_times_is_md5_with_device():
    import hashlib
    from datetime import datetime
    from app.codes import token_from_times
    c = datetime(2026, 6, 9, 1, 2, 3)
    e = datetime(2026, 6, 12, 1, 2, 3)
    t = token_from_times(c, e, fingerprint="fp-abc")
    assert len(t) == 32 and all(ch in "0123456789abcdef" for ch in t)
    # token = md5(生成时间 + 设备信息 + 到期时间)
    assert t == hashlib.md5(f"{c.isoformat()}|fp-abc|{e.isoformat()}|".encode()).hexdigest()
    # 不同设备 → 不同 token；无设备信息也可生成（兜底）
    assert t != token_from_times(c, e, fingerprint="fp-xyz")
    assert token_from_times(c, e) == hashlib.md5(f"{c.isoformat()}||{e.isoformat()}|".encode()).hexdigest()


def test_parse_degree():
    from app.codes import parse_degree
    assert parse_degree("475") == 475
    assert parse_degree("4.75") == 475
    assert parse_degree("475度") == 475
    assert parse_degree("") == 0
    assert parse_degree(None) == 0
    assert parse_degree("abc") == 0
    assert parse_degree("99999") == 0  # 超范围 → 0
    assert parse_degree("480") == 0    # 非 25 的倍数 → 0
    assert parse_degree("1000") == 1000
    assert parse_degree("25") == 25
    assert parse_degree("0") == 0


def test_build_display_code():
    from app.codes import build_display_code
    assert build_display_code("WJ-ABC123", 1, 0) == "WJ-ABC12302-0"
    assert build_display_code("WJ-ABC123", 2, 475) == "WJ-ABC12310-475"


def test_derive_user_code_deterministic():
    from app.codes import derive_user_code
    assert derive_user_code("tok", "fp") == derive_user_code("tok", "fp")
    assert len(derive_user_code("tok", "fp")) == 8


def test_derive_user_code_varies_by_device():
    from app.codes import derive_user_code
    assert derive_user_code("tok", "fp1") != derive_user_code("tok", "fp2")


def test_derive_user_code_varies_by_token():
    from app.codes import derive_user_code
    assert derive_user_code("tok1", "fp") != derive_user_code("tok2", "fp")
