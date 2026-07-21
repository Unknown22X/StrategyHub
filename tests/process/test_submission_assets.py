from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_submission_documentation_and_public_brand_are_present() -> None:
    required = (
        "README.md",
        "DEMO.md",
        "SUBMISSION_CHECKLIST.md",
        "BUILD_WEEK_CHANGES.md",
        "KNOWN_LIMITATIONS.md",
        "USER_GUIDE.md",
    )
    for relative_path in required:
        path = ROOT / relative_path
        assert path.is_file(), f"Missing submission asset: {relative_path}"
        assert path.read_text(encoding="utf-8").strip()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "USER_GUIDE.md").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    installer = (ROOT / "deploy" / "RangeBot.iss").read_text(encoding="utf-8")

    assert readme.startswith("# StrategyHub")
    assert "built to help my dad" in readme
    assert "no Live Credentials, Live Orders" in readme
    assert "A fresh engine starts in **Paper**" in guide
    assert "does not require Gate.io API Credentials" in guide
    assert "<h1>StrategyHub</h1>" in app
    assert "<strong>StrategyHub</strong>" in app
    assert "StrategyHub — safe trading strategy operations" in index
    assert 'Source: "..\\README.md"' in installer
    assert 'Source: "..\\KNOWN_LIMITATIONS.md"' in installer


def test_private_runtime_artifact_patterns_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        "credentials/",
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
    ):
        assert pattern in gitignore
