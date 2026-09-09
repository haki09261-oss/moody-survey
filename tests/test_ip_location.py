import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import ip_location


@pytest.mark.parametrize("value,status", [
    (None, "missing"), ("", "missing"), ("   ", "missing"),
    ("not-an-ip", "invalid"), ("1.2.3.4, 5.6.7.8", "invalid"),
    ("127.0.0.1", "non_public"), ("192.168.1.2", "non_public"),
    ("10.1.2.3", "non_public"), ("100.64.0.1", "non_public"),
    ("::1", "non_public"), ("fe80::1", "non_public"),
    ("192.0.2.1", "non_public"), ("224.0.0.1", "non_public"),
])
def test_unusable_ips_are_not_assigned_a_city(value, status, monkeypatch):
    def unexpected_lookup(*args):
        pytest.fail("Unusable IPs must not reach the database")
    monkeypatch.setattr(ip_location, "_lookup", unexpected_lookup)
    result = ip_location.describe_ip(value)
    assert result["status"] == status
    assert result["city"] == result["province"] == ""


def test_real_databases_resolve_v4_v6_and_mapped_ips_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Geolocation must work without network access")
    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    ips = ["113.118.113.77", "240e:3b7:3272:d8d0:db09:c067:8d59:539e", "::ffff:113.118.113.77"]
    for address in ips:
        result = ip_location.describe_ip(address)
        assert result["status"] == "found"
        assert result["country"] == "中国"
        assert result["province"] == "广东省"
        assert result["city"] == "深圳市"
        assert result["isp"] == "电信"


def test_cloud_egress_has_a_comparison_warning():
    result = ip_location.describe_ip("47.100.0.1")
    assert result["status"] == "hosting"
    assert "不宜用于收货地比对" in result["note"]


@pytest.mark.parametrize("raw,status", [(None, "unavailable"), ("", "unknown"), ("bad|format", "unknown"), ("0|0|0|0|0", "unknown")])
def test_lookup_failure_does_not_invent_location(monkeypatch, raw, status):
    monkeypatch.setattr(ip_location, "_lookup", lambda *args: raw)
    result = ip_location.describe_ip("113.118.113.77")
    assert result["status"] == status
    assert result["city"] == ""


def test_missing_database_is_a_nonfatal_condition(monkeypatch, tmp_path):
    ip_location._reader.cache_clear()
    ip_location._lookup.cache_clear()
    monkeypatch.setattr(ip_location, "DB_DIR", tmp_path)
    try:
        assert ip_location.describe_ip("113.118.113.77")["status"] == "unavailable"
    finally:
        ip_location._reader.cache_clear()
        ip_location._lookup.cache_clear()


def test_concurrent_queries_preserve_results():
    ips = ["113.118.113.77", "47.100.0.1", "240e:3b7:3272:d8d0:db09:c067:8d59:539e"] * 20
    expected = [ip_location.describe_ip(ip) for ip in ips]
    ip_location._lookup.cache_clear()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(ip_location.describe_ip, ips)) == expected
