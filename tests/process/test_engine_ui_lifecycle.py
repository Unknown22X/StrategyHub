import os
import subprocess
import sys
import time

import httpx


def _wait_for_engine(port: int) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.2)
            if response.is_success:
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError("Engine did not become available.")


def test_ui_exit_leaves_engine_running_and_reconnects(tmp_path) -> None:
    port = 18765
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    engine = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "rangebot.engine.main",
            "--database-url",
            database_url,
            "--port",
            str(port),
        ],
        env=environment,
    )
    try:
        first_snapshot = _wait_for_engine(port)
        completed_ui = subprocess.run(
            [
                sys.executable,
                "-m",
                "rangebot.ui.main",
                "--engine-url",
                f"http://127.0.0.1:{port}",
                "--once",
            ],
            env=environment,
            check=False,
            timeout=10,
        )
        remaining_engine = httpx.get(
            f"http://127.0.0.1:{port}/v1/runtime-state", timeout=1
        )

        assert completed_ui.returncode == 0
        assert remaining_engine.is_success

        engine.terminate()
        engine.wait(timeout=10)
        restarted_engine = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "rangebot.engine.main",
                "--database-url",
                database_url,
                "--port",
                str(port),
            ],
            env=environment,
        )
        engine = restarted_engine
        fresh_snapshot = _wait_for_engine(port)

        assert fresh_snapshot["state_revision"] == first_snapshot["state_revision"] + 1
    finally:
        if engine.poll() is None:
            engine.terminate()
            engine.wait(timeout=10)


def test_duplicate_engine_process_is_rejected_without_stopping_owner(
    tmp_path,
) -> None:
    port = 18767
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    lock_path = tmp_path / "engine.lock"
    environment = os.environ.copy()
    environment["RANGEBOT_HOME"] = str(tmp_path / "RangeBot")
    command = [
        sys.executable,
        "-m",
        "rangebot.engine.main",
        "--database-url",
        database_url,
        "--port",
        str(port),
        "--instance-lock-file",
        str(lock_path),
    ]
    owner = subprocess.Popen(command, env=environment)
    try:
        _wait_for_engine(port)
        duplicate = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        owner_health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)

        assert duplicate.returncode != 0
        assert "already running" in (duplicate.stdout + duplicate.stderr)
        assert owner_health.is_success
        assert owner.poll() is None
    finally:
        if owner.poll() is None:
            owner.terminate()
            owner.wait(timeout=10)


def test_ui_reconnects_when_engine_becomes_available(tmp_path) -> None:
    port = 18766
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    ui = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "rangebot.ui.main",
            "--engine-url",
            f"http://127.0.0.1:{port}",
            "--startup-timeout",
            "12",
            "--once",
        ],
        env=environment,
    )
    time.sleep(0.3)
    engine = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "rangebot.engine.main",
            "--database-url",
            database_url,
            "--port",
            str(port),
        ],
        env=environment,
    )
    try:
        assert ui.wait(timeout=20) == 0
        snapshot = _wait_for_engine(port)
        assert snapshot["lifecycle"] == "running"
    finally:
        if ui.poll() is None:
            ui.terminate()
            ui.wait(timeout=10)
        if engine.poll() is None:
            engine.terminate()
            engine.wait(timeout=10)
