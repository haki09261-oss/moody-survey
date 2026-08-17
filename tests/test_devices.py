# tests/test_devices.py
from app.devices import describe_device


def test_harmony_huawei():
    ua = ("Mozilla/5.0 (Phone; OpenHarmony 6.1; VDE-AL00 Build/HUAWEI) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 ArkWeb/4.1.6.1 Mobile Lark/7.68.8")
    assert describe_device(ua) == "华为 VDE-AL00"


def test_iphone():
    ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
    assert describe_device(ua) == "iPhone (iOS 18.7)"


def test_android_xiaomi():
    ua = ("Mozilla/5.0 (Linux; Android 14; 23127PN0CC Build/UKQ1.230804.001) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
    assert describe_device(ua) == "小米 23127PN0CC"


def test_android_samsung():
    ua = "Mozilla/5.0 (Linux; Android 13; SM-G9910) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Mobile Safari/537.36"
    assert describe_device(ua) == "三星 SM-G9910"


def test_android_huawei_honor():
    ua = "Mozilla/5.0 (Linux; Android 12; HONOR ANY-AN00 Build/HONORANY-AN00) AppleWebKit/537.36"
    assert describe_device(ua).startswith("荣耀")


def test_mac_and_windows():
    mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    assert describe_device(mac) == "Mac 电脑"
    assert describe_device(win) == "Windows 电脑"


def test_empty_ua():
    assert describe_device("") == "未知设备"
    assert describe_device(None) == "未知设备"


def test_iphone_model_from_screen():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15"
    assert describe_device(ua, {"screen": "390x844"}) == "iPhone 12/13/14"
    assert describe_device(ua, {"screen": "440x956"}) == "iPhone 16 Pro Max/17 Pro Max"
    # 未知分辨率回退 iOS 版本口径
    assert describe_device(ua, {"screen": "999x999"}) == "iPhone (iOS 18.7)"
