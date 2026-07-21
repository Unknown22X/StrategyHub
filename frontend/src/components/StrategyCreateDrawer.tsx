import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { createStrategy } from "../api";
import type {
  Environment,
  JsonValue,
  StrategyInstance,
  StrategyTypeMetadata,
} from "../types";
import { ContractSymbolPicker } from "./ContractSymbolPicker";
import { Icon } from "./Icon";
import {
  normalizeFixedPriceLadderLevels,
  StrategyConfigurationFields,
  strategySchemaDefaults,
  validateFixedPriceLadderLevels,
} from "./StrategyConfigurationFields";

interface StrategyCreateDrawerProps {
  open: boolean;
  environment: Environment;
  initialTypeId: string | null;
  strategyTypes: StrategyTypeMetadata[];
  onClose: () => void;
  onCreated: (strategy: StrategyInstance) => void;
}

export function StrategyCreateDrawer({
  open,
  environment,
  initialTypeId,
  strategyTypes,
  onClose,
  onCreated,
}: StrategyCreateDrawerProps) {
  const [typeId, setTypeId] = useState("");
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframeMinutes, setTimeframeMinutes] = useState(5);
  const [direction, setDirection] = useState<"long" | "short" | "both">("both");
  const [requestedMargin, setRequestedMargin] = useState("20");
  const [requestedLeverage, setRequestedLeverage] = useState(3);
  const [configuration, setConfiguration] = useState<Record<string, JsonValue>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedType = useMemo(
    () => strategyTypes.find((item) => item.type_id === typeId) ?? null,
    [strategyTypes, typeId],
  );

  useEffect(() => {
    if (!open || strategyTypes.length === 0) {
      return;
    }
    const initialType = strategyTypes.find((item) => item.type_id === initialTypeId);
    if (initialType) {
      if (typeId !== initialType.type_id) {
        chooseType(initialType);
      }
      return;
    }
    if (!strategyTypes.some((item) => item.type_id === typeId)) {
      chooseType(strategyTypes[0]);
    }
  }, [initialTypeId, open, strategyTypes, typeId]);

  if (!open) {
    return null;
  }

  function chooseType(metadata: StrategyTypeMetadata) {
    setTypeId(metadata.type_id);
    setConfiguration(strategySchemaDefaults(metadata));
    if (metadata.type_id === "fixed_price_ladder") {
      setDirection("long");
      setRequestedMargin("300");
      setRequestedLeverage(1);
    }
    setError(null);
  }

  function updateConfiguration(key: string, value: JsonValue) {
    setConfiguration((current) => ({ ...current, [key]: value }));
    setError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedType) {
      setError("لا يوجد نوع استراتيجية متاح من المحرك.");
      return;
    }
    if (selectedType.type_id === "fixed_price_ladder") {
      const ladderError = validateFixedPriceLadderLevels(configuration.levels);
      if (ladderError) {
        setError(ladderError);
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      const effectiveConfiguration = selectedType.type_id === "fixed_price_ladder"
        ? {
            ...configuration,
            levels: normalizeFixedPriceLadderLevels(configuration.levels),
            contract_symbol: symbol.trim().toUpperCase().replace("/", "_"),
            environment,
            leverage: requestedLeverage,
          }
        : configuration;
      const created = await createStrategy({
        type_id: selectedType.type_id,
        name: name.trim(),
        environment,
        symbol: symbol.trim().toUpperCase().replace("/", "_"),
        timeframe_minutes: timeframeMinutes,
        direction,
        requested_margin: requestedMargin,
        requested_leverage: requestedLeverage,
        configuration: effectiveConfiguration,
      });
      onCreated(created);
      setName("");
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذر إنشاء الاستراتيجية.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-label="إنشاء استراتيجية"
        aria-modal="true"
        className="trade-drawer strategy-drawer"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <span className="eyebrow">السجل الديناميكي للاستراتيجيات</span>
            <h2>إضافة استراتيجية محفوظة</h2>
            <p>الأنواع والحقول الافتراضية تأتي من محرك RangeBot، وليست قائمة ثابتة داخل الواجهة.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="إغلاق">
            <Icon name="x" />
          </button>
        </header>

        {strategyTypes.length === 0 ? (
          <div className="state-panel state-error">
            <strong>لا توجد أنواع استراتيجية مسجلة</strong>
            <span>تحقق من سجل الاستراتيجيات في المحرك.</span>
          </div>
        ) : (
          <form className="trade-form" onSubmit={submit}>
            <label className="field">
              <span>نوع الاستراتيجية</span>
              <select
                value={typeId}
                onChange={(event) => {
                  const metadata = strategyTypes.find((item) => item.type_id === event.target.value);
                  if (metadata) chooseType(metadata);
                }}
              >
                {strategyTypes.map((item) => (
                  <option key={item.type_id} value={item.type_id}>{item.display_name_ar}</option>
                ))}
              </select>
            </label>

            {selectedType && (
              <div className="strategy-type-description">
                <strong>{selectedType.display_name_ar}</strong>
                <span>{selectedType.description_ar}</span>
                {selectedType.important_warnings_ar.map((warning) => (
                  <small key={warning}>{warning}</small>
                ))}
              </div>
            )}

            <div className="field-group two-columns">
              <label className="field">
                <span>اسم النسخة المحفوظة</span>
                <input
                  required
                  maxLength={200}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="مثال: نطاق BTC خمس دقائق"
                />
              </label>
              <ContractSymbolPicker
                value={symbol}
                onChange={setSymbol}
                environment={environment}
                label="Coin / contract"
                required
              />
            </div>

            <div className="field-group three-columns">
              <label className="field">
                <span>البيئة</span>
                <input readOnly value={environment} />
              </label>
              <label className="field">
                <span>الإطار بالدقائق</span>
                <input
                  required
                  min={1}
                  max={10080}
                  type="number"
                  value={timeframeMinutes}
                  onChange={(event) => setTimeframeMinutes(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>الاتجاه</span>
                <select
                  value={direction}
                  onChange={(event) => setDirection(event.target.value as "long" | "short" | "both")}
                >
                  <option value="both">الاتجاهان</option>
                  <option value="long">شراء فقط</option>
                  <option value="short">بيع فقط</option>
                </select>
              </label>
            </div>

            <div className="field-group two-columns">
              <label className="field">
                <span>الهامش لكل دخول تلقائي</span>
                <input
                  required
                  min="0.01"
                  step="0.01"
                  inputMode="decimal"
                  value={requestedMargin}
                  onChange={(event) => setRequestedMargin(event.target.value)}
                />
              </label>
              <label className="field">
                <span>الرافعة المطلوبة</span>
                <input
                  required
                  min={1}
                  max={100}
                  type="number"
                  value={requestedLeverage}
                  onChange={(event) => setRequestedLeverage(Number(event.target.value))}
                />
              </label>
            </div>
            <p className="field-help">
              يطبق المحرك هذه القيم بعد فحص الرصيد وحدود العقد والمخاطر؛ الاستراتيجية لا تحدد حجم الأمر بنفسها.
            </p>

            {selectedType && (
              <section className="configuration-section">
                <div className="section-title-row">
                  <div>
                    <span className="eyebrow">JSON Schema من المحرك</span>
                    <h3>إعدادات الاستراتيجية</h3>
                  </div>
                </div>
                <StrategyConfigurationFields
                  metadata={selectedType}
                  configuration={configuration}
                  onChange={updateConfiguration}
                />
              </section>
            )}

            {error && <div className="inline-alert error-alert" role="alert">{error}</div>}

            <button className="primary-button" type="submit" disabled={busy || !selectedType}>
              <Icon name="plus" />
              {busy ? "جارٍ الحفظ…" : "حفظ الاستراتيجية"}
            </button>
          </form>
        )}
      </aside>
    </div>
  );
}
