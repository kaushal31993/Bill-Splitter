import type { CSSProperties } from "react";

/**
 * US formatting, pinned to an explicit `en-US` locale rather than the browser
 * default — otherwise the same data renders differently machine to machine.
 */

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usDate = new Intl.DateTimeFormat("en-US", {
  month: "2-digit",
  day: "2-digit",
  year: "numeric",
});

export function formatCents(cents: number): string {
  return usd.format(cents / 100);
}

/** Bare dollars for use inside a text input — no symbol, no grouping. */
export function centsToInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Parse user-typed money into integer cents.
 *
 * Rounds half away from zero on the third decimal, so "1.005" becomes 101
 * rather than 100 — matching the backend's ROUND_HALF_UP.
 * Returns null for anything unparseable so the caller can keep the field's
 * previous value instead of silently writing a 0.
 */
export function parseMoneyToCents(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, "").trim();
  if (cleaned === "" || cleaned === "-" || cleaned === ".") return null;
  if (!/^-?\d*\.?\d*$/.test(cleaned)) return null;
  const value = Number(cleaned);
  if (!Number.isFinite(value)) return null;
  const sign = value < 0 ? -1 : 1;
  return sign * Math.round(Math.abs(value) * 100);
}

/** `date` is an ISO YYYY-MM-DD string from the API. */
export function formatDate(date: string | null | undefined): string {
  if (!date) return "";
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return "";
  return usDate.format(new Date(y, m - 1, d));
}

export function formatDateTime(iso: string): string {
  return usDate.format(new Date(iso));
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * A stable tint per participant, so the same person reads the same everywhere.
 * These are the platform system colours; the CSS mixes each one down for
 * legible text in light mode and up in dark mode, so one hex serves both.
 * Yellow is deliberately absent — it cannot be made legible in both schemes.
 */
const TINTS = [
  "#007AFF", // blue
  "#FF9500", // orange
  "#34C759", // green
  "#AF52DE", // purple
  "#FF2D55", // pink
  "#30B0C7", // teal
  "#5856D6", // indigo
  "#FF3B30", // red
  "#00C7BE", // mint
  "#A2845E", // brown
];

export function participantTint(index: number): string {
  return TINTS[index % TINTS.length];
}

/**
 * The tint travels to CSS as a custom property, which `React.CSSProperties`
 * has no index signature for — hence the single cast, kept in one place.
 */
export function tintStyle(tint: string): CSSProperties {
  return { "--tint": tint } as CSSProperties;
}
