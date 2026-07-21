import type { JsonValue, StrategyTypeMetadata } from "../types";

type SchemaRecord = Record<string, JsonValue>;

type LadderLevelRecord = { [key: string]: JsonValue };

export function normalizeFixedPriceLadderLevels(
  levels: JsonValue | undefined,
): JsonValue {
  if (!Array.isArray(levels)) {
    return levels ?? [];
  }

  const rows = levels.filter((level): level is LadderLevelRecord => (
    level !== null && typeof level === "object" && !Array.isArray(level)
  ));
  const enabled = rows.filter((row) => row.enabled === true);
  const disabled = rows.filter((row) => row.enabled !== true);
  const priceValue = (row: LadderLevelRecord) => {
    const price = Number(row.price);
    return Number.isFinite(price) ? price : Number.NEGATIVE_INFINITY;
  };
  const ordered = [...enabled].sort((left, right) => priceValue(right) - priceValue(left));

  return [...ordered, ...disabled].map((row, index) => ({
    ...row,
    display_order: index + 1,
  }));
}

export function validateFixedPriceLadderLevels(levels: JsonValue | undefined): string | null {
  if (!Array.isArray(levels)) {
    return "Add at least two ladder levels.";
  }
  const enabled = levels.filter((level): level is LadderLevelRecord => (
    level !== null && typeof level === "object" && !Array.isArray(level)
      && level.enabled === true
  ));
  if (enabled.length < 2) {
    return "At least two ladder levels must be enabled.";
  }
  const prices = enabled.map((level) => Number(level.price));
  if (prices.some((price) => !Number.isFinite(price) || price <= 0)) {
    return "Enter a positive price for every enabled ladder level.";
  }
  if (new Set(prices).size !== prices.length) {
    return "Enabled ladder prices must be unique.";
  }
  return null;
}

interface SchemaField {
  key: string;
  schema: SchemaRecord;
}

interface StrategyConfigurationFieldsProps {
  metadata: StrategyTypeMetadata | null;
  configuration: Record<string, JsonValue>;
  onChange: (key: string, value: JsonValue) => void;
  disabled?: boolean;
}

export function StrategyConfigurationFields({
  metadata,
  configuration,
  onChange,
  disabled = false,
}: StrategyConfigurationFieldsProps) {
  const fields = strategySchemaFields(metadata).filter(
    (field) => !(metadata?.type_id === "fixed_price_ladder" && field.key === "levels"),
  );
  if (fields.length === 0 && metadata?.type_id !== "fixed_price_ladder") {
    return (
      <div className="configuration-empty">
        لا يعلن هذا النوع إعدادات إضافية قابلة للتحرير.
      </div>
    );
  }

  return (
    <div className="configuration-grid">
      {metadata?.type_id === "fixed_price_ladder" && (
        <FixedPriceLadderLevels
          disabled={disabled}
          levels={configuration.levels}
          onChange={(value) => onChange("levels", value)}
        />
      )}
      {fields.map((field) => (
        <ConfigurationField
          disabled={disabled}
          field={field}
          key={field.key}
          value={configuration[field.key] ?? null}
          onChange={(value) => onChange(field.key, value)}
        />
      ))}
    </div>
  );
}

export function strategySchemaDefaults(
  metadata: StrategyTypeMetadata,
): Record<string, JsonValue> {
  const defaults: Record<string, JsonValue> = {};
  for (const field of strategySchemaFields(metadata)) {
    if (Object.prototype.hasOwnProperty.call(field.schema, "default")) {
      defaults[field.key] = field.schema.default ?? null;
    }
  }
  if (metadata.type_id === "fixed_price_ladder") {
    defaults.contract_symbol = "BTC_USDT";
    defaults.total_budget = "300";
    defaults.take_profit_value = "5";
    defaults.levels = [
      { level_id: "level-1", enabled: true, price: "", display_order: 1 },
      { level_id: "level-2", enabled: true, price: "", display_order: 2 },
      { level_id: "level-3", enabled: true, price: "", display_order: 3 },
    ];
  }
  return defaults;
}

function FixedPriceLadderLevels({
  levels,
  onChange,
  disabled,
}: {
  levels: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
  disabled: boolean;
}) {
  const rows = Array.isArray(levels)
    ? levels.filter((level): level is LadderLevelRecord => (
      level !== null && typeof level === "object" && !Array.isArray(level)
    ))
    : [];

  function updateRow(index: number, key: string, value: JsonValue) {
    onChange(rows.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row));
  }

  function addRow() {
    const nextOrder = rows.length + 1;
    onChange([
      ...rows,
      { level_id: `level-${nextOrder}`, enabled: true, price: "0", display_order: nextOrder },
    ]);
  }

  return (
    <section className="ladder-level-editor">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Futures limit entries</span>
          <h3>Fixed entry ladder</h3>
        </div>
        <button className="mini-button" disabled={disabled || rows.length >= 20} type="button" onClick={addRow}>
          Add level
        </button>
      </div>
      <p className="field-help">
        Enter unique prices from highest to lowest. Quantities are calculated from the budget and exchange contract rules.
      </p>
      <div className="table-scroll">
        <table className="ladder-level-table">
          <thead>
            <tr><th>#</th><th>Level ID</th><th>Price</th><th>Enabled</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.level_id ?? index)}>
                <td>{index + 1}</td>
                <td><input disabled={disabled} value={String(row.level_id ?? "")} onChange={(event) => updateRow(index, "level_id", event.target.value)} /></td>
                <td><input disabled={disabled} inputMode="decimal" type="number" step="any" value={String(row.price ?? "")} onChange={(event) => updateRow(index, "price", event.target.value)} /></td>
                <td><input checked={row.enabled === true} disabled={disabled} type="checkbox" onChange={(event) => updateRow(index, "enabled", event.target.checked)} /></td>
                <td><button className="mini-button danger" disabled={disabled || rows.length <= 2} type="button" onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConfigurationField({
  field,
  value,
  onChange,
  disabled,
}: {
  field: SchemaField;
  value: JsonValue;
  onChange: (value: JsonValue) => void;
  disabled: boolean;
}) {
  const type = stringSchemaValue(field.schema.type) ?? "string";
  const title = stringSchemaValue(field.schema.title) ?? field.key;
  const description = stringSchemaValue(field.schema.description);
  const enumValues = Array.isArray(field.schema.enum) ? field.schema.enum : null;

  if (type === "boolean") {
    return (
      <label className="checkbox-field">
        <input
          checked={value === true}
          disabled={disabled}
          type="checkbox"
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>
          <strong>{title}</strong>
          {description && <small>{description}</small>}
        </span>
      </label>
    );
  }

  if (enumValues) {
    return (
      <label className="field">
        <span>{title}</span>
        <select
          disabled={disabled}
          value={String(value ?? "")}
          onChange={(event) => onChange(coerceEnumValue(event.target.value, enumValues))}
        >
          {enumValues.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
        {description && <small>{description}</small>}
      </label>
    );
  }

  const numeric = type === "integer" || type === "number";
  return (
    <label className="field">
      <span>{title}</span>
      <input
        disabled={disabled}
        type={numeric ? "number" : "text"}
        step={type === "integer" ? 1 : numeric ? "any" : undefined}
        min={numericValue(field.schema.minimum)}
        max={numericValue(field.schema.maximum)}
        value={scalarInputValue(value)}
        onChange={(event) => {
          if (!numeric) {
            onChange(event.target.value);
            return;
          }
          if (event.target.value === "") {
            onChange(null);
            return;
          }
          const parsed = Number(event.target.value);
          onChange(Number.isFinite(parsed) ? parsed : null);
        }}
      />
      {description && <small>{description}</small>}
    </label>
  );
}

function strategySchemaFields(metadata: StrategyTypeMetadata | null): SchemaField[] {
  const properties = recordValue(metadata?.configuration_schema.properties);
  if (!properties) {
    return [];
  }
  return Object.entries(properties).flatMap(([key, value]) => {
    const schema = recordValue(value);
    return schema ? [{ key, schema }] : [];
  });
}

function recordValue(value: JsonValue | undefined): SchemaRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as SchemaRecord
    : null;
}

function stringSchemaValue(value: JsonValue | undefined): string | null {
  return typeof value === "string" ? value : null;
}

function numericValue(value: JsonValue | undefined): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function scalarInputValue(value: JsonValue): string | number {
  return typeof value === "string" || typeof value === "number" ? value : "";
}

function coerceEnumValue(value: string, options: JsonValue[]): JsonValue {
  const matched = options.find((option) => String(option) === value);
  return matched ?? value;
}
