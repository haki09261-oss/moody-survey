# app/devices.py
"""User-Agent → 可读设备描述（品牌 + 型号），后台「设备」列展示用。"""
import re

# 型号前缀 → 品牌（安卓机型号命名惯例）
_MODEL_BRAND_PREFIXES = [
    ("SM-", "三星"),
    ("MI ", "小米"), ("Mi ", "小米"), ("Redmi", "红米"), ("2", "小米"),  # 小米数字型号如 23127PN0CC
    ("PJ", "OPPO"), ("PH", "OPPO"), ("PG", "OPPO"), ("OPPO", "OPPO"),
    ("V2", "vivo"), ("vivo", "vivo"), ("iQOO", "iQOO"),
    ("Pixel", "Google"),
    ("NOH", "华为"), ("VDE", "华为"), ("ALN", "华为"), ("BRA", "华为"), ("ADY", "华为"),
]


def _brand_for_model(model: str, ua: str) -> str:
    if "HUAWEI" in ua or "HarmonyOS" in ua or "OpenHarmony" in ua:
        return "华为"
    if "HONOR" in ua or model.upper().startswith("HONOR"):
        return "荣耀"
    for prefix, brand in _MODEL_BRAND_PREFIXES:
        if model.startswith(prefix):
            return brand
    return ""


# iPhone 不在 UA 里暴露型号，用逻辑分辨率反查型号档位（同分辨率多型号并列）
_IPHONE_BY_SCREEN = {
    "320x568": "iPhone SE(初代)/5s",
    "375x667": "iPhone SE(2/3代)/8/7",
    "414x736": "iPhone 8 Plus/7 Plus",
    "375x812": "iPhone X/XS/11 Pro/12 mini",
    "414x896": "iPhone XR/11/XS Max/11 Pro Max",
    "360x780": "iPhone 12/13 mini",
    "390x844": "iPhone 12/13/14",
    "393x852": "iPhone 14 Pro/15/15 Pro/16",
    "428x926": "iPhone 12/13 Pro Max/14 Plus",
    "430x932": "iPhone 14 Pro Max/15 Plus/15 Pro Max/16 Plus",
    "402x874": "iPhone 16 Pro/17/17 Pro",
    "440x956": "iPhone 16 Pro Max/17 Pro Max",
}


def _describe_from_device(device: dict) -> str:
    """优先用客户端上报的设备信息(小程序 my.getSystemInfoSync / tt.getSystemInfoSync)。
    云网关转发的 UA 不是手机的,小程序场景只能靠这个快照。"""
    if not device:
        return ""
    model = str(device.get("model") or "").strip()
    brand = str(device.get("brand") or "").strip()
    system = str(device.get("system") or "").strip()
    platform = str(device.get("platform") or "").strip()
    screen = str(device.get("screen") or "").strip()
    is_ios = ("iphone" in model.lower()) or platform.lower() == "ios" or brand.lower() in ("apple", "iphone")
    if is_ios:
        # iPhone：优先用屏幕逻辑分辨率反查友好型号；否则用 model（形如 iPhone15,3）
        name = _IPHONE_BY_SCREEN.get(screen) or (model if model.lower().startswith("iphone") else "iPhone")
        return f"{name} · {system}" if system else name
    # 安卓/其他：brand + model（避免 model 已含 brand 时重复）
    if brand and model:
        head = model if model.lower().startswith(brand.lower()) else f"{brand} {model}"
    else:
        head = model or brand or platform
    bits = [b for b in (head, system) if b]
    return " · ".join(bits)


def describe_device(ua, device=None) -> str:
    """先用小程序上报的设备快照；拿不到再回退 User-Agent 解析品牌+型号。"""
    device = device or {}
    from_dev = _describe_from_device(device)
    if from_dev:
        return from_dev
    if not ua:
        return "未知设备"

    # 鸿蒙/华为：(Phone; OpenHarmony 6.1; VDE-AL00 Build/HUAWEI)
    m = re.search(r"OpenHarmony [\d.]+;\s*([^;)]+?)(?:\s+Build/[^;)]*)?\)", ua)
    if m:
        return f"华为 {m.group(1).strip()}"

    if "iPhone" in ua:
        model = _IPHONE_BY_SCREEN.get(str(device.get("screen") or ""))
        if model:
            return model
        ver = re.search(r"iPhone OS (\d+)[_.](\d+)", ua)
        return f"iPhone (iOS {ver.group(1)}.{ver.group(2)})" if ver else "iPhone"
    if "iPad" in ua:
        return "iPad"

    # 安卓：(Linux; Android 14; 23127PN0CC Build/...)
    m = re.search(r"Android [\d.]+;\s*([^;)]+?)(?:\s+Build/[^;)]*)?\)", ua)
    if m:
        model = m.group(1).strip()
        if model.upper().startswith("HONOR"):
            model = model[5:].strip()
            return f"荣耀 {model}" if model else "荣耀"
        brand = _brand_for_model(model, ua)
        return f"{brand} {model}".strip() if brand else f"安卓 {model}"

    if "Macintosh" in ua:
        return "Mac 电脑"
    if "Windows NT" in ua:
        return "Windows 电脑"
    if "Android" in ua:
        return "安卓手机"
    return "未知设备"
