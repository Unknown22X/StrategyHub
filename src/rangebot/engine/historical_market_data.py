"""Gate-only public contract universe and completed historical candle loading."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

import httpx

from rangebot.domain.discovery import DiscoveryMarketContract
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.engine.gate_websocket import LIVE_REST_URL, TESTNET_REST_URL


GateHistoricalEnvironment = Literal["live", "testnet"]
UtcClock = Callable[[], datetime]
MAX_CANDLES_PER_REQUEST = 2000
_TIMEFRAME_INTERVALS: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    240: "4h",
    480: "8h",
    1440: "1d",
    10080: "7d",
}


class GateHistoricalMarketDataProvider:
    """Load sanitized public Gate futures data without credentials or order access."""

    warning_ar = (
        "تم تقدير التمويل التاريخي باستخدام القيمة الاسمية عند الدخول؛ "
        "قد يختلف المبلغ الفعلي قليلاً مع تغير قيمة المركز عند وقت التمويل."
    )

    def __init__(
        self,
        environment: GateHistoricalEnvironment,
        *,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 15.0,
        clock: UtcClock | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Gate historical REST timeout must be positive.")
        self._base_url = (
            base_url
            or (LIVE_REST_URL if environment == "live" else TESTNET_REST_URL)
        ).rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]:
        """Return active USDT perpetual contracts ranked by Gate quote volume."""
        if minimum_quote_volume < 0:
            raise ValueError("Minimum quote volume cannot be negative.")
        if maximum_contracts is not None and maximum_contracts < 1:
            raise ValueError("Maximum contract count must be positive.")

        contract_payload = self._get_json("contracts")
        ticker_payload = self._get_json("tickers")
        if not isinstance(contract_payload, list) or not isinstance(ticker_payload, list):
            raise LookupError("Gate contract universe response is malformed.")

        active_names = {
            str(item.get("name"))
            for item in contract_payload
            if isinstance(item, dict)
            and item.get("name")
            and not bool(item.get("in_delisting", False))
            and str(item.get("status", "trading")).lower()
            not in {"delisted", "disabled", "closed"}
        }
        contracts: list[DiscoveryMarketContract] = []
        for ticker in ticker_payload:
            if not isinstance(ticker, dict):
                continue
            symbol = str(ticker.get("contract", ""))
            if symbol not in active_names:
                continue
            last_price = _optional_positive_decimal(ticker.get("last"))
            if last_price is None:
                continue
            quote_volume = _optional_nonnegative_decimal(
                ticker.get("volume_24h_quote", ticker.get("volume_24h"))
            ) or Decimal("0")
            if quote_volume < minimum_quote_volume:
                continue
            contracts.append(
                DiscoveryMarketContract(
                    symbol=symbol,
                    last_price=last_price,
                    mark_price=_optional_positive_decimal(ticker.get("mark_price")),
                    index_price=_optional_positive_decimal(ticker.get("index_price")),
                    best_bid=_optional_positive_decimal(ticker.get("highest_bid")),
                    best_ask=_optional_positive_decimal(ticker.get("lowest_ask")),
                    volume_24h_quote=quote_volume,
                    funding_rate=_optional_decimal(ticker.get("funding_rate")),
                    change_percentage=_optional_decimal(
                        ticker.get("change_percentage")
                    ),
                    high_24h=_optional_positive_decimal(ticker.get("high_24h")),
                    low_24h=_optional_positive_decimal(ticker.get("low_24h")),
                )
            )
        contracts.sort(
            key=lambda contract: (-contract.volume_24h_quote, contract.symbol)
        )
        if maximum_contracts is not None:
            contracts = contracts[:maximum_contracts]
        return tuple(contracts)

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]:
        """Load the latest completed candles, requesting one extra for the live candle."""
        interval = self._interval(timeframe_minutes)
        if limit < 1 or limit >= MAX_CANDLES_PER_REQUEST:
            raise ValueError("Latest candle limit must be between 1 and 1999.")
        payload = self._get_json(
            "candlesticks",
            params={
                "contract": symbol,
                "interval": interval,
                "limit": str(limit + 1),
                "timezone": "utc0",
            },
        )
        candles = self._parse_candles(payload, timeframe_minutes)
        now = _utc(self._clock())
        completed = [candle for candle in candles if candle.closed_at <= now]
        return tuple(completed[-limit:])

    def candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedCandle, ...]:
        """Load an exclusive-end UTC range, paginated within Gate's 2,000-point cap."""
        interval_name = self._interval(timeframe_minutes)
        interval = timedelta(minutes=timeframe_minutes)
        start = _utc(start)
        end = _utc(end)
        if end <= start:
            raise ValueError("Historical candle end must be after start.")

        now = _utc(self._clock())
        last_requested_open = end - interval
        if last_requested_open < start:
            return ()
        cursor = start
        by_opened_at: dict[datetime, NormalizedCandle] = {}
        maximum_span = interval * (MAX_CANDLES_PER_REQUEST - 1)
        while cursor <= last_requested_open:
            chunk_end = min(cursor + maximum_span, last_requested_open)
            payload = self._get_json(
                "candlesticks",
                params={
                    "contract": symbol,
                    "interval": interval_name,
                    "from": str(int(cursor.timestamp())),
                    "to": str(int(chunk_end.timestamp())),
                    "timezone": "utc0",
                },
            )
            for candle in self._parse_candles(payload, timeframe_minutes):
                if (
                    start <= candle.opened_at < end
                    and candle.closed_at <= now
                ):
                    by_opened_at[candle.opened_at] = candle
            cursor = chunk_end + interval
        return tuple(by_opened_at[key] for key in sorted(by_opened_at))

    def funding_cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal:
        """Estimate signed funding cash flow from Gate historical rates.

        Positive values are costs deducted from P&L. Negative values are credits.
        """
        if direction not in {"long", "short"}:
            raise ValueError("Funding direction must be long or short.")
        if notional < 0:
            raise ValueError("Funding notional cannot be negative.")
        entered_at = _utc(entered_at)
        exited_at = _utc(exited_at)
        if exited_at <= entered_at or notional == 0:
            return Decimal("0")
        rates = self.funding_rates(
            symbol,
            start=entered_at,
            end=exited_at,
        )
        direction_sign = Decimal("1") if direction == "long" else Decimal("-1")
        return notional * sum((rate for _, rate in rates), Decimal("0")) * direction_sign

    def cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal:
        return self.funding_cost(
            symbol=symbol,
            direction=direction,
            notional=notional,
            entered_at=entered_at,
            exited_at=exited_at,
        )

    def funding_rates(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[tuple[datetime, Decimal], ...]:
        """Load all Gate funding events in an exclusive-start, inclusive-end window."""
        start = _utc(start)
        end = _utc(end)
        if end <= start:
            return ()
        start_epoch = int(start.timestamp())
        cursor_end = int(end.timestamp())
        records: dict[int, Decimal] = {}
        limit = 1000
        while cursor_end > start_epoch:
            payload = self._get_json(
                "funding_rate",
                params={
                    "contract": symbol,
                    "limit": str(limit),
                    "from": str(start_epoch),
                    "to": str(cursor_end),
                },
            )
            if not isinstance(payload, list):
                raise LookupError("Gate funding-rate response is malformed.")
            timestamps: list[int] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                try:
                    timestamp = int(item["t"])
                    rate = _decimal(item["r"])
                except (KeyError, TypeError, ValueError) as error:
                    raise LookupError("Gate funding-rate record is invalid.") from error
                if start_epoch < timestamp <= int(end.timestamp()):
                    records[timestamp] = rate
                    timestamps.append(timestamp)
            if len(payload) < limit or not timestamps:
                break
            earliest = min(timestamps)
            if earliest >= cursor_end:
                break
            cursor_end = earliest - 1
        return tuple(
            (datetime.fromtimestamp(timestamp, UTC), records[timestamp])
            for timestamp in sorted(records)
        )

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> object:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout_seconds,
                headers={
                    "Accept": "application/json",
                    "X-Gate-Size-Decimal": "1",
                },
            ) as client:
                response = client.get(f"{self._base_url}/{path}", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ConnectionError(f"Gate historical REST request failed: {path}") from error

    @staticmethod
    def _interval(timeframe_minutes: int) -> str:
        try:
            return _TIMEFRAME_INTERVALS[timeframe_minutes]
        except KeyError as error:
            supported = ", ".join(str(value) for value in _TIMEFRAME_INTERVALS)
            raise ValueError(
                f"Unsupported Gate historical timeframe {timeframe_minutes}; "
                f"supported minute values: {supported}."
            ) from error

    @staticmethod
    def _parse_candles(
        payload: object,
        timeframe_minutes: int,
    ) -> list[NormalizedCandle]:
        if not isinstance(payload, list):
            raise LookupError("Gate historical candlestick response is malformed.")
        interval = timedelta(minutes=timeframe_minutes)
        candles: list[NormalizedCandle] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                opened_at = datetime.fromtimestamp(int(item["t"]), UTC)
                candle = NormalizedCandle(
                    opened_at=opened_at,
                    closed_at=opened_at + interval,
                    open=_required_positive_decimal(item.get("o"), "open"),
                    high=_required_positive_decimal(item.get("h"), "high"),
                    low=_required_positive_decimal(item.get("l"), "low"),
                    close=_required_positive_decimal(item.get("c"), "close"),
                    volume=_optional_nonnegative_decimal(item.get("v"))
                    or Decimal("0"),
                    closed=True,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise LookupError("Gate historical candle contains invalid fields.") from error
            candles.append(candle)
        candles.sort(key=lambda candle: candle.opened_at)
        return candles


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Historical market timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _decimal(value: object) -> Decimal:
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Gate numeric field is invalid.") from error
    if not numeric.is_finite():
        raise ValueError("Gate numeric field must be finite.")
    return numeric


def _required_positive_decimal(value: object, field: str) -> Decimal:
    numeric = _decimal(value)
    if numeric <= 0:
        raise ValueError(f"Gate candle {field} must be positive.")
    return numeric


def _optional_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return _decimal(value)


def _optional_positive_decimal(value: object) -> Decimal | None:
    numeric = _optional_decimal(value)
    return numeric if numeric is not None and numeric > 0 else None


def _optional_nonnegative_decimal(value: object) -> Decimal | None:
    numeric = _optional_decimal(value)
    return numeric if numeric is not None and numeric >= 0 else None
