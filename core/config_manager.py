import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "active_profile": "default",
    "profiles": {
        "default": {
            "name": "Default",
            "keys": {}
        }
    },
    "midi_device": "",
    "brightness": 80
}

# Launchpad Mini MK3 の 8x8 グリッド + 上部・右端パッドのMIDIノート番号
# 下から上に向かって 11〜19, 21〜29, ..., 81〜89
# 上部ラウンドボタン: 91〜99
# 右端ラウンドボタン: 19, 29, 39, 49, 59, 69, 79, 89

GRID_NOTES = []
for row in range(8):
    for col in range(8):
        note = (8 - row) * 10 + (col + 1)
        GRID_NOTES.append(note)

# 上部ボタン (CC)
TOP_CCS = list(range(91, 99))
# 右端ボタン (Note)
RIGHT_NOTES = [19, 29, 39, 49, 59, 69, 79, 89]

ACTION_TYPES = {
    "app_launch": "アプリ起動",
    "hotkey": "キーボードショートカット",
    "text_type": "テキスト入力",
    "none": "なし"
}


class ConfigManager:
    def __init__(self, config_dir: str | None = None):
        if config_dir is None:
            config_dir = Path.home() / ".launchdeck"
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "config.json"
        self.config = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # デフォルトとマージ
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError):
                pass
        return DEFAULT_CONFIG.copy()

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # ---- プロファイル操作 ----

    def get_profiles(self) -> list[str]:
        return list(self.config["profiles"].keys())

    def get_active_profile(self) -> str:
        return self.config["active_profile"]

    def set_active_profile(self, name: str):
        if name in self.config["profiles"]:
            self.config["active_profile"] = name
            self.save()

    def add_profile(self, name: str):
        if name not in self.config["profiles"]:
            self.config["profiles"][name] = {"name": name, "keys": {}}
            self.save()

    def remove_profile(self, name: str):
        if name in self.config["profiles"] and name != "default":
            del self.config["profiles"][name]
            if self.config["active_profile"] == name:
                self.config["active_profile"] = "default"
            self.save()

    # ---- キー操作 ----

    def get_key_config(self, note: int) -> dict:
        profile = self.config["active_profile"]
        keys = self.config["profiles"][profile]["keys"]
        return keys.get(str(note), {
            "action_type": "none",
            "label": "",
            "color": [0, 0, 0],
            "params": {}
        })

    def set_key_config(self, note: int, cfg: dict):
        profile = self.config["active_profile"]
        self.config["profiles"][profile]["keys"][str(note)] = cfg
        self.save()

    def get_all_keys(self) -> dict:
        profile = self.config["active_profile"]
        return self.config["profiles"][profile]["keys"]

    # ---- デバイス設定 ----

    def get_midi_device(self) -> str:
        return self.config.get("midi_device", "")

    def set_midi_device(self, device: str):
        self.config["midi_device"] = device
        self.save()

    def get_brightness(self) -> int:
        return self.config.get("brightness", 80)

    def set_brightness(self, value: int):
        self.config["brightness"] = max(0, min(127, value))
        self.save()
