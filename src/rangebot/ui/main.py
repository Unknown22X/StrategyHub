"""Command-line entry point for the desktop control UI."""

import argparse
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from rangebot.ui.client import EngineClient
from rangebot.ui.engine_bootstrap import start_bundled_engine_if_needed
from rangebot.ui.window import RangeBotWindow


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RangeBot control UI.")
    parser.add_argument("--engine-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Refresh once and exit; intended for lifecycle verification.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.once:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    start_bundled_engine_if_needed()
    application = QApplication([])
    client = EngineClient(arguments.engine_url)
    window = RangeBotWindow(client.fetch_runtime_state, engine_client=client)
    window.show()
    if arguments.once:
        exit_code = 1

        def exit_when_connected() -> None:
            nonlocal exit_code
            if window.is_connected:
                exit_code = 0
                application.quit()
            else:
                QTimer.singleShot(50, exit_when_connected)

        QTimer.singleShot(50, exit_when_connected)
        QTimer.singleShot(10_000, application.quit)
        application.exec()
        raise SystemExit(exit_code)
    raise SystemExit(application.exec())


if __name__ == "__main__":
    main()
