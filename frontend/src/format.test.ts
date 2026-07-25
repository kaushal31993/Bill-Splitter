import { describe, expect, it } from "vitest";

import { centsToInput, formatCents, formatDate, initials, parseMoneyToCents } from "./format";

describe("formatCents", () => {
  it("formats US currency", () => {
    expect(formatCents(0)).toBe("$0.00");
    expect(formatCents(5)).toBe("$0.05");
    expect(formatCents(123456)).toBe("$1,234.56");
  });

  it("formats negatives", () => {
    expect(formatCents(-2500)).toBe("-$25.00");
  });
});

describe("parseMoneyToCents", () => {
  it("parses plain and decorated input", () => {
    expect(parseMoneyToCents("19.99")).toBe(1999);
    expect(parseMoneyToCents("$19.99")).toBe(1999);
    expect(parseMoneyToCents("1,234.56")).toBe(123456);
    expect(parseMoneyToCents(" 7 ")).toBe(700);
    expect(parseMoneyToCents(".5")).toBe(50);
  });

  it("rounds half away from zero, matching the backend", () => {
    expect(parseMoneyToCents("0.005")).toBe(1);
    expect(parseMoneyToCents("0.004")).toBe(0);
    expect(parseMoneyToCents("-0.005")).toBe(-1);
  });

  it("does not drift on values that are inexact as floats", () => {
    expect(parseMoneyToCents("19.99")).toBe(1999);
    expect(parseMoneyToCents("0.29")).toBe(29);
    expect(parseMoneyToCents("1.15")).toBe(115);
  });

  it("returns null for input it cannot parse, rather than zero", () => {
    expect(parseMoneyToCents("")).toBeNull();
    expect(parseMoneyToCents("abc")).toBeNull();
    expect(parseMoneyToCents("1.2.3")).toBeNull();
    expect(parseMoneyToCents(".")).toBeNull();
    expect(parseMoneyToCents("-")).toBeNull();
  });

  it("round-trips through the input formatter", () => {
    for (const cents of [0, 1, 99, 100, 12345, -6789]) {
      expect(parseMoneyToCents(centsToInput(cents))).toBe(cents);
    }
  });
});

describe("formatDate", () => {
  it("renders ISO dates as MM/DD/YYYY", () => {
    expect(formatDate("2026-07-24")).toBe("07/24/2026");
  });

  it("handles missing dates", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
  });

  it("does not shift the day across timezones", () => {
    // Parsed as a local date, not UTC midnight — otherwise this renders as the
    // 31st for anyone west of Greenwich.
    expect(formatDate("2026-01-01")).toBe("01/01/2026");
  });
});

describe("initials", () => {
  it("derives initials", () => {
    expect(initials("Priya")).toBe("PR");
    expect(initials("Priya Sharma")).toBe("PS");
    expect(initials("  ")).toBe("?");
  });
});
