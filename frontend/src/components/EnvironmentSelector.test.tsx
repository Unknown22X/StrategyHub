import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EnvironmentRuntimeState } from "../types";
import { EnvironmentSelector } from "./EnvironmentSelector";

afterEach(cleanup);

const readyTestnet: EnvironmentRuntimeState = {
  configured_environment: "testnet",
  requested_environment: "testnet",
  active_engine_environment: "testnet",
  exchange_adapter_environment: "testnet",
  public_rest_environment: "testnet",
  public_websocket_environment: "testnet",
  private_websocket_environment: "testnet",
  credential_profile: "testnet",
  transition_state: "ready",
  restart_required: false,
  activated: true,
  transition_started_at: null,
  transition_completed_at: "2026-07-21T06:00:00Z",
  failure_code: null,
  message_ar: null,
  revision: 2,
};

describe("EnvironmentSelector", () => {
  it("shows authoritative Testnet state and requests Paper through the callback", () => {
    const onChange = vi.fn();
    render(<EnvironmentSelector runtime={readyTestnet} busy={false} onChange={onChange} />);

    expect(screen.getAllByText("Testnet")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Testnet" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Paper" }));
    expect(onChange).toHaveBeenCalledWith("paper");
  });

  it("shows mismatched stored and active environments without pretending activation", () => {
    render(
      <EnvironmentSelector
        runtime={{
          ...readyTestnet,
          configured_environment: "live",
          active_engine_environment: "paper",
          exchange_adapter_environment: null,
          public_rest_environment: "live",
          public_websocket_environment: "live",
          private_websocket_environment: null,
          credential_profile: null,
          transition_state: "mismatch",
          activated: false,
        }}
        busy={false}
        onChange={() => undefined}
      />,
    );

    expect(screen.getByText("Environment mismatch")).toBeInTheDocument();
    expect(screen.getByText(/المحفوظ: LIVE · الفعلي: Paper/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Paper" })).not.toBeDisabled();
  });

  it("disables every switch while a transition is running", () => {
    render(
      <EnvironmentSelector
        runtime={{
          ...readyTestnet,
          requested_environment: "live",
          transition_state: "switching",
          activated: false,
        }}
        busy
        onChange={() => undefined}
      />,
    );

    expect(screen.getByText("Switching to LIVE…")).toBeInTheDocument();
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
    }
  });
});
