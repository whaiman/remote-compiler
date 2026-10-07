import os
import stat
from pathlib import Path

import yaml

import rgcc.core.config as config


def test_secure_dump_writes_yaml_and_0600(tmp_path: Path):
    path = tmp_path / "secret.yaml"
    config._secure_dump({"server": {"auth_token": "secret"}}, path)
    assert yaml.safe_load(path.read_text())["server"]["auth_token"] == "secret"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_server_config_creates_default(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "rgccd.yaml"
    monkeypatch.setattr(config, "SERVER_CONFIG_PATH", path)
    monkeypatch.setattr(config.secrets, "token_urlsafe", lambda n: "TOKEN")

    result = config.load_server_config()
    assert result["server"]["auth_token"] == "TOKEN"
    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert result["compilers"]["g++"]["platforms"]["win64"]["target"] == "x86_64-w64-mingw32"


def test_load_server_config_reads_existing(tmp_path, monkeypatch):
    path = tmp_path / "rgccd.yaml"
    path.write_text("server:\n  auth_token: existing\n")
    monkeypatch.setattr(config, "SERVER_CONFIG_PATH", path)
    assert config.load_server_config() == {"server": {"auth_token": "existing"}}


def test_load_server_config_empty_yaml_returns_empty(tmp_path, monkeypatch):
    path = tmp_path / "rgccd.yaml"
    path.write_text("")
    monkeypatch.setattr(config, "SERVER_CONFIG_PATH", path)
    assert config.load_server_config() == {}


def test_load_client_config_creates_placeholder(tmp_path, monkeypatch):
    path = tmp_path / "rgcc.yaml"
    monkeypatch.setattr(config, "CLIENT_CONFIG_PATH", path)
    result = config.load_client_config()
    assert result["client"]["endpoint"] == "http://CHANGE_ME:4444"
    assert result["client"]["auth_token"] == "PASTE_TOKEN_FROM_SERVER_CONFIG"
    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_client_config_reads_existing(tmp_path, monkeypatch):
    path = tmp_path / "rgcc.yaml"
    path.write_text("client:\n  endpoint: http://localhost:4444\n  auth_token: x\n")
    monkeypatch.setattr(config, "CLIENT_CONFIG_PATH", path)
    assert config.load_client_config() == {
        "client": {"endpoint": "http://localhost:4444", "auth_token": "x"}
    }


def test_secure_dump_overwrites_existing_file(tmp_path: Path):
    path = tmp_path / "cfg.yaml"
    config._secure_dump({"a": 1}, path)
    config._secure_dump({"a": 2}, path)
    assert yaml.safe_load(path.read_text()) == {"a": 2}
