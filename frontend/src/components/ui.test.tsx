import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MoneyInput } from "./ui";

describe("MoneyInput", () => {
  it("shows the value as dollars", () => {
    render(<MoneyInput valueCents={1999} onCommit={() => {}} ariaLabel="Price" />);
    expect(screen.getByLabelText("Price")).toHaveValue("19.99");
  });

  it("commits cents on blur, not on every keystroke", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(<MoneyInput valueCents={0} onCommit={onCommit} ariaLabel="Price" />);

    const input = screen.getByLabelText("Price");
    await user.clear(input);
    await user.type(input, "12.50");
    // A half-typed "1." must never round-trip to the server.
    expect(onCommit).not.toHaveBeenCalled();

    await user.tab();
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(1250);
  });

  it("reverts unparseable input instead of writing a zero", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(<MoneyInput valueCents={500} onCommit={onCommit} ariaLabel="Price" />);

    const input = screen.getByLabelText("Price");
    await user.clear(input);
    await user.type(input, "not money");
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
    expect(input).toHaveValue("5.00");
  });

  it("does not fire when the value is unchanged", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(<MoneyInput valueCents={1000} onCommit={onCommit} ariaLabel="Price" />);

    await user.click(screen.getByLabelText("Price"));
    await user.tab();
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("accepts a typed dollar sign and commas", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(<MoneyInput valueCents={0} onCommit={onCommit} ariaLabel="Price" />);

    const input = screen.getByLabelText("Price");
    await user.clear(input);
    await user.type(input, "$1,234.56");
    await user.tab();

    expect(onCommit).toHaveBeenCalledWith(123456);
  });
});
