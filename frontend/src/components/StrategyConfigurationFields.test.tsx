import { describe, expect, it } from "vitest";

import {
  normalizeFixedPriceLadderLevels,
  validateFixedPriceLadderLevels,
} from "./StrategyConfigurationFields";

describe("normalizeFixedPriceLadderLevels", () => {
  it("orders enabled long levels from highest to lowest and renumbers them", () => {
    const result = normalizeFixedPriceLadderLevels([
      { level_id: "level-1", enabled: true, price: "0.085", display_order: 1 },
      { level_id: "level-2", enabled: true, price: "0.083", display_order: 2 },
      { level_id: "level-3", enabled: true, price: "0.088", display_order: 3 },
    ]);

    expect(result).toEqual([
      { level_id: "level-3", enabled: true, price: "0.088", display_order: 1 },
      { level_id: "level-1", enabled: true, price: "0.085", display_order: 2 },
      { level_id: "level-2", enabled: true, price: "0.083", display_order: 3 },
    ]);
  });

  it("keeps disabled levels after enabled levels", () => {
    const result = normalizeFixedPriceLadderLevels([
      { level_id: "disabled", enabled: false, price: "0.100", display_order: 1 },
      { level_id: "low", enabled: true, price: "0.080", display_order: 2 },
      { level_id: "high", enabled: true, price: "0.090", display_order: 3 },
    ]);

    expect(result).toEqual([
      { level_id: "high", enabled: true, price: "0.090", display_order: 1 },
      { level_id: "low", enabled: true, price: "0.080", display_order: 2 },
      { level_id: "disabled", enabled: false, price: "0.100", display_order: 3 },
    ]);
  });
});

describe("validateFixedPriceLadderLevels", () => {
  it("rejects missing or non-positive prices", () => {
    expect(validateFixedPriceLadderLevels([
      { enabled: true, price: "", display_order: 1 },
      { enabled: true, price: "0", display_order: 2 },
    ])).toBe("Enter a positive price for every enabled ladder level.");
  });

  it("accepts unique positive prices in any input order", () => {
    expect(validateFixedPriceLadderLevels([
      { enabled: true, price: "0.083", display_order: 1 },
      { enabled: true, price: "0.088", display_order: 2 },
    ])).toBeNull();
  });
});
