import threading
import time
from typing import Callable

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False


SYSEX_PROGRAMMER_MODE = [0, 32, 41, 2, 13, 14, 1]
SYSEX_LED_RGB_HEADER = [0, 32, 41, 2, 13, 3]


def rgb_to_launchpad(r: int, g: int, b: int):
    return r >> 1, g >> 1, b >> 1


class MidiHandler:
    def __init__(self, config, action_manager):
        self.config = config
        self.action_manager = action_manager

        self._inport = None
        self._outport = None

        self._lock = threading.RLock()
        self._running = False

        self._button_callbacks: list[Callable] = []

    # -------------------------
    # device utils
    # -------------------------

    def list_devices(self):
        if not MIDO_AVAILABLE:
            return []
        return mido.get_input_names()

    DEVICE_KEYWORDS = ["launchpad", "lpmini", "lppro", "lpx", "novation"]

    def _find_device(self):
        saved = self.config.get_midi_device()
        devs = self.list_devices()

        if saved and saved in devs:
            return saved

        for d in devs:
            low = d.lower()
            if any(k in low for k in self.DEVICE_KEYWORDS):
                return d

        return None

    # -------------------------
    # connect / disconnect
    # -------------------------

    def _find_output(self, input_name: str):
        outs = mido.get_output_names()
        low = input_name.lower()

        # 1. 完全一致
        for o in outs:
            if o == input_name:
                return o

        # 2. 相互部分一致
        for o in outs:
            ol = o.lower()
            if low in ol or ol in low:
                return o

        # 3. Launchpad系フォールバック
        for o in outs:
            ol = o.lower()
            if any(k in ol for k in self.DEVICE_KEYWORDS):
                return o

        return None

    def connect(self):
        if not MIDO_AVAILABLE:
            print("[MIDI] mido not installed")
            return False

        name = self._find_device()
        if not name:
            print("[MIDI] no device found")
            return False

        try:
            with self._lock:
                self.disconnect()

                print(f"[MIDI] connect input: {name}")
                self._inport = mido.open_input(name, callback=self._on_msg)

                # ★ここが修正ポイント
                out = self._find_output(name)

                if out:
                    print(f"[MIDI] connect output: {out}")
                    self._outport = mido.open_output(out)
                else:
                    print("[MIDI] WARNING: output not found (LED disabled)")
                    self._outport = None

                # ★ MK3安定化シーケンス
                self._send_sysex(SYSEX_PROGRAMMER_MODE)
                time.sleep(0.15)

                self.clear_all_leds()
                time.sleep(0.05)

                self._restore_leds()

                print("[MIDI] connected")
                return True

        except Exception as e:
            print("[MIDI] connect error:", e)
            self._cleanup()
            return False

    def disconnect(self):
        with self._lock:
            self._cleanup()

    def _cleanup(self):
        try:
            if self._outport:
                self.clear_all_leds()
        except:
            pass

        try:
            if self._inport:
                self._inport.close()
        except:
            pass

        try:
            if self._outport:
                self._outport.close()
        except:
            pass

        self._inport = None
        self._outport = None

    def is_connected(self):
        return self._inport is not None

    def get_connected_device(self):
        if self._inport:
            return getattr(self._inport, "name", None)
        return None

    # -------------------------
    # input
    # -------------------------

    def _on_msg(self, msg):
        note = None

        if msg.type == "note_on" and msg.velocity > 0:
            note = msg.note
        elif msg.type == "control_change":
            note = msg.control

        if note is None:
            return

        self.action_manager.trigger(note)

        for cb in self._button_callbacks:
            try:
                cb(note)
            except:
                pass

    def add_button_callback(self, cb):
        self._button_callbacks.append(cb)

    # -------------------------
    # LED
    # -------------------------

    def set_led_rgb(self, note, r, g, b):
        if not self._outport:
            return

        lr, lg, lb = rgb_to_launchpad(r, g, b)

        try:
            with self._lock:
                if not self._outport:
                    return

                msg = mido.Message(
                    "sysex",
                    data=SYSEX_LED_RGB_HEADER + [3, int(note), lr, lg, lb]
                )

                self._outport.send(msg)

        except Exception as e:
            print("[LED] error:", e)

    def clear_all_leds(self):
        if not self._outport:
            return

        try:
            with self._lock:
                self._send_sysex(SYSEX_PROGRAMMER_MODE)
        except:
            pass

    def _send_sysex(self, data):
        if not self._outport:
            return

        try:
            self._outport.send(mido.Message("sysex", data=data))
        except Exception as e:
            print(f"[SysEx] error: {e}")

    def _restore_leds(self):
        for note_str, cfg in self.config.get_all_keys().items():
            note = int(note_str)
            color = cfg.get("color", [0, 0, 0])
            if any(color):
                self.set_led_rgb(note, *color)

    def refresh_leds(self):
        self.clear_all_leds()
        time.sleep(0.05)
        self._restore_leds()

    def _startup_folder(self):
        import os
        return os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )
    
    def enable_autostart(self):
        import sys
        from pathlib import Path
        from win32com.client import Dispatch

        startup = self._startup_folder()
        shortcut_path = Path(startup) / "LaunchDeck.lnk"

        target = sys.executable
        working_dir = str(Path(sys.executable).parent)

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = working_dir
        shortcut.save()

    def disable_autostart(self):
        from pathlib import Path

        startup = self._startup_folder()
        shortcut_path = Path(startup) / "LaunchDeck.lnk"

        if shortcut_path.exists():
            shortcut_path.unlink()

    def is_autostart_enabled(self):
        from pathlib import Path

        startup = self._startup_folder()
        return (Path(startup) / "LaunchDeck.lnk").exists()

    # -------------------------
    # auto reconnect loop
    # -------------------------

    def watch(self):
        self._running = True

        while self._running:
            time.sleep(2)

            if not self.is_connected():
                print("[MIDI] reconnect...")
                self.connect()