"""Resolve recorded submission IPs locally; never infer a buyer identity."""
import ipaddress
import logging
from functools import lru_cache
from pathlib import Path

from ip2region import searcher as xdb, util


logger = logging.getLogger(__name__)
DB_DIR = Path(__file__).resolve().parent.parent / "resources" / "ip2region"
SOURCE = "ip2region 离线库 c1a1fc7d5941"
HOSTING_MARKERS = (
    "阿里", "腾讯云", "华为云", "百度云", "亚马逊",
    "数据中心", "机房", "cloud", "hosting", "amazon", "microsoft", "fastly",
)


@lru_cache(maxsize=2)
def _reader(version: int):
    path = str(DB_DIR / f"ip2region_v{version}.xdb")
    try:
        util.verify_from_file(path)
        content = util.load_content_from_file(path)
        # The official full-buffer reader supports concurrent queries without shared file IO.
        return xdb.new_with_buffer(util.IPv4 if version == 4 else util.IPv6, content)
    except Exception:
        logger.exception("IP location database unavailable (IPv%s)", version)
        return None


@lru_cache(maxsize=4096)
def _lookup(address: str, version: int):
    reader = _reader(version)
    if reader is None:
        return None
    try:
        return reader.search(address)
    except Exception:
        # Do not include consumer IPs in diagnostic logs.
        logger.exception("IP location lookup failed (IPv%s)", version)
        return None


def describe_ip(raw_ip):
    result = {
        "status": "missing", "label": "未记录 IP", "country": "",
        "province": "", "city": "", "isp": "", "source": "",
        "note": "无法用于地址比对",
    }
    value = str(raw_ip or "").strip()
    if not value:
        return result
    try:
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
    except ValueError:
        return {**result, "status": "invalid", "label": "IP 格式无效"}
    if not address.is_global or address.is_multicast:
        return {**result, "status": "non_public", "label": "内网或非公网 IP"}

    region = _lookup(str(address), address.version)
    if region is None:
        return {**result, "status": "unavailable", "label": "归属地暂不可用"}
    # This pinned dataset uses country|province|city|ISP|ISO country code.
    parts = region.split("|")
    if len(parts) != 5:
        return {**result, "status": "unknown", "label": "未查到归属地", "source": SOURCE}
    country, province, city, isp, _ = ("" if part in ("", "0") else part for part in parts)
    places = list(dict.fromkeys(part for part in (country, province, city) if part))
    if not places:
        return {**result, "status": "unknown", "label": "未查到归属地", "source": SOURCE}
    hosting = any(marker in isp.lower() for marker in HOSTING_MARKERS)
    return {
        "status": "hosting" if hosting else "found",
        "label": " · ".join(places), "country": country, "province": province,
        "city": city, "isp": isp, "source": SOURCE,
        "note": "疑似云服务出口，不宜用于收货地比对" if hosting else "网络出口位置，仅供辅助核对",
    }
