"""Dynamic discovery and lookup of strategy metadata and evaluator factories."""

from collections.abc import Callable
from importlib import import_module
import pkgutil
from types import ModuleType

from rangebot.domain.discovery import StrategyScanner
from rangebot.domain.strategy import StrategyTypeMetadata
from rangebot.domain.strategy_runtime import StrategyEvaluator


EvaluatorFactory = Callable[[], StrategyEvaluator]
ScannerFactory = Callable[[], StrategyScanner]


class StrategyRegistry:
    """Own available strategy types without exposing module names to frontends."""

    def __init__(self) -> None:
        self._types: dict[str, StrategyTypeMetadata] = {}
        self._evaluator_factories: dict[str, EvaluatorFactory] = {}
        self._scanner_factories: dict[str, ScannerFactory] = {}

    def register(
        self,
        metadata: StrategyTypeMetadata,
        evaluator_factory: EvaluatorFactory | None = None,
        scanner_factory: ScannerFactory | None = None,
    ) -> None:
        if metadata.type_id in self._types:
            raise ValueError(f"Strategy type already registered: {metadata.type_id}")
        self._types[metadata.type_id] = metadata
        if evaluator_factory is not None:
            self._evaluator_factories[metadata.type_id] = evaluator_factory
        if scanner_factory is not None:
            self._scanner_factories[metadata.type_id] = scanner_factory

    def get(self, type_id: str) -> StrategyTypeMetadata:
        try:
            return self._types[type_id]
        except KeyError as error:
            raise LookupError(f"Unknown strategy type: {type_id}") from error

    def evaluator(self, type_id: str) -> StrategyEvaluator:
        self.get(type_id)
        try:
            evaluator = self._evaluator_factories[type_id]()
        except KeyError as error:
            raise LookupError(
                f"Strategy type has no evaluator implementation: {type_id}"
            ) from error
        if evaluator.type_id != type_id:
            raise ValueError(
                f"Evaluator type mismatch: expected {type_id}, got {evaluator.type_id}"
            )
        return evaluator

    def scanner(self, type_id: str) -> StrategyScanner:
        metadata = self.get(type_id)
        if not metadata.supports_scanning:
            raise LookupError(f"Strategy type does not support scanning: {type_id}")
        try:
            scanner = self._scanner_factories[type_id]()
        except KeyError as error:
            raise LookupError(
                f"Strategy type has no scanner implementation: {type_id}"
            ) from error
        if scanner.type_id != type_id:
            raise ValueError(
                f"Scanner type mismatch: expected {type_id}, got {scanner.type_id}"
            )
        return scanner

    def validate_configuration(
        self, type_id: str, configuration: dict[str, object]
    ) -> None:
        evaluator = self.evaluator(type_id)
        model = getattr(evaluator, "configuration_model", None)
        if model is None or not hasattr(model, "model_validate"):
            raise TypeError(
                f"Strategy evaluator has no configuration model: {type_id}"
            )
        model.model_validate(configuration)

    def list(self) -> list[StrategyTypeMetadata]:
        return [self._types[type_id] for type_id in sorted(self._types)]


def _metadata_from_module(module: ModuleType) -> StrategyTypeMetadata | None:
    candidate = getattr(module, "STRATEGY_TYPE", None)
    if candidate is None:
        return None
    return StrategyTypeMetadata.model_validate(candidate)


def _evaluator_factory_from_module(module: ModuleType) -> EvaluatorFactory | None:
    candidate = getattr(module, "EVALUATOR_FACTORY", None)
    if candidate is None:
        return None
    if not callable(candidate):
        raise TypeError(
            f"EVALUATOR_FACTORY in {module.__name__} must be callable."
        )
    return candidate


def _scanner_factory_from_module(module: ModuleType) -> ScannerFactory | None:
    candidate = getattr(module, "SCANNER_FACTORY", None)
    if candidate is None:
        return None
    if not callable(candidate):
        raise TypeError(
            f"SCANNER_FACTORY in {module.__name__} must be callable."
        )
    return candidate


def discover_strategy_registry(
    package_name: str = "rangebot.strategies",
) -> StrategyRegistry:
    """Discover modules exposing validated metadata and optional evaluators."""
    package = import_module(package_name)
    registry = StrategyRegistry()
    for module_info in pkgutil.iter_modules(package.__path__, f"{package_name}."):
        if module_info.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        module = import_module(module_info.name)
        metadata = _metadata_from_module(module)
        if metadata is not None:
            registry.register(
                metadata,
                _evaluator_factory_from_module(module),
                _scanner_factory_from_module(module),
            )
    return registry
