"""Add reusable strategy templates, coin setups, opportunities, and deployments.

Revision ID: 0029_strategy_workflow
Revises: 0028_account_risk_policy
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from alembic import op
import sqlalchemy as sa


revision = "0029_strategy_workflow"
down_revision = "0028_account_risk_policy"
branch_labels = None
depends_on = None


_DEFAULT_SETUP_DEFAULTS = {
    "execution_plan": {
        "entry": {
            "order_type": "market",
            "limit_price": None,
            "limit_price_formula": None,
            "time_in_force": "gtc",
            "expires_after_minutes": None,
            "cancellation_policy": "cancel_on_signal_reset",
            "partial_fill_behavior": "accept_partial",
        },
        "take_profit": {
            "order_type": "market",
            "limit_offset_percentage": None,
            "time_in_force": "ioc",
            "maximum_wait_seconds": 30,
            "fallback_to_market": True,
        },
        "stop_loss": {
            "order_type": "market",
            "limit_offset_percentage": None,
            "time_in_force": "ioc",
            "maximum_wait_seconds": 30,
            "fallback_to_market": True,
        },
        "strategy_exit": {
            "order_type": "market",
            "limit_offset_percentage": None,
            "time_in_force": "ioc",
            "maximum_wait_seconds": 30,
            "fallback_to_market": True,
        },
        "manual_exit": {
            "order_type": "market",
            "limit_offset_percentage": None,
            "time_in_force": "ioc",
            "maximum_wait_seconds": 30,
            "fallback_to_market": True,
        },
    },
    "dca": {
        "enabled": False,
        "maximum_entries": 1,
        "spacing_percentage": "1",
        "allocation_method": "equal",
        "custom_allocations": [],
    },
    "risk": {
        "requested_margin": "20",
        "requested_leverage": 3,
        "maximum_positions": 1,
        "maximum_exposure_percentage": "25",
    },
}


def upgrade() -> None:
    op.create_table(
        "strategy_template",
        sa.Column("template_id", sa.String(length=36), primary_key=True),
        sa.Column("type_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("setup_defaults_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_strategy_template_status", "strategy_template", ["status"], unique=False
    )
    op.create_index(
        "ix_strategy_template_type", "strategy_template", ["type_id"], unique=False
    )

    op.create_table(
        "strategy_template_version",
        sa.Column("version_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("setup_defaults_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "template_id", "revision", name="uq_strategy_template_revision"
        ),
    )
    op.create_index(
        "ix_strategy_template_version_template",
        "strategy_template_version",
        ["template_id", "revision"],
        unique=False,
    )

    op.create_table(
        "strategy_coin_setup",
        sa.Column("setup_id", sa.String(length=36), primary_key=True),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("template_revision", sa.Integer(), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=36), nullable=True),
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("quote_currency", sa.String(length=16), nullable=False),
        sa.Column("current_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("price_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_state", sa.String(length=16), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("configuration_overrides_json", sa.Text(), nullable=False),
        sa.Column("setup_defaults_override_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latest_backtest_id", sa.String(length=36), nullable=True),
        sa.Column("latest_backtest_revision", sa.Integer(), nullable=True),
        sa.Column("latest_backtest_assessment", sa.String(length=32), nullable=True),
        sa.Column("source_opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "template_id", "exchange", "market_type", "symbol",
            name="uq_strategy_coin_setup_identity",
        ),
    )
    op.create_index(
        "ix_strategy_coin_setup_template",
        "strategy_coin_setup",
        ["template_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_coin_setup_runtime",
        "strategy_coin_setup",
        ["runtime_instance_id"],
        unique=False,
    )

    op.create_table(
        "strategy_coin_setup_version",
        sa.Column("version_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("setup_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("setup_id", "revision", name="uq_coin_setup_revision"),
    )
    op.create_index(
        "ix_coin_setup_version_setup",
        "strategy_coin_setup_version",
        ["setup_id", "revision"],
        unique=False,
    )

    op.create_table(
        "strategy_setup_approval",
        sa.Column("approval_id", sa.String(length=36), primary_key=True),
        sa.Column("setup_id", sa.String(length=36), nullable=False),
        sa.Column("setup_revision", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_setup_approval_lookup",
        "strategy_setup_approval",
        ["setup_id", "setup_revision", "mode", "status"],
        unique=False,
    )

    op.create_table(
        "strategy_opportunity",
        sa.Column("opportunity_id", sa.String(length=36), primary_key=True),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_type_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("quote_currency", sa.String(length=16), nullable=False),
        sa.Column("current_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("price_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_state", sa.String(length=16), nullable=False),
        sa.Column("scanner_score", sa.Integer(), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=False),
        sa.Column("eligible_now", sa.Boolean(), nullable=False),
        sa.Column("qualifying_factors_json", sa.Text(), nullable=False),
        sa.Column("explanation_ar", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("converted_setup_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint("scan_id", "symbol", name="uq_opportunity_scan_symbol"),
    )
    op.create_index(
        "ix_strategy_opportunity_status",
        "strategy_opportunity",
        ["status", "discovered_at"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_opportunity_strategy",
        "strategy_opportunity",
        ["strategy_type_id", "scanner_score"],
        unique=False,
    )

    op.create_table(
        "bot_deployment",
        sa.Column("deployment_id", sa.String(length=36), primary_key=True),
        sa.Column("setup_id", sa.String(length=36), nullable=False),
        sa.Column("setup_revision", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("template_revision", sa.Integer(), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("strategy_type_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("configuration_snapshot_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "runtime_instance_id", name="uq_bot_deployment_runtime_instance"
        ),
    )
    op.create_index(
        "ix_bot_deployment_setup",
        "bot_deployment",
        ["setup_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_bot_deployment_status",
        "bot_deployment",
        ["status", "environment"],
        unique=False,
    )

    op.add_column(
        "backtest_run", sa.Column("setup_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "backtest_run", sa.Column("setup_revision", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_backtest_run_setup",
        "backtest_run",
        ["setup_id", "setup_revision", "created_at"],
        unique=False,
    )

    _backfill_existing_instances()


def _backfill_existing_instances() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT instance_id, type_id, name, environment, symbol,
                   timeframe_minutes, direction, requested_margin,
                   requested_leverage, configuration_json, status,
                   created_at, updated_at
            FROM strategy_instance
            """
        )
    ).mappings()
    now = datetime.now(UTC)
    for row in rows:
        instance_id = str(row["instance_id"])
        template_id = str(uuid5(NAMESPACE_URL, f"rangebot-template:{instance_id}"))
        setup_id = str(uuid5(NAMESPACE_URL, f"rangebot-setup:{instance_id}"))
        configuration_json = str(row["configuration_json"])
        setup_defaults = json.loads(json.dumps(_DEFAULT_SETUP_DEFAULTS))
        setup_defaults["risk"]["requested_margin"] = str(row["requested_margin"])
        setup_defaults["risk"]["requested_leverage"] = int(row["requested_leverage"])
        setup_defaults_json = json.dumps(
            setup_defaults, sort_keys=True, separators=(",", ":")
        )
        created_at = row["created_at"] or now
        updated_at = row["updated_at"] or now

        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_template (
                    template_id, type_id, name, description, status,
                    current_revision, timeframe_minutes, direction,
                    configuration_json, setup_defaults_json, created_at,
                    updated_at, archived_at
                ) VALUES (
                    :template_id, :type_id, :name, :description, 'active',
                    1, :timeframe_minutes, :direction, :configuration_json,
                    :setup_defaults_json, :created_at, :updated_at, NULL
                )
                """
            ),
            {
                "template_id": template_id,
                "type_id": row["type_id"],
                "name": row["name"],
                "description": "تم ترحيل هذه الاستراتيجية من نسخة RangeBot السابقة.",
                "timeframe_minutes": row["timeframe_minutes"],
                "direction": row["direction"],
                "configuration_json": configuration_json,
                "setup_defaults_json": setup_defaults_json,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_template_version (
                    template_id, revision, timeframe_minutes, direction,
                    configuration_json, setup_defaults_json, created_at
                ) VALUES (
                    :template_id, 1, :timeframe_minutes, :direction,
                    :configuration_json, :setup_defaults_json, :created_at
                )
                """
            ),
            {
                "template_id": template_id,
                "timeframe_minutes": row["timeframe_minutes"],
                "direction": row["direction"],
                "configuration_json": configuration_json,
                "setup_defaults_json": setup_defaults_json,
                "created_at": created_at,
            },
        )

        runtime_status = str(row["status"])
        setup_status = "backtest_required"
        approval_mode = str(row["environment"])
        if runtime_status in {"running", "monitoring", "paused"}:
            setup_status = f"approved_{approval_mode}"
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_coin_setup (
                    setup_id, template_id, template_revision,
                    runtime_instance_id, exchange, market_type, symbol,
                    quote_currency, current_price, price_observed_at,
                    price_state, timeframe_minutes, direction,
                    configuration_overrides_json,
                    setup_defaults_override_json, status,
                    latest_backtest_id, latest_backtest_revision,
                    latest_backtest_assessment, source_opportunity_id,
                    revision, created_at, updated_at, archived_at
                ) VALUES (
                    :setup_id, :template_id, 1, :instance_id, 'gateio',
                    'usdt_perpetual', :symbol, 'USDT', NULL, NULL,
                    'unavailable', :timeframe_minutes, :direction, '{}',
                    NULL, :status, NULL, NULL, NULL, NULL, 1,
                    :created_at, :updated_at, NULL
                )
                """
            ),
            {
                "setup_id": setup_id,
                "template_id": template_id,
                "instance_id": instance_id,
                "symbol": row["symbol"],
                "timeframe_minutes": row["timeframe_minutes"],
                "direction": row["direction"],
                "status": setup_status,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        snapshot = {
            "migrated_from_instance_id": instance_id,
            "template_id": template_id,
            "template_revision": 1,
            "symbol": row["symbol"],
            "timeframe_minutes": row["timeframe_minutes"],
            "direction": row["direction"],
            "configuration_overrides": {},
            "setup_defaults_override": None,
        }
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_coin_setup_version (
                    setup_id, revision, snapshot_json, created_at
                ) VALUES (:setup_id, 1, :snapshot_json, :created_at)
                """
            ),
            {
                "setup_id": setup_id,
                "snapshot_json": json.dumps(
                    snapshot, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ),
                "created_at": created_at,
            },
        )

        if runtime_status not in {"running", "monitoring", "paused"}:
            continue
        approval_id = str(uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO strategy_setup_approval (
                    approval_id, setup_id, setup_revision, mode, status,
                    note, approved_at, invalidated_at
                ) VALUES (
                    :approval_id, :setup_id, 1, :mode, 'approved',
                    :note, :approved_at, NULL
                )
                """
            ),
            {
                "approval_id": approval_id,
                "setup_id": setup_id,
                "mode": approval_mode,
                "note": "اعتماد ترحيل للحفاظ على تشغيل نسخة كانت نشطة قبل نموذج الموافقات.",
                "approved_at": updated_at,
            },
        )
        deployment_id = str(uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO bot_deployment (
                    deployment_id, setup_id, setup_revision, template_id,
                    template_revision, runtime_instance_id, environment,
                    strategy_type_id, strategy_version,
                    configuration_snapshot_json, status, created_at,
                    updated_at, started_at, ended_at, error_message
                ) VALUES (
                    :deployment_id, :setup_id, 1, :template_id, 1,
                    :instance_id, :environment, :type_id, 'legacy',
                    :snapshot_json, :status, :created_at, :updated_at,
                    :started_at, NULL, NULL
                )
                """
            ),
            {
                "deployment_id": deployment_id,
                "setup_id": setup_id,
                "template_id": template_id,
                "instance_id": instance_id,
                "environment": approval_mode,
                "type_id": row["type_id"],
                "snapshot_json": json.dumps(
                    snapshot, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ),
                "status": runtime_status,
                "created_at": created_at,
                "updated_at": updated_at,
                "started_at": created_at,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_backtest_run_setup", table_name="backtest_run")
    op.drop_column("backtest_run", "setup_revision")
    op.drop_column("backtest_run", "setup_id")
    op.drop_index("ix_bot_deployment_status", table_name="bot_deployment")
    op.drop_index("ix_bot_deployment_setup", table_name="bot_deployment")
    op.drop_table("bot_deployment")
    op.drop_index("ix_strategy_opportunity_strategy", table_name="strategy_opportunity")
    op.drop_index("ix_strategy_opportunity_status", table_name="strategy_opportunity")
    op.drop_table("strategy_opportunity")
    op.drop_index("ix_setup_approval_lookup", table_name="strategy_setup_approval")
    op.drop_table("strategy_setup_approval")
    op.drop_index("ix_coin_setup_version_setup", table_name="strategy_coin_setup_version")
    op.drop_table("strategy_coin_setup_version")
    op.drop_index("ix_strategy_coin_setup_runtime", table_name="strategy_coin_setup")
    op.drop_index("ix_strategy_coin_setup_template", table_name="strategy_coin_setup")
    op.drop_table("strategy_coin_setup")
    op.drop_index(
        "ix_strategy_template_version_template",
        table_name="strategy_template_version",
    )
    op.drop_table("strategy_template_version")
    op.drop_index("ix_strategy_template_type", table_name="strategy_template")
    op.drop_index("ix_strategy_template_status", table_name="strategy_template")
    op.drop_table("strategy_template")
