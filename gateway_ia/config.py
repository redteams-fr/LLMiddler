from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class BackendConfig(BaseModel):
    base_url: str = "http://172.24.208.1:1234"
    timeout: int = 120
    verify_ssl: bool = True


class ListenConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class UIConfig(BaseModel):
    prefix: str = "/_ui"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    quiet: bool = False


class AppConfig(BaseModel):
    backend: BackendConfig = BackendConfig()
    listen: ListenConfig = ListenConfig()
    ui: UIConfig = UIConfig()
    logging: LoggingConfig = LoggingConfig()


def load_config() -> AppConfig:
    config_path = Path(
        os.environ.get("GATEWAY_IA_CONFIG", "config.yaml")
    )
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)
    return AppConfig()
