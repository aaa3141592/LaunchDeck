import subprocess
import threading
from typing import Any
import os
import webbrowser
import configparser
try:
    from pynput.keyboard import Controller, Key, HotKey
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


# 文字列 → pynput Key のマッピング
KEY_MAP: dict[str, Any] = {}
if PYNPUT_AVAILABLE:
    KEY_MAP = {
        "ctrl": Key.ctrl,
        "alt": Key.alt,
        "shift": Key.shift,
        "cmd": Key.cmd,
        "win": Key.cmd,
        "super": Key.cmd,
        "enter": Key.enter,
        "space": Key.space,
        "tab": Key.tab,
        "esc": Key.esc,
        "backspace": Key.backspace,
        "delete": Key.delete,
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right,
        "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
        "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
        "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
    }


class ActionManager:
    def __init__(self, config):
        self.config = config
        self._keyboard = Controller() if PYNPUT_AVAILABLE else None

    def trigger(self, note: int):
        """ボタン押下時に呼ばれる"""
        cfg = self.config.get_key_config(note)
        action_type = cfg.get("action_type", "none")

        if action_type == "none":
            return

        # 別スレッドで実行（MIDIスレッドをブロックしない）
        t = threading.Thread(
            target=self._execute,
            args=(action_type, cfg.get("params", {})),
            daemon=True
        )
        t.start()

    def _execute(self, action_type: str, params: dict):
        try:
            if action_type == "app_launch":
                self._launch_app(params)
            elif action_type == "hotkey":
                self._send_hotkey(params)
            elif action_type == "text_type":
                self._type_text(params)
        except Exception as e:
            print(f"[Action] エラー ({action_type}): {e}")

    # ---- アプリ起動 ----

    def _launch_app(self, params: dict):
        path = params.get("path", "")
        args = params.get("args", "")
        if not path:
            return

        # -------------------------
        # URL直指定
        # -------------------------
        if path.startswith("http://") or path.startswith("https://"):
            webbrowser.open(path)
            return

        # -------------------------
        # .url ショートカット
        # -------------------------
        if path.lower().endswith(".url"):
            try:
                cfg = configparser.ConfigParser()
                cfg.read(path, encoding="utf-8")

                url = cfg.get("InternetShortcut", "URL", fallback=None)
                if url:
                    webbrowser.open(url)
                return
            except Exception as e:
                print("url parse error:", e)

        # -------------------------
        # 通常アプリ / exe / フォルダ
        # -------------------------
        try:
            if args:
                subprocess.Popen([path] + args.split(), shell=False)
            else:
                os.startfile(path)   # ← Windows最強
        except Exception:
            # 最終フォールバック
            try:
                subprocess.Popen(path, shell=True)
            except Exception as e:
                print("[launch error]", e)

    # ---- キーボードショートカット ----

    def _send_hotkey(self, params: dict):
        if not PYNPUT_AVAILABLE or not self._keyboard:
            return
        combo = params.get("combo", "")
        if not combo:
            return

        parts = [p.strip().lower() for p in combo.split("+")]
        keys = []
        for part in parts:
            if part in KEY_MAP:
                keys.append(KEY_MAP[part])
            elif len(part) == 1:
                keys.append(part)
            else:
                print(f"[Hotkey] 不明なキー: {part}")
                return

        # 順番に押して、逆順に離す
        for k in keys:
            self._keyboard.press(k)
        for k in reversed(keys):
            self._keyboard.release(k)

    # ---- テキスト入力 ----

    def _type_text(self, params: dict):
        if not PYNPUT_AVAILABLE or not self._keyboard:
            return
        text = params.get("text", "")
        if text:
            self._keyboard.type(text)

    # ---- 設定UI用: アクション一覧 ----

    @staticmethod
    def get_action_types() -> list[dict]:
        return [
            {"id": "none",       "label": "なし"},
            {"id": "app_launch", "label": "アプリ起動"},
            {"id": "hotkey",     "label": "キーボードショートカット"},
            {"id": "text_type",  "label": "テキスト入力"},
        ]
