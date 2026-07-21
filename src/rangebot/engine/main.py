"""Command-line entry point for the engine service."""

import argparse
from pathlib import Path

import uvicorn

from rangebot.engine.api import create_app
from rangebot.engine.credential_adapter import CredentialReloadingGateIoAdapter
from rangebot.engine.exchange import UnavailableGateIoAdapter
from rangebot.engine.gate_websocket import (
    GateFuturesRestSnapshotProvider,
    GateFuturesWebSocketService,
    GateMarketTarget,
    MarketSubscriptionRegistry,
)
from rangebot.engine.instance_lock import (
    EngineAlreadyRunningError,
    EngineInstanceLock,
    engine_lock_path,
)
from rangebot.engine.market import GatePublicMarketProvider
from rangebot.engine.market_data_manager import MarketDataManager
from rangebot.engine.paths import default_database_url


LOCALHOST = "127.0.0.1"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RangeBot engine.")
    parser.add_argument(
        "--database-url",
        default=default_database_url(),
        help="SQLAlchemy database URL for persisted runtime state.",
    )
    parser.add_argument(
        "--enable-order-submission",
        action="store_true",
        help="Enable the exchange order transport boundary; risk checks remain mandatory.",
    )
    parser.add_argument("--host", default=LOCALHOST)
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--mode",
        choices=("paper", "testnet", "live"),
        default="live",
        help="Operating mode. All modes use the local application database by default.",
    )
    parser.add_argument(
        "--restored-state",
        action="store_true",
        help="Invalidate exchange readiness after a database restore.",
    )
    parser.add_argument(
        "--enable-read-only-exchange",
        action="store_true",
        help="Allow signed read-only reconciliation. Order submission remains disabled.",
    )
    parser.add_argument(
        "--instance-lock-file",
        type=Path,
        default=None,
        help="Override the duplicate-engine lock path for service tests or diagnostics.",
    )
    parser.add_argument(
        "--enable-public-websocket",
        action="store_true",
        help="Enable Gate public futures market-data WebSocket subscriptions.",
    )
    parser.add_argument(
        "--enable-private-websocket",
        action="store_true",
        help="Enable authenticated Gate futures account notifications and REST reconciliation.",
    )
    parser.add_argument(
        "--market-symbol",
        action="append",
        default=[],
        help="Pin a public market symbol even when no saved strategy references it.",
    )
    parser.add_argument(
        "--market-timeframe-minutes",
        action="append",
        type=int,
        default=[],
        help="Subscribe pinned symbols to a supported Gate candle timeframe.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.host != LOCALHOST:
        raise SystemExit("RangeBot engine API must bind to 127.0.0.1 only.")
    adapter = (
        UnavailableGateIoAdapter()
        if arguments.mode == "paper"
        else CredentialReloadingGateIoAdapter(
            arguments.mode,
            enable_network=arguments.enable_read_only_exchange,
            enable_order_submission=(
                arguments.enable_read_only_exchange
                and arguments.enable_order_submission
            ),
        )
    )
    market_data = MarketDataManager()
    market_subscription_registry: MarketSubscriptionRegistry | None = None
    market_websocket_service: GateFuturesWebSocketService | None = None
    if arguments.enable_public_websocket:
        websocket_environment = (
            "testnet" if arguments.mode == "testnet" else "live"
        )
        pinned_symbols = tuple(
            dict.fromkeys(
                symbol.upper().replace("/", "_")
                for symbol in (arguments.market_symbol or ["BTC_USDT"])
            )
        )
        pinned_targets = {
            GateMarketTarget(symbol) for symbol in pinned_symbols
        }
        for symbol in pinned_symbols:
            for timeframe in arguments.market_timeframe_minutes:
                pinned_targets.add(GateMarketTarget(symbol, timeframe))
        market_subscription_registry = MarketSubscriptionRegistry(
            tuple(pinned_targets)
        )
        rest_snapshot = GateFuturesRestSnapshotProvider(websocket_environment)
        market_websocket_service = GateFuturesWebSocketService(
            environment=websocket_environment,
            market_data=market_data,
            subscriptions=market_subscription_registry,
            rest_snapshot=rest_snapshot.snapshot,
        )
    lock_path = arguments.instance_lock_file or engine_lock_path(arguments.port)
    try:
        with EngineInstanceLock(lock_path):
            uvicorn.run(
                create_app(
                    arguments.database_url,
                    public_market_provider=GatePublicMarketProvider(),
                    exchange_adapter=adapter,
                    exchange_adapter_mode=(
                        arguments.mode
                        if arguments.mode in {"testnet", "live"}
                        else None
                    ),
                    restored_state=arguments.restored_state,
                    market_data_manager=market_data,
                    market_subscription_registry=market_subscription_registry,
                    market_websocket_service=market_websocket_service,
                    enable_private_websocket=arguments.enable_private_websocket,
                ),
                host=LOCALHOST,
                port=arguments.port,
                log_level="warning",
            )
    except EngineAlreadyRunningError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
