from datetime import UTC, datetime
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from rangebot.domain.strategy_workflow import (
    StrategyRiskDefaults,
    StrategySetupDefaults,
)
from rangebot.engine.strategy_workflow import (
    BotDeploymentRecord,
    StrategyCoinSetupRecord,
    StrategyCoinSetupVersionRecord,
    StrategySetupApprovalRecord,
    StrategyTemplateRecord,
    StrategyTemplateVersionRecord,
)


def authorize_existing_strategy_instance(app, instance_id: str) -> str:
    """Attach a complete explicit workflow fixture to an existing instance.

    Legacy integration tests often need a running instance but are not testing the
    product workflow itself. The fixture mirrors the production migration shape:
    template, pinned version, coin setup, setup version, approval, and deployment.
    """

    instance = app.state.strategy_instance_repository.get(instance_id)
    deployment_id = str(uuid4())
    setup_id = str(uuid4())
    template_id = str(uuid4())
    now = datetime.now(UTC)
    defaults = StrategySetupDefaults(
        risk=StrategyRiskDefaults(
            requested_margin=instance.requested_margin,
            requested_leverage=instance.requested_leverage,
        )
    )
    defaults_json = defaults.model_dump_json()
    configuration_json = json.dumps(
        instance.configuration,
        sort_keys=True,
        separators=(",", ":"),
    )
    setup_snapshot = {
        "setup_id": setup_id,
        "template_id": template_id,
        "template_revision": 1,
        "runtime_instance_id": instance_id,
        "symbol": instance.symbol,
        "timeframe_minutes": instance.timeframe_minutes,
        "direction": instance.direction,
        "configuration_overrides": {},
        "setup_defaults_override": None,
    }
    deployment_snapshot = {
        "setup_id": setup_id,
        "setup_revision": 1,
        "template_id": template_id,
        "template_revision": 1,
        "strategy_type_id": instance.type_id,
        "strategy_version": "test-fixture",
        "exchange": "gateio",
        "market_type": "usdt_perpetual",
        "symbol": instance.symbol,
        "quote_currency": "USDT",
        "timeframe_minutes": instance.timeframe_minutes,
        "direction": instance.direction,
        "configuration": instance.configuration,
        "setup_defaults": defaults.model_dump(mode="json"),
        "approved_backtest_id": "test-fixture-backtest",
    }

    engine = app.state.strategy_workflow_repository._database_engine
    with Session(engine) as session:
        session.add(
            StrategyTemplateRecord(
                template_id=template_id,
                type_id=instance.type_id,
                name=instance.name,
                description="Explicit integration-test workflow fixture.",
                status="active",
                current_revision=1,
                timeframe_minutes=instance.timeframe_minutes,
                direction=instance.direction,
                configuration_json=configuration_json,
                setup_defaults_json=defaults_json,
                created_at=now,
                updated_at=now,
                archived_at=None,
            )
        )
        session.add(
            StrategyTemplateVersionRecord(
                template_id=template_id,
                revision=1,
                timeframe_minutes=instance.timeframe_minutes,
                direction=instance.direction,
                configuration_json=configuration_json,
                setup_defaults_json=defaults_json,
                created_at=now,
            )
        )
        session.add(
            StrategyCoinSetupRecord(
                setup_id=setup_id,
                template_id=template_id,
                template_revision=1,
                runtime_instance_id=instance_id,
                exchange="gateio",
                market_type="usdt_perpetual",
                symbol=instance.symbol,
                quote_currency="USDT",
                current_price=None,
                price_observed_at=None,
                price_state="unavailable",
                timeframe_minutes=instance.timeframe_minutes,
                direction=instance.direction,
                configuration_overrides_json="{}",
                setup_defaults_override_json=None,
                status=f"approved_{instance.environment}",
                latest_backtest_id="test-fixture-backtest",
                latest_backtest_revision=1,
                latest_backtest_assessment="promising",
                source_opportunity_id=None,
                revision=1,
                created_at=now,
                updated_at=now,
                archived_at=None,
            )
        )
        session.add(
            StrategyCoinSetupVersionRecord(
                setup_id=setup_id,
                revision=1,
                snapshot_json=json.dumps(
                    setup_snapshot,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                created_at=now,
            )
        )
        session.add(
            StrategySetupApprovalRecord(
                approval_id=str(uuid4()),
                setup_id=setup_id,
                setup_revision=1,
                mode=instance.environment,
                status="approved",
                note="Explicit integration-test approval fixture.",
                approved_at=now,
                invalidated_at=None,
            )
        )
        session.add(
            BotDeploymentRecord(
                deployment_id=deployment_id,
                setup_id=setup_id,
                setup_revision=1,
                template_id=template_id,
                template_revision=1,
                runtime_instance_id=instance_id,
                environment=instance.environment,
                strategy_type_id=instance.type_id,
                strategy_version="test-fixture",
                configuration_snapshot_json=json.dumps(
                    deployment_snapshot,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                status="not_started",
                created_at=now,
                updated_at=now,
                started_at=None,
                ended_at=None,
                error_message=None,
            )
        )
        session.commit()
    return deployment_id
