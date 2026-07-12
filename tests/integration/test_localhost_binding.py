import sys

import pytest

from rangebot.engine import main


def test_engine_rejects_non_localhost_binding(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["rangebot-engine", "--host", "0.0.0.0"])

    with pytest.raises(SystemExit, match="127.0.0.1"):
        main.main()
