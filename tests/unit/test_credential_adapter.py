from rangebot.engine.credential_adapter import CredentialReloadingGateIoAdapter
from rangebot.engine.credentials import StoredGateCredentials
from rangebot.engine.exchange import MockGateIoAdapter


def _value(index: int) -> str:
    return "".join(chr(code + index) for code in (102, 105, 120, 116, 117, 114, 101))


def test_adapter_refreshes_after_save_replace_and_remove_without_engine_restart() -> None:
    current: list[StoredGateCredentials | None] = [None]
    created: list[MockGateIoAdapter] = []

    def provider(_: str) -> StoredGateCredentials | None:
        return current[0]

    def factory(_: str) -> MockGateIoAdapter:
        adapter = MockGateIoAdapter()
        created.append(adapter)
        return adapter

    adapter = CredentialReloadingGateIoAdapter(
        "live",
        enable_network=True,
        enable_order_submission=True,
        credentials_provider=provider,
        adapter_factory=factory,
    )

    unavailable = adapter.reconcile("live")
    current[0] = StoredGateCredentials(_value(0), _value(1))
    first = adapter.reconcile("live")
    same = adapter.reconcile("live")
    current[0] = StoredGateCredentials(_value(0), _value(2))
    replaced = adapter.reconcile("live")
    current[0] = None
    removed = adapter.reconcile("live")

    assert unavailable.reconciliation_error is not None
    assert first.reconciliation_error is None
    assert same.reconciliation_error is None
    assert replaced.reconciliation_error is None
    assert removed.reconciliation_error is not None
    assert len(created) == 2
