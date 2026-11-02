"""
AIORI - Privacy-Aware IPv6 Security Monitoring System
Global configuration loaded from environment variables.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Application
    app_name: str = Field(default="AIORI", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    debug: bool = Field(default=True, alias="DEBUG")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./database/aiori.db",
        alias="DATABASE_URL",
    )

    # WSL2
    wsl_distro: str = Field(default="Ubuntu-24.04", alias="WSL_DISTRO")
    wsl_user: str = Field(default="root", alias="WSL_USER")

    # Networking
    mininet_enabled: bool = Field(default=False, alias="MININET_ENABLED")
    zeek_log_dir: str = Field(default="/var/log/zeek", alias="ZEEK_LOG_DIR")
    pcap_dir: str = Field(default="/tmp/aiori/pcap", alias="PCAP_DIR")
    network_interface: str = Field(default="s1-eth0", alias="NETWORK_INTERFACE")

    # AI Model
    ml_model_dir: str = Field(default="./ml/models", alias="ML_MODEL_DIR")
    similarity_threshold: float = Field(default=0.75, alias="SIMILARITY_THRESHOLD")
    anomaly_threshold: float = Field(default=0.85, alias="ANOMALY_THRESHOLD")
    feature_window_seconds: int = Field(default=30, alias="FEATURE_WINDOW_SECONDS")

    # Blockchain
    blockchain_enabled: bool = Field(default=False, alias="BLOCKCHAIN_ENABLED")
    hlf_network_dir: str = Field(
        default="../blockchain/network", alias="HLF_NETWORK_DIR"
    )
    hlf_channel_name: str = Field(
        default="aiori-channel", alias="HLF_CHANNEL_NAME"
    )
    hlf_chaincode_name: str = Field(
        default="identity_audit", alias="HLF_CHAINCODE_NAME"
    )

    # WebSocket
    ws_heartbeat_interval: int = Field(default=30, alias="WS_HEARTBEAT_INTERVAL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


# Project root (backend directory)
BASE_DIR = Path(__file__).resolve().parent

# Singleton settings instance
settings = Settings()
