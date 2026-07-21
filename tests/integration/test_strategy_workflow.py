from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.backtesting import (
    BacktestAssessment,
    BacktestMetrics,
    BacktestResult,
    StoredBacktestRun,
)
from rangebot.domain.strategy_workflow import (
    BotDeploymentCreate,
    DcaSettings,
    SetupApprovalRequest,
    SetupBacktestRequest,
    StrategyCoinSetupCreate,
    StrategyCoinSetupUpdate,
    StrategySetupDefaults,
    StrategyTemplateCreate,
)
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_registry import discover_strategy_registry
from rangebot.engine.strategy_workflow import StrategyWorkflowRepository


def _repository(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    apply_migrations(database_url)
    engine = create_database_engine(database_url)
    instances = StrategyInstanceRepository(engine)
    registry = discover_strategy_registry()
    workflow = StrategyWorkflowRepository(engine, registry, instances)
    return engine, instances, workflow


def _promising_backtest(workflow, setup_id: str) -> StoredBacktestRun:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    request = workflow.build_backtest_request(
        setup_id,
        SetupBacktestRequest(
            start=now,
            end=now + timedelta(days=30),
        ),
    )
    metrics = BacktestMetrics(
        starting_balance=Decimal("1000"),
        ending_balance=Decimal("1120"),
        net_profit=Decimal("120"),
        return_percentage=Decimal("12"),
        total_trades=8,
        winning_trades=6,
        losing_trades=2,
        win_rate_percentage=Decimal("75"),
        gross_profit=Decimal("160"),
        gross_loss=Decimal("-40"),
        fees=Decimal("8"),
        funding=Decimal("0"),
        average_win=Decimal("26.6666666667"),
        average_loss=Decimal("-20"),
        profit_factor=Decimal("4"),
        maximum_drawdown_percentage=Decimal("8"),
        maximum_losing_streak=1,
        long_net_pnl=Decimal("120"),
        short_net_pnl=Decimal("0"),
        largest_winner_share_percentage=Decimal("25"),
    )
    result = BacktestResult(
        spec=request.spec(),
        started_at=now,
        ended_at=now + timedelta(seconds=1),
        candle_count=500,
        trades=(),
        equity_curve=(),
        metrics=metrics,
        assessment=BacktestAssessment(
            label="promising",
            score=90,
            summary_ar="نتيجة واعدة للاختبار.",
            reasons=("صافي موجب",),
        ),
    )
    return StoredBacktestRun(
        backtest_id="workflow-backtest-1",
        strategy_version="1",
        created_at=now,
        request=request,
        result=result,
    )


def test_template_setup_backtest_approval_and_deployment_are_revision_bound(tmp_path) -> None:
    engine, instances, workflow = _repository(tmp_path)

    template = workflow.create_template(
        StrategyTemplateCreate(
            type_id="adaptive_trend",
            name="اتجاه متعدد العملات",
            description="قواعد اتجاه قابلة لإعادة الاستخدام.",
            timeframe_minutes=5,
            direction="both",
            configuration={},
            status="active",
        )
    )
    setup = workflow.create_setup(
        StrategyCoinSetupCreate(
            template_id=template.template_id,
            symbol="BTC_USDT",
        ),
        current_price=Decimal("100000"),
        price_observed_at=datetime.now(UTC),
        price_state="fresh",
    )

    assert template.setup_count == 0
    assert workflow.get_template(template.template_id).setup_count == 1
    assert setup.status == "ready_for_backtest"
    assert setup.current_price == Decimal("100000")
    assert setup.effective_setup_defaults.execution_plan.entry.order_type == "market"

    stored = _promising_backtest(workflow, setup.setup_id)
    setup = workflow.record_backtest(setup.setup_id, stored)
    assert setup.status == "backtest_passed"
    assert setup.latest_backtest_revision == setup.revision

    approval = workflow.approve_setup(
        setup.setup_id,
        SetupApprovalRequest(mode="paper", note="مراجعة Paper مكتملة."),
    )
    assert approval.status == "approved"
    assert approval.setup_revision == setup.revision

    deployment = workflow.create_deployment(
        setup.setup_id,
        BotDeploymentCreate(environment="paper"),
    )
    assert deployment.status == "not_started"
    assert deployment.configuration_snapshot["setup_revision"] == setup.revision
    assert instances.get(deployment.runtime_instance_id).status == "stopped"

    monitoring = workflow.transition_deployment(deployment.deployment_id, "monitor")
    assert monitoring.status == "monitoring"
    stopped = workflow.transition_deployment(deployment.deployment_id, "stop")
    assert stopped.status == "stopped"
    running = workflow.transition_deployment(deployment.deployment_id, "start")
    assert running.status == "running"
    stopped = workflow.transition_deployment(deployment.deployment_id, "stop")
    assert stopped.status == "stopped"

    edited = workflow.update_setup(
        setup.setup_id,
        StrategyCoinSetupUpdate(timeframe_minutes=15),
    )
    assert edited.revision == setup.revision + 1
    assert edited.status == "backtest_required"
    assert edited.latest_backtest_id is None
    assert edited.active_approval_mode is None
    assert workflow.approvals(setup.setup_id)[0].status == "stale"

    try:
        workflow.create_deployment(
            setup.setup_id,
            BotDeploymentCreate(environment="paper"),
        )
    except RuntimeError as error:
        assert "not approved" in str(error)
    else:
        raise AssertionError("Edited setup must not reuse an older approval.")

    try:
        workflow.transition_deployment(deployment.deployment_id, "start")
    except RuntimeError as error:
        assert "older setup revision" in str(error)
    else:
        raise AssertionError("An older deployment must not restart after setup edits.")

    versions = workflow.setup_versions(setup.setup_id)
    assert [version.revision for version in versions] == [1, 2]
    engine.dispose()


def test_setup_can_be_approved_and_deployed_without_backtest_after_confirmation(tmp_path) -> None:
    engine, instances, workflow = _repository(tmp_path)
    template = workflow.create_template(
        StrategyTemplateCreate(
            type_id="adaptive_trend",
            name="No backtest strategy",
            timeframe_minutes=5,
            direction="both",
            configuration={},
            status="active",
        )
    )
    setup = workflow.create_setup(
        StrategyCoinSetupCreate(template_id=template.template_id, symbol="BTC_USDT"),
        current_price=Decimal("100000"),
        price_observed_at=datetime.now(UTC),
        price_state="fresh",
    )

    try:
        workflow.approve_setup(
            setup.setup_id,
            SetupApprovalRequest(mode="testnet", skip_backtest=True),
        )
    except RuntimeError as error:
        assert "APPROVE WITHOUT BACKTEST" in str(error)
    else:
        raise AssertionError("No-backtest approval must require explicit confirmation.")

    approval = workflow.approve_setup(
        setup.setup_id,
        SetupApprovalRequest(
            mode="testnet",
            note="Manual Testnet smoke test.",
            skip_backtest=True,
            confirmation="APPROVE WITHOUT BACKTEST",
        ),
    )
    assert approval.status == "approved"
    assert "no backtest" in approval.note

    deployment = workflow.create_deployment(
        setup.setup_id,
        BotDeploymentCreate(environment="testnet"),
    )
    assert deployment.status == "not_started"
    assert instances.get(deployment.runtime_instance_id).status == "stopped"
    engine.dispose()


def test_unsupported_dca_cannot_be_approved_for_a_strategy_without_a_real_runner(
    tmp_path,
) -> None:
    engine, _, workflow = _repository(tmp_path)
    template = workflow.create_template(
        StrategyTemplateCreate(
            type_id="adaptive_trend",
            name="DCA غير مدعوم",
            timeframe_minutes=5,
            configuration={},
            setup_defaults=StrategySetupDefaults(
                dca=DcaSettings(
                    enabled=True,
                    maximum_entries=3,
                    spacing_percentage=Decimal("1"),
                )
            ),
            status="active",
        )
    )
    setup = workflow.create_setup(
        StrategyCoinSetupCreate(template_id=template.template_id, symbol="SOL_USDT")
    )
    setup = workflow.record_backtest(setup.setup_id, _promising_backtest(workflow, setup.setup_id))
    assert any("DCA" in warning for warning in setup.warnings)

    try:
        workflow.approve_setup(
            setup.setup_id,
            SetupApprovalRequest(mode="paper"),
        )
    except RuntimeError as error:
        assert "DCA" in str(error)
    else:
        raise AssertionError("Unsupported DCA must not become an approved deployment.")
    engine.dispose()


def test_used_items_archive_but_unused_drafts_can_be_deleted(tmp_path) -> None:
    engine, _, workflow = _repository(tmp_path)
    draft = workflow.create_template(
        StrategyTemplateCreate(
            type_id="adaptive_trend",
            name="مسودة قابلة للحذف",
            timeframe_minutes=5,
            configuration={},
        )
    )
    workflow.delete_template(draft.template_id)

    used = workflow.create_template(
        StrategyTemplateCreate(
            type_id="adaptive_trend",
            name="استراتيجية مستخدمة",
            timeframe_minutes=5,
            configuration={},
            status="active",
        )
    )
    setup = workflow.create_setup(
        StrategyCoinSetupCreate(template_id=used.template_id, symbol="ETH_USDT")
    )
    try:
        workflow.delete_template(used.template_id)
    except RuntimeError as error:
        assert "archive" in str(error).lower()
    else:
        raise AssertionError("Used templates must not be hard-deleted.")

    archived_setup = workflow.archive_setup(setup.setup_id)
    archived_template = workflow.archive_template(used.template_id)
    assert archived_setup.status == "archived"
    assert archived_template.status == "archived"
    engine.dispose()
