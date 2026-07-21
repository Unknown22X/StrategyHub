import { describe, expect, it } from "vitest";

import {
  formatCompact,
  formatDateTime,
  formatDecimal,
  formatDuration,
  toEnglishDigits,
} from "./format";

const nonLatinDigits = /[\u0660-\u0669\u06f0-\u06f9]/;

describe("Arabic UI formatting with English digits", () => {
  it("normalizes Arabic-Indic and Eastern Arabic digits", () => {
    expect(
      toEnglishDigits(
        "\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669\u0660 / \u06f1\u06f2\u06f3",
      ),
    ).toBe("1234567890 / 123");
  });

  it.each([
    ["decimal", formatDecimal(1234.5)],
    ["compact", formatCompact(1250000)],
    ["date", formatDateTime("2026-07-19T00:00:00Z")],
    ["duration", formatDuration(3660)],
  ])("uses Latin digits for %s output", (_name, formatted) => {
    expect(formatted).toMatch(/[0-9]/);
    expect(formatted).not.toMatch(nonLatinDigits);
  });
});
