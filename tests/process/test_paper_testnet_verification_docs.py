from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "PAPER_TESTNET_VERIFICATION.md"


def test_paper_testnet_guide_covers_full_safe_lifecycle_and_limitations() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    assert "test_p0_5_trading_verification.py" in text
    assert "POST /v1/runtime/environment/switch" in text
    assert "POST /v1/exchange/testnet/credentials/test" in text
    assert "POST /v1/exchange/testnet/reconcile" in text
    assert "GET /v1/exchange/testnet/reconciliation" in text
    assert "POST /v1/manual-orders/preview" in text
    assert "POST /v1/manual-orders" in text
    assert "GET /v1/exchange/testnet/state" in text
    assert "POST /v1/exchange/testnet/protection/check" in text
    assert "POST /v1/exchange/testnet/close" in text
    assert "Take Profit" in text
    assert "Stop Loss" in text
    assert "CLOSE POSITION" in text
    assert "uses_real_funds=false" in text
    assert "no Live key, Live Order, or real funds were used" in text
    assert "لم تُستخدم" in text
    assert "Gate.io Testnet credentials حقيقية" in text
