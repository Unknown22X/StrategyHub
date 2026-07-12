"""Command-line entry point for the engine service."""

import argparse

import uvicorn

from rangebot.engine.api import create_app
from rangebot.engine.exchange import UnavailableGateIoAdapter, configured_gate_adapter
from rangebot.engine.market import GatePublicMarketProvider


LOCALHOST = "127.0.0.1"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RangeBot engine.")
    parser.add_argument(
        "--database-url",
        default="sqlite:///runtime/rangebot.db",
        help="SQLAlchemy database URL for persisted runtime state.",
    )
    parser.add_argument(
        "--enable-order-submission",
        action="store_true",
        help="Enable the exchange order transport boundary; Live remains locked in-app.",
    )
    parser.add_argument("--host", default=LOCALHOST)
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--mode",
        choices=("paper", "testnet", "live"),
        default="paper",
        help="Operating mode. Live requires an explicit PostgreSQL URL.",
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
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.host != LOCALHOST:
        raise SystemExit("RangeBot engine API must bind to 127.0.0.1 only.")
    if arguments.mode != "paper" and not arguments.database_url.startswith(
        "postgresql"
    ):
        raise SystemExit(
            "Testnet and Live modes require an explicit local PostgreSQL database URL."
        )
    adapter = (
        UnavailableGateIoAdapter()
        if arguments.mode == "paper"
        else configured_gate_adapter(
            arguments.mode,
            enable_network=arguments.enable_read_only_exchange,
            enable_order_submission=(
                arguments.enable_read_only_exchange
                and arguments.enable_order_submission
            ),
        )
    )
    uvicorn.run(
        create_app(
            arguments.database_url,
            public_market_provider=GatePublicMarketProvider(),
            exchange_adapter=adapter,
            restored_state=arguments.restored_state,
        ),
        host=LOCALHOST,
        port=arguments.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
