"""Command-line entry point for the engine service."""

import argparse

import uvicorn

from rangebot.engine.api import create_app
from rangebot.engine.market import GatePublicMarketProvider


LOCALHOST = "127.0.0.1"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RangeBot engine.")
    parser.add_argument(
        "--database-url",
        default="sqlite:///runtime/rangebot.db",
        help="SQLAlchemy database URL for persisted runtime state.",
    )
    parser.add_argument("--host", default=LOCALHOST)
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--mode",
        choices=("paper", "testnet", "live"),
        default="paper",
        help="Operating mode. Live requires an explicit PostgreSQL URL.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.host != LOCALHOST:
        raise SystemExit("RangeBot engine API must bind to 127.0.0.1 only.")
    if arguments.mode == "live" and not arguments.database_url.startswith("postgresql"):
        raise SystemExit("Live mode requires an explicit local PostgreSQL database URL.")
    uvicorn.run(
        create_app(
            arguments.database_url, public_market_provider=GatePublicMarketProvider()
        ),
        host=LOCALHOST,
        port=arguments.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
