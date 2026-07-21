import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AccountRiskPolicy } from "../types";
import { RiskManagementDrawer } from "./RiskManagementDrawer";

const { loadAccountRiskPolicy, saveAccountRiskPolicy } = vi.hoisted(() => ({
  loadAccountRiskPolicy: vi.fn(),
  saveAccountRiskPolicy: vi.fn(),
}));

vi.mock("../api", () => ({
  loadAccountRiskPolicy: (...args: unknown[]) => loadAccountRiskPolicy(...args),
  saveAccountRiskPolicy: (...args: unknown[]) => saveAccountRiskPolicy(...args),
}));

const policy: AccountRiskPolicy = {
  daily_loss_enabled: true,
  daily_loss_limit: "100",
  losing_trade_enabled: true,
  losing_trade_limit: 3,
  automatic_trade_enabled: true,
  automatic_trade_limit: 5,
  revision: 2,
  updated_at: "2026-07-21T08:00:00Z",
};

afterEach(cleanup);

beforeEach(() => {
  loadAccountRiskPolicy.mockReset();
  saveAccountRiskPolicy.mockReset();
  loadAccountRiskPolicy.mockResolvedValue(policy);
  saveAccountRiskPolicy.mockImplementation(async (change) => ({
    ...policy,
    ...change,
    revision: 3,
  }));
  vi.restoreAllMocks();
});

describe("RiskManagementDrawer", () => {
  it("persists disabled state and requires LIVE confirmation even from Paper", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("DISABLE LIVE RISK LIMITS");
    render(
      <RiskManagementDrawer
        open
        environment="paper"
        onClose={() => undefined}
        onSaved={() => undefined}
      />,
    );

    const toggle = await screen.findByRole("checkbox", {
      name: /Enable Daily Equity-Loss Limit/,
    });
    const lossInput = screen.getByDisplayValue("100");
    expect(toggle).toBeChecked();
    expect(lossInput).not.toBeDisabled();

    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(lossInput).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /حفظ Risk Policy/ }));

    await waitFor(() => {
      expect(saveAccountRiskPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          daily_loss_enabled: false,
          daily_loss_limit: "100",
          losing_trade_enabled: true,
          automatic_trade_enabled: true,
          confirmation: "DISABLE LIVE RISK LIMITS",
        }),
      );
    });
  });

  it("requires the exact real-funds confirmation before weakening LIVE", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const prompt = vi
      .spyOn(window, "prompt")
      .mockReturnValue("DISABLE LIVE RISK LIMITS");
    render(
      <RiskManagementDrawer
        open
        environment="live"
        onClose={() => undefined}
        onSaved={() => undefined}
      />,
    );

    const toggle = await screen.findByRole("checkbox", {
      name: /Enable Daily Automatic-Entry Limit/,
    });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /حفظ Risk Policy/ }));

    await waitFor(() => {
      expect(confirm).toHaveBeenCalledWith(expect.stringContaining("أموالاً حقيقية"));
      expect(prompt).toHaveBeenCalledWith(
        expect.stringContaining("DISABLE LIVE RISK LIMITS"),
        "",
      );
      expect(saveAccountRiskPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          automatic_trade_enabled: false,
          confirmation: "DISABLE LIVE RISK LIMITS",
        }),
      );
    });
  });

  it("does not save LIVE changes when the confirmation phrase is wrong", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("wrong phrase");
    render(
      <RiskManagementDrawer
        open
        environment="live"
        onClose={() => undefined}
        onSaved={() => undefined}
      />,
    );

    const toggle = await screen.findByRole("checkbox", {
      name: /Enable Daily Losing-Trades Limit/,
    });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /حفظ Risk Policy/ }));

    expect(await screen.findByText(/عبارة تأكيد LIVE لم تكن مطابقة/)).toBeInTheDocument();
    expect(saveAccountRiskPolicy).not.toHaveBeenCalled();
  });
});
