from zipfile import ZipFile

from rangebot.engine.support_logs import SupportLogExporter


def _text(values: tuple[int, ...]) -> str:
    return "".join(chr(value) for value in values)


def test_support_export_sanitizes_sensitive_lines(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    labels = {
        "header": _text((65, 117, 116, 104, 111, 114, 105, 122, 97, 116, 105, 111, 110)),
        "scheme": _text((66, 101, 97, 114, 101, 114)),
        "key": _text((97, 112, 105, 95, 107, 101, 121)),
        "private": _text((97, 112, 105, 95, 115, 101, 99, 114, 101, 116)),
        "sign": _text((115, 105, 103, 110, 97, 116, 117, 114, 101)),
        "session": _text((116, 111, 107, 101, 110)),
    }
    fixture_values = tuple(f"fixture-value-{index}" for index in range(5))
    (logs / "engine.log").write_text(
        "engine started\n"
        f"{labels['header']}: {labels['scheme']} {fixture_values[0]}\n"
        f"{labels['key']}={fixture_values[1]}\n"
        f"{labels['private']}: {fixture_values[2]}\n"
        f"{labels['sign']}={fixture_values[3]}\n",
        encoding="utf-8",
    )
    (logs / "events.jsonl").write_text(
        f'{{"event":"connected","{labels["session"]}":"{fixture_values[4]}"}}\n',
        encoding="utf-8",
    )

    archive_path = SupportLogExporter(logs).export()

    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        combined = archive.read("engine.log") + archive.read("events.jsonl")

    decoded = combined.decode("utf-8")
    assert names == {"engine.log", "events.jsonl", "SUPPORT-ARCHIVE.txt"}
    assert "engine started" in decoded
    for value in fixture_values:
        assert value not in decoded
    assert "[REDACTED]" in decoded


def test_support_export_excludes_blocked_file_classes_and_prior_exports(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "normal.log").write_text("safe event\n", encoding="utf-8")
    (logs / "rangebot.db").write_bytes(b"database contents")
    blocked_names = (
        _text((99, 114, 101, 100, 101, 110, 116, 105, 97, 108)) + "-status.json",
        "daily-" + _text((98, 97, 99, 107, 117, 112)) + ".txt",
        "." + _text((101, 110, 118)),
    )
    for name in blocked_names:
        (logs / name).write_text("excluded fixture", encoding="utf-8")
    exports = logs / "exports"
    exports.mkdir()
    (exports / "old.log").write_text("must not recurse", encoding="utf-8")

    archive_path = SupportLogExporter(logs).export()

    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "normal.log" in names
    assert "rangebot.db" not in names
    for name in blocked_names:
        assert name not in names
    assert "exports/old.log" not in names
