import customtkinter as ctk
from tkinter import colorchooser, filedialog, messagebox
import threading

from core.config_manager import ConfigManager, GRID_NOTES, ACTION_TYPES
from core.midi_handler import MidiHandler
from core.action_manager import ActionManager

try:
    from pynput import keyboard as _kb_check
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


def _resource_path(*parts: str) -> "Path":
    import sys
    from pathlib import Path
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base.joinpath(*parts)

# テーマ設定
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# カラーパレット（アプリ全体で使用）
COLORS = {
    "bg_dark":    "#0F0F0F",
    "bg_panel":   "#1A1A1A",
    "bg_card":    "#242424",
    "bg_hover":   "#2E2E2E",
    "accent":     "#6C63FF",
    "accent_dim": "#4A44B3",
    "text_main":  "#F0F0F0",
    "text_sub":   "#9A9A9A",
    "border":     "#333333",
    "success":    "#22C55E",
    "danger":     "#EF4444",
    "warning":    "#F59E0B",
}

PAD_SIZE = 52
PAD_GAP  = 6 
PAD_COLS = 8
PAD_ROWS = 8


class PadButton(ctk.CTkButton):
    """1つのLaunchpadパッドを表すボタン"""
    @staticmethod
    def _wrap_label(text: str, max_chars: int = 6) -> str:
        """max_chars幅で折り返して改行を挿入する"""
        if not text:
            return ""
        lines = []
        while len(text) > max_chars:
            lines.append(text[:max_chars])
            text = text[max_chars:]
        lines.append(text)
        return "\n".join(lines)

    def __init__(self, parent, note: int, config: ConfigManager, on_click, **kwargs):
        self.note = note
        self.config = config
        self.on_click_cb = on_click

        cfg = config.get_key_config(note)
        color = cfg.get("color", [0, 0, 0])
        label = cfg.get("label", "")
        fg = self._rgb_to_hex(*color) if any(color) else COLORS["bg_card"]
        text_color = self._text_color_for_bg(*color) if any(color) else COLORS["text_sub"]

        kwargs.pop("fg_color", None)
        kwargs.pop("hover_color", None)

        super().__init__(
            parent,
            text=self._wrap_label(label),
            width=PAD_SIZE,
            height=PAD_SIZE,
            fg_color=fg,
            hover_color=self._brighten(fg),
            text_color=text_color,
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=6,
            font=ctk.CTkFont(size=9),
            command=self._on_click,
            **kwargs
        )

    def _on_click(self):
        self.on_click_cb(self.note)

    def refresh(self):
        cfg = self.config.get_key_config(self.note)
        color = cfg.get("color", [0, 0, 0])
        label = cfg.get("label", "")
        fg = self._rgb_to_hex(*color) if any(color) else COLORS["bg_card"]
        text_color = self._text_color_for_bg(*color) if any(color) else COLORS["text_sub"]
        self.configure(
            fg_color=fg,
            hover_color=self._brighten(fg),
            text_color=text_color,
            text=self._wrap_label(label),
        )

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _brighten(hex_color: str, factor: float = 1.3) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _text_color_for_bg(r: int, g: int, b: int) -> str:
        def linearize(c: int) -> float:
            s = c / 255.0
            return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
        lum = 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
        return "#F0F0F0" if lum < 0.35 else "#1A1A1A"


class KeyEditDialog(ctk.CTkToplevel):
    """パッドのキー割り当て編集ダイアログ"""

    def __init__(self, parent, note: int, config: ConfigManager,
                 midi: MidiHandler, on_save):
        super().__init__(parent)
        self.note = note
        self.config = config
        self.midi = midi
        self.on_save = on_save

        self.title(f"パッド設定 (Note: {note})")
        self.geometry("420x520")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_panel"])
        self.grab_set()

        self.cfg = dict(config.get_key_config(note))
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 8}

        # ---- ラベル ----
        ctk.CTkLabel(self, text="ラベル", text_color=COLORS["text_sub"],
                     font=ctk.CTkFont(size=11)).pack(anchor="w", **pad)
        self.label_entry = ctk.CTkEntry(
            self, placeholder_text="ボタンに表示するラベル",
            fg_color=COLORS["bg_card"], border_color=COLORS["border"],
            text_color=COLORS["text_main"], width=380
        )
        self.label_entry.insert(0, self.cfg.get("label", ""))
        self.label_entry.pack(**pad)

        # ---- LED 色 ----
        ctk.CTkLabel(self, text="LED カラー", text_color=COLORS["text_sub"],
                     font=ctk.CTkFont(size=11)).pack(anchor="w", **pad)

        color_frame = ctk.CTkFrame(self, fg_color="transparent")
        color_frame.pack(anchor="w", padx=20, pady=4)

        color = self.cfg.get("color", [0, 0, 0])
        self._hex_color = self._rgb_to_hex(*color)

        self.color_preview = ctk.CTkButton(
            color_frame, text="  ", width=40, height=40,
            fg_color=self._hex_color, hover_color=self._hex_color,
            corner_radius=6, command=self._pick_color
        )
        self.color_preview.pack(side="left", padx=(0, 12))

        self.color_label = ctk.CTkLabel(
            color_frame, text=self._hex_color,
            text_color=COLORS["text_sub"], font=ctk.CTkFont(size=11)
        )
        self.color_label.pack(side="left")

        ctk.CTkButton(
            color_frame, text="消灯", width=60, height=32,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self._clear_color
        ).pack(side="left", padx=(12, 0))

        # ---- アクション種別 ----
        ctk.CTkLabel(self, text="アクション", text_color=COLORS["text_sub"],
                     font=ctk.CTkFont(size=11)).pack(anchor="w", **pad)

        self.action_var = ctk.StringVar(value=self.cfg.get("action_type", "none"))
        action_options = [f"{v}  ({k})" for k, v in ACTION_TYPES.items()]
        action_ids = list(ACTION_TYPES.keys())

        self.action_menu = ctk.CTkOptionMenu(
            self,
            values=action_options,
            variable=ctk.StringVar(
                value=action_options[action_ids.index(self.action_var.get())]
            ),
            fg_color=COLORS["bg_card"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
            width=380,
            command=lambda v: self._on_action_change(action_ids[action_options.index(v)])
        )
        self.action_menu.pack(**pad)

        # ---- パラメータフレーム ----
        self.param_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"],
                                         corner_radius=8)
        self.param_frame.pack(fill="x", padx=20, pady=8)
        self._build_param_widgets()

        # ---- 保存ボタン ----
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=16)

        ctk.CTkButton(
            btn_frame, text="キャンセル", width=140,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self.destroy
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="💾  保存", width=200,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dim"],
            command=self._save
        ).pack(side="right")

    def _build_param_widgets(self):
        for w in self.param_frame.winfo_children():
            w.destroy()

        action = self.action_var.get()
        params = self.cfg.get("params", {})

        if action == "app_launch":
            ctk.CTkLabel(self.param_frame, text="アプリのパス",
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(12, 4))
            path_frame = ctk.CTkFrame(self.param_frame, fg_color="transparent")
            path_frame.pack(fill="x", padx=12, pady=(0, 8))
            self.app_path_entry = ctk.CTkEntry(
                path_frame, placeholder_text="/Applications/Safari.app",
                fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
                text_color=COLORS["text_main"]
            )
            self.app_path_entry.insert(0, params.get("path", ""))
            self.app_path_entry.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                path_frame, text="…", width=36,
                fg_color=COLORS["bg_card"],
                command=self._browse_app
            ).pack(side="left", padx=(4, 0))

            ctk.CTkLabel(self.param_frame, text="引数（任意）",
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(4, 4))
            self.app_args_entry = ctk.CTkEntry(
                self.param_frame, placeholder_text="--flag value",
                fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
                text_color=COLORS["text_main"]
            )
            self.app_args_entry.insert(0, params.get("args", ""))
            self.app_args_entry.pack(fill="x", padx=12, pady=(0, 12))

        elif action == "hotkey":
            ctk.CTkLabel(self.param_frame, text="ショートカット  (例: ctrl+c, cmd+shift+4)",
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(12, 4))

            hotkey_row = ctk.CTkFrame(self.param_frame, fg_color="transparent")
            hotkey_row.pack(fill="x", padx=12, pady=(0, 8))

            self.hotkey_entry = ctk.CTkEntry(
                hotkey_row, placeholder_text="ctrl+c",
                fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
                text_color=COLORS["text_main"]
            )
            self.hotkey_entry.insert(0, params.get("combo", ""))
            self.hotkey_entry.pack(side="left", fill="x", expand=True)

            self._capture_btn = ctk.CTkButton(
                hotkey_row, text="⏺ 記録", width=72, height=32,
                fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
                border_width=1, border_color=COLORS["border"],
                command=self._start_hotkey_capture
            )
            self._capture_btn.pack(side="left", padx=(6, 0))

            self._capture_label = ctk.CTkLabel(
                self.param_frame,
                text="「記録」を押してからキーを押してください",
                text_color=COLORS["text_sub"], font=ctk.CTkFont(size=10)
            )
            self._capture_label.pack(anchor="w", padx=12, pady=(0, 12))
            self._capturing = False
            self._captured_keys: set = set()

        elif action == "text_type":
            ctk.CTkLabel(self.param_frame, text="入力するテキスト",
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(12, 4))
            self.text_entry = ctk.CTkTextbox(
                self.param_frame, height=80,
                fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
                text_color=COLORS["text_main"]
            )
            self.text_entry.insert("0.0", params.get("text", ""))
            self.text_entry.pack(fill="x", padx=12, pady=(0, 12))

        else:
            ctk.CTkLabel(self.param_frame, text="アクションを選択してください",
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=11)).pack(pady=20)

    # ---- ホットキーキャプチャ ----

    def _start_hotkey_capture(self):
        """キー監視モードを開始"""
        if not PYNPUT_AVAILABLE:
            self._capture_label.configure(
                text="pynput がインストールされていません", text_color=COLORS["danger"]
            )
            return
        self._capturing = True
        self._captured_keys = set()
        self._capture_btn.configure(text="⏹ 停止", fg_color=COLORS["danger"],
                                     hover_color="#B91C1C",
                                     command=self._stop_hotkey_capture)
        self._capture_label.configure(
            text="🔴 キーを押してください… (離したら自動確定)",
            text_color=COLORS["warning"]
        )
        self.hotkey_entry.delete(0, "end")

        from pynput import keyboard as kb

        self._pressed_set: set = set()

        def on_press(key):
            if not self._capturing:
                return False
            name = self._key_name(key)
            self._pressed_set.add(name)
            # プレビュー更新
            preview = "+".join(self._sort_combo(list(self._pressed_set)))
            self.after(0, lambda: self.hotkey_entry.delete(0, "end") or
                       self.hotkey_entry.insert(0, preview))

        def on_release(key):
            if not self._capturing:
                return False
            # すべてのキーが離されたら確定
            name = self._key_name(key)
            self._pressed_set.discard(name)
            if not self._pressed_set:
                self.after(0, self._stop_hotkey_capture)
                return False  # リスナー停止

        self._kb_listener = kb.Listener(on_press=on_press, on_release=on_release)
        self._kb_listener.start()

    def _stop_hotkey_capture(self):
        self._capturing = False
        if hasattr(self, "_kb_listener") and self._kb_listener.is_alive():
            self._kb_listener.stop()
        self._capture_btn.configure(
            text="⏺ 記録", fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, command=self._start_hotkey_capture
        )
        combo = self.hotkey_entry.get()
        if combo:
            self._capture_label.configure(
                text=f"✅ 確定: {combo}", text_color=COLORS["success"]
            )
        else:
            self._capture_label.configure(
                text="「記録」を押してからキーを押してください",
                text_color=COLORS["text_sub"]
            )

    @staticmethod
    def _key_name(key) -> str:
        """pynput Key/KeyCode → 文字列変換（文字化け対策済み）"""
        from pynput.keyboard import Key
        _MAP = {
            Key.ctrl_l: "ctrl", Key.ctrl_r: "ctrl",
            Key.alt_l: "alt",   Key.alt_r: "alt",
            Key.shift: "shift", Key.shift_r: "shift",
            Key.cmd: "cmd",     Key.cmd_r: "cmd",
            Key.enter: "enter", Key.space: "space",
            Key.tab: "tab",     Key.esc: "esc",
            Key.backspace: "backspace", Key.delete: "delete",
            Key.up: "up", Key.down: "down",
            Key.left: "left",   Key.right: "right",
            Key.home: "home",   Key.end: "end",
            Key.page_up: "pageup", Key.page_down: "pagedown",
            Key.insert: "insert",
            Key.caps_lock: "capslock",
            Key.num_lock: "numlock",
            Key.print_screen: "printscreen",
            Key.scroll_lock: "scrolllock",
            Key.pause: "pause",
        }
        # ファンクションキー
        for i in range(1, 13):
            fk = getattr(Key, f"f{i}", None)
            if fk:
                _MAP[fk] = f"f{i}"

        if key in _MAP:
            return _MAP[key]

        # 通常文字キー: char が printable ASCII かどうか確認
        char = getattr(key, "char", None)
        if char is not None:
            # printable ASCII (0x20–0x7E) のみ使用
            if len(char) == 1 and 0x20 <= ord(char) <= 0x7E:
                return char.lower()
            # それ以外 (制御文字・マルチバイト等) は vk から判定
            vk = getattr(key, "vk", None)
            if vk is not None:
                # 0x30-0x39: 数字キー, 0x41-0x5A: アルファベット
                if 0x41 <= vk <= 0x5A:
                    return chr(vk).lower()
                if 0x30 <= vk <= 0x39:
                    return chr(vk)
                # テンキー (0x60-0x69)
                if 0x60 <= vk <= 0x69:
                    return f"num{vk - 0x60}"

        # フォールバック: Key.xxx 形式の文字列から "Key." を除去
        return str(key).replace("Key.", "").lower()

    @staticmethod
    def _sort_combo(keys: list[str]) -> list[str]:
        mods = ["ctrl", "cmd", "alt", "shift"]
        mod_keys = [k for k in mods if k in keys]
        other = [k for k in keys if k not in mods]
        return mod_keys + other

    def _on_action_change(self, action_id: str):
        self.action_var.set(action_id)
        self._build_param_widgets()

    def _pick_color(self):
        result = colorchooser.askcolor(color=self._hex_color, title="LED カラー選択")
        if result and result[1]:
            self._hex_color = result[1]
            self.color_preview.configure(fg_color=self._hex_color,
                                          hover_color=self._hex_color)
            self.color_label.configure(text=self._hex_color)

    def _clear_color(self):
        self._hex_color = "#000000"
        self.color_preview.configure(fg_color="#000000", hover_color="#111111")
        self.color_label.configure(text="#000000")

    def _browse_app(self):
        path = filedialog.askopenfilename(title="アプリを選択")
        if path:
            self.app_path_entry.delete(0, "end")
            self.app_path_entry.insert(0, path)

    def _hex_to_rgb(self, h: str) -> list[int]:
        h = h.lstrip("#")
        return [int(h[i:i+2], 16) for i in (0, 2, 4)]

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    def _save(self):
        action = self.action_var.get()
        params = {}

        if action == "app_launch":
            params["path"] = self.app_path_entry.get()
            params["args"] = self.app_args_entry.get()
        elif action == "hotkey":
            params["combo"] = self.hotkey_entry.get()
        elif action == "text_type":
            params["text"] = self.text_entry.get("0.0", "end").rstrip("\n")

        color = self._hex_to_rgb(self._hex_color)
        new_cfg = {
            "action_type": action,
            "label": self.label_entry.get(),
            "color": color,
            "params": params
        }
        self.config.set_key_config(self.note, new_cfg)

        # LED を即座に更新
        if self.midi.is_connected():
            self.midi.set_led_rgb(self.note, *color)

        self.on_save()
        self.destroy()


class _CloseDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_quit, on_tray):
        super().__init__(parent)
        self._parent = parent  # master に頼らず親を明示保持
        self.on_quit = on_quit
        self.on_tray = on_tray

        self.title("LaunchDeck を閉じる")
        self.geometry("360x220")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_panel"])
        self.grab_set()
        self.focus_set()

        # ウィンドウ中央に配置
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - 360) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 220) // 2
        self.geometry(f"+{px}+{py}")

        self._choice = ctk.StringVar(value="tray")
        self._build()

    def _build(self):
        ctk.CTkLabel(
            self, text="閉じるときの動作を選択してください",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_main"]
        ).pack(pady=(24, 16))

        radio_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8)
        radio_frame.pack(fill="x", padx=24, pady=(0, 20))

        ctk.CTkRadioButton(
            radio_frame,
            text="  バックグラウンド継続（おすすめ）",
            variable=self._choice, value="tray",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_main"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkRadioButton(
            radio_frame,
            text="  アプリを終了",
            variable=self._choice, value="quit",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_main"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
        ).pack(anchor="w", padx=16, pady=(0, 14))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24)

        ctk.CTkButton(
            btn_frame, text="キャンセル", width=120,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self.destroy
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="OK", width=160,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dim"],
            command=self._confirm
        ).pack(side="right")

    def _confirm(self):
        choice = self._choice.get()
        self.grab_release()
        self.destroy()
        if choice == "quit":
            self._parent.after(10, self.on_quit)
        else:
            self._parent.after(10, self.on_tray)


class App:
    """メインアプリウィンドウ"""

    def __init__(self, config: ConfigManager, midi: MidiHandler,
                 action_manager: ActionManager):
        self.config = config
        self.midi = midi
        self.action_manager = action_manager
        self._stop_event = threading.Event()

        self.root = ctk.CTk()
        self.root.title("LaunchDeck")
        self.root.geometry("780x680")
        self.root.configure(fg_color=COLORS["bg_dark"])
        self.root.resizable(False, False)

        # タスクバー・ウィンドウアイコンを設定
        _ico = _resource_path("settings_file", "icon.ico")
        if _ico.exists():
            try:
                self.root.iconbitmap(str(_ico))
            except Exception:
                pass

        self.pad_buttons: dict[int, PadButton] = {}
        self._selected_note: int | None = None
        self._tray_icon = None
        self._quitting = False

        self._build_ui()
        # 接続完了を待ってから最初のステータス更新（100ms遅延）
        self.root.after(100, self._update_status)

        # ボタン点滅コールバック（押されたパッドをUIでハイライト）
        self.midi.add_button_callback(self._on_pad_pressed)

        # ✕ボタンのカスタム処理
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_request)

    def _build_ui(self):
        # ---- ヘッダー ----
        header = ctk.CTkFrame(self.root, fg_color=COLORS["bg_panel"],
                               corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="⬛ LaunchDeck",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(side="left", padx=24, pady=14)

        # 接続状態
        self.status_dot = ctk.CTkLabel(header, text="●",
                                        text_color=COLORS["danger"],
                                        font=ctk.CTkFont(size=14))
        self.status_dot.pack(side="right", padx=(0, 8), pady=14)
        self.status_label = ctk.CTkLabel(header, text="未接続",
                                          text_color=COLORS["text_sub"],
                                          font=ctk.CTkFont(size=12))
        self.status_label.pack(side="right", padx=4, pady=14)

        ctk.CTkButton(
            header, text="再接続", width=80, height=30,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self._reconnect
        ).pack(side="right", padx=12, pady=14)

        # ---- プロファイルバー ----
        profile_bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_panel"],
                                    corner_radius=0, height=44)
        profile_bar.pack(fill="x")
        profile_bar.pack_propagate(False)

        ctk.CTkLabel(profile_bar, text="プロファイル:",
                     text_color=COLORS["text_sub"],
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=16)

        self.profile_var = ctk.StringVar(value=self.config.get_active_profile())
        self.profile_menu = ctk.CTkOptionMenu(
            profile_bar,
            values=self.config.get_profiles(),
            variable=self.profile_var,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
            width=160, height=28,
            command=self._on_profile_change
        )
        self.profile_menu.pack(side="left", padx=8)

        ctk.CTkButton(
            profile_bar, text="+ 追加", width=64, height=28,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self._add_profile
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            profile_bar, text="削除", width=56, height=28,
            fg_color=COLORS["bg_card"], hover_color="#3A1515",
            border_width=1, border_color=COLORS["danger"],
            text_color=COLORS["danger"],
            command=self._remove_profile
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            profile_bar, text="LED 全更新", width=90, height=28,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_hover"],
            border_width=1, border_color=COLORS["border"],
            command=self._refresh_leds
        ).pack(side="right", padx=16)

        # ---- メインコンテンツ ----
        content = ctk.CTkFrame(self.root, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=20)

        # パッドグリッド
        grid_frame = ctk.CTkFrame(content, fg_color=COLORS["bg_panel"],
                                   corner_radius=12)
        grid_frame.pack(side="left")

        ctk.CTkLabel(grid_frame, text="Launchpad Mini MK3",
                     text_color=COLORS["text_sub"],
                     font=ctk.CTkFont(size=10)).pack(pady=(12, 6))

        pad_grid = ctk.CTkFrame(grid_frame, fg_color="transparent")
        pad_grid.pack(padx=16, pady=(0, 16))

        # 8x8 グリッドを生成（上から表示）
        for row in range(PAD_ROWS):
            for col in range(PAD_COLS):
                # 下段から MK3 のノート番号: row=0 (上) → MIDI row=7
                midi_row = 7 - row
                note = (midi_row + 1) * 10 + (col + 1)

                btn = PadButton(
                    pad_grid, note, self.config,
                    on_click=self._on_pad_click,
                )
                btn.grid(
                    row=row, column=col,
                    padx=PAD_GAP // 2, pady=PAD_GAP // 2
                )
                self.pad_buttons[note] = btn

        # ---- ヒント ----
        hint = ctk.CTkFrame(content, fg_color="transparent")
        hint.pack(side="left", fill="both", expand=True, padx=(20, 0))

        ctk.CTkLabel(hint, text="使い方",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLORS["text_main"]).pack(anchor="w")

        tips = [
            "1. パッドをクリックして動作を設定",
            "2. アプリパス or ショートカットを入力",
            "3. LED カラーで色をカスタマイズ",
        ]
        for tip in tips:
            ctk.CTkLabel(hint, text=tip,
                         text_color=COLORS["text_sub"],
                         font=ctk.CTkFont(size=12)).pack(anchor="w", pady=3)

        ctk.CTkLabel(hint, text="",).pack(pady=12)

        ctk.CTkLabel(hint, text="キー表記例",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLORS["text_main"]).pack(anchor="w")

        examples = [
            "ctrl+c  / cmd+c",
            "ctrl+shift+esc",
            "f5",
            "win+d  / cmd+space",
        ]
        for ex in examples:
            ctk.CTkLabel(hint, text=f"  {ex}",
                         text_color=COLORS["accent"],
                         font=ctk.CTkFont(size=12, family="Courier")).pack(anchor="w", pady=1)
        self.autostart_btn = ctk.CTkButton(
            profile_bar,
            text="自動起動: ON" if self.midi.is_autostart_enabled() else "自動起動: OFF",
            width=110,
            height=28,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_hover"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._toggle_autostart
        )
        self.autostart_btn.pack(side="right", padx=6)

    def _toggle_autostart(self):
        if self.midi.is_autostart_enabled():
            self.midi.disable_autostart()
        else:
            self.midi.enable_autostart()

        enabled = self.midi.is_autostart_enabled()
        self.autostart_btn.configure(
            text=f"自動起動: {'ON' if enabled else 'OFF'}"
        )

    def _shutdown(self):
        if self._quitting:
            return

        self._quitting = True

        try:
            self._stop_event.set()
        except:
            pass

        try:
            if hasattr(self.midi, "disconnect"):
                self.midi.disconnect()
        except:
            pass

        try:
            if self._tray_icon:
                self._tray_icon.stop()
                self._tray_icon = None
        except:
            pass

        try:
            self.root.after(0, self.root.destroy)
        except:
            pass

    def _on_pad_click(self, note: int):
        dialog = KeyEditDialog(
            self.root, note, self.config, self.midi,
            on_save=self._refresh_pads
        )

    def _on_pad_pressed(self, note: int):
        btn = self.pad_buttons.get(note)
        if not btn:
            return

        def flash():
            try:
                orig = btn.cget("fg_color")
                btn.configure(fg_color="#FFFFFF")

                self.root.after(120, lambda: btn.configure(fg_color=orig))
            except Exception:
                pass

        self.root.after(0, flash)

    def _refresh_pads(self):
        for btn in self.pad_buttons.values():
            btn.refresh()

    def _refresh_leds(self):
        threading.Thread(target=self.midi.refresh_leds, daemon=True).start()

    def _on_profile_change(self, value: str):
        self.config.set_active_profile(value)
        self._refresh_pads()
        self._refresh_leds()

    def _add_profile(self):
        dialog = ctk.CTkInputDialog(
            text="新しいプロファイル名を入力:",
            title="プロファイル追加"
        )
        name = dialog.get_input()
        if name:
            self.config.add_profile(name)
            self.profile_menu.configure(values=self.config.get_profiles())
            self.profile_var.set(name)
            self.config.set_active_profile(name)
            self._refresh_pads()

    def _remove_profile(self):
        current = self.profile_var.get()
        if current == "default":
            messagebox.showwarning("削除不可", "default プロファイルは削除できません")
            return
        if messagebox.askyesno("確認", f"「{current}」を削除しますか？"):
            self.config.remove_profile(current)
            profiles = self.config.get_profiles()
            self.profile_menu.configure(values=profiles)
            self.profile_var.set(self.config.get_active_profile())
            self._refresh_pads()

    def _reconnect(self):
        if getattr(self, "_midi_lock", False):
            return

        self._midi_lock = True
        threading.Thread(target=self._do_reconnect, daemon=True).start()


    def _do_reconnect(self):
        try:
            self.midi.disconnect()
        except Exception as e:
            print("disconnect error:", e)

        import time
        time.sleep(0.3)

        try:
            self.midi.connect()
        except Exception as e:
            print("connect error:", e)

        finally:
            self._midi_lock = False
            self.root.after(0, self._update_status)

    def _update_status(self):
        if self._quitting:
            return

        try:
            if self.midi.is_connected():
                self.status_dot.configure(text_color=COLORS["success"])
                dev = self.midi.get_connected_device() or ""
                short = dev[:28] + "…" if len(dev) > 28 else dev
                self.status_label.configure(text=f"接続済み  {short}")
            else:
                self.status_dot.configure(text_color=COLORS["danger"])
                devs = self.midi.list_devices()
                hint = f"  ({devs[0][:20]}…?)" if devs else "  (デバイスなし)"
                self.status_label.configure(text=f"未接続{hint}")

        except Exception as e:
            print("status error:", e)

        self.root.after(2000, self._update_status)

    # ---- 終了 / システムトレイ ----

    def _on_close_request(self):
        _CloseDialog(
            self.root,
            on_quit=self._quit_app,
            on_tray=self._minimize_to_tray
        )

    def _quit_app(self):
        """アプリを完全終了"""
        if self._quitting:
            return
        self._quitting = True

        # MIDI切断
        try:
            self.midi.disconnect()
        except Exception:
            pass

        # トレイ停止
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

        # pynput listener停止
        try:
            if hasattr(self, "_kb_listener"):
                self._kb_listener.stop()
        except Exception:
            pass

        # mainloop を抜ける（launch_deck.py の app.run() が返る）
        try:
            self.root.quit()
        except Exception:
            pass

    def _minimize_to_tray(self):
        """ウィンドウを隠してシステムトレイに常駐（タスクバーからも消す）"""
        self.root.iconify()
        self.root.withdraw()
        self._start_tray_icon()

    def _start_tray_icon(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            icon_path = _resource_path("settings_file", "icon.ico")

            if icon_path.exists():
                img = Image.open(icon_path).convert("RGBA").resize((64, 64))
            else:
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                d.ellipse((4, 4, 60, 60), fill="#6C63FF")

            def show_window(icon, item):
                icon.stop()
                self._tray_icon = None
                self.root.after(0, lambda: (
                    self.root.deiconify(),
                    self.root.lift(),
                    self.root.focus_force()
                ))

            def quit_app(icon, item):
                icon.stop()
                self._tray_icon = None
                self.root.after(0, self._shutdown)

            menu = pystray.Menu(
                pystray.MenuItem("表示", show_window),
                pystray.MenuItem("終了", quit_app),
            )

            self._tray_icon = pystray.Icon(
                "LaunchDeck", img, "LaunchDeck", menu
            )

            threading.Thread(target=self._tray_icon.run, daemon=True).start()

        except Exception as e:
            print("tray error:", e)
            self.root.deiconify()
            messagebox.showwarning(
                "トレイエラー",
                "pystray or pillow error"
            )

    def run(self):
        self.root.mainloop()
