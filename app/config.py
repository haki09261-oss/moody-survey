# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SURVEY_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./survey.db"

    # token 生命周期（分发链接有效期）：3 天
    token_ttl_hours: int = 72

    # 风控阈值
    min_elapsed_ms: int = 5000
    ip_window_minutes: int = 10
    ip_max: int = 5
    token_max_devices: int = 3
    flag_threshold: int = 50
    # 同 IP 单设备硬拦：生产 SNI 透传层拿不到真实客户端 IP（全员同 IP）时
    # 须用 SURVEY_IP_SINGLE_DEVICE=false 关闭，否则第一个领取者会拦死所有人
    ip_single_device: bool = True

    # 后台
    admin_seed_username: str = "admin"
    admin_seed_password: str = "admin"  # 测试期默认；上线请用 SURVEY_ADMIN_SEED_PASSWORD 覆盖


settings = Settings()
