import threading
from core.config_manager import ConfigManager
from core.midi_handler import MidiHandler
from core.action_manager import ActionManager
from ui.app import App


def main():
    config = ConfigManager()
    action_manager = ActionManager(config)
    midi_handler = MidiHandler(config, action_manager)

    app = App(config, midi_handler, action_manager)

    midi_thread = threading.Thread(
        target=midi_handler.watch,
        daemon=True
    )
    midi_thread.start()

    app.run()


if __name__ == "__main__":
    main()