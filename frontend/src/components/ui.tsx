import { useEffect, useState } from "react";

import { centsToInput, parseMoneyToCents } from "../format";

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-subhead text-label-2" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-label-3/30 border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorBanner({ error, onDismiss }: { error: unknown; onDismiss?: () => void }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      role="alert"
      className="animate-pop flex items-start justify-between gap-3 rounded-xl px-3.5 py-2.5 text-subhead"
      style={{ backgroundColor: "rgb(var(--red) / 0.10)", color: "rgb(var(--red))" }}
    >
      <span>{message}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="shrink-0 font-semibold underline">
          Dismiss
        </button>
      )}
    </div>
  );
}

export function Notice({
  tone = "info",
  children,
}: {
  tone?: "info" | "warn";
  children: React.ReactNode;
}) {
  const color = tone === "warn" ? "var(--orange)" : "var(--accent)";
  return (
    <div
      className="flex items-start gap-2.5 rounded-xl px-3.5 py-2.5 text-subhead"
      style={{ backgroundColor: `rgb(${color} / 0.10)`, color: `rgb(${color})` }}
    >
      <span
        aria-hidden
        className="mt-[3px] flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
        style={{ backgroundColor: `rgb(${color})` }}
      >
        {tone === "warn" ? "!" : "i"}
      </span>
      <div className="[&_strong]:font-semibold">{children}</div>
    </div>
  );
}

/**
 * A money field that edits dollars and reports integer cents.
 *
 * Commits on blur (and on Enter) rather than on every keystroke, so a
 * half-typed "1." never round-trips to the server. Unparseable input reverts to
 * the last good value instead of silently becoming zero.
 */
export function MoneyInput({
  valueCents,
  onCommit,
  className = "",
  ariaLabel,
  disabled,
}: {
  valueCents: number;
  onCommit: (cents: number) => void;
  className?: string;
  ariaLabel?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(() => centsToInput(valueCents));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setDraft(centsToInput(valueCents));
  }, [valueCents, focused]);

  const commit = () => {
    setFocused(false);
    const parsed = parseMoneyToCents(draft);
    if (parsed === null) {
      setDraft(centsToInput(valueCents));
      return;
    }
    setDraft(centsToInput(parsed));
    if (parsed !== valueCents) onCommit(parsed);
  };

  return (
    <div className={`relative ${className}`}>
      <span
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subhead text-label-3"
      >
        $
      </span>
      <input
        type="text"
        inputMode="decimal"
        aria-label={ariaLabel}
        disabled={disabled}
        className="field tabular pl-6 text-right"
        value={draft}
        onFocus={(e) => {
          setFocused(true);
          e.currentTarget.select();
        }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") {
            setDraft(centsToInput(valueCents));
            e.currentTarget.blur();
          }
        }}
      />
    </div>
  );
}

/** Text field that commits on blur/Enter, same contract as MoneyInput. */
export function TextField({
  value,
  onCommit,
  placeholder,
  ariaLabel,
  title,
  className = "field",
}: {
  value: string;
  onCommit: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  /** Long values scroll inside the field; this exposes the whole string. */
  title?: string;
  className?: string;
}) {
  const [draft, setDraft] = useState(value);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setDraft(value);
  }, [value, focused]);

  return (
    <input
      type="text"
      aria-label={ariaLabel}
      title={title}
      placeholder={placeholder}
      className={className}
      value={draft}
      onFocus={() => setFocused(true)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        setFocused(false);
        if (draft !== value) onCommit(draft);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          setDraft(value);
          e.currentTarget.blur();
        }
      }}
    />
  );
}

/**
 * Two-step destructive action: the button arms on first press and commits on
 * the second, disarming itself after a few seconds. Cheaper than a modal for
 * something that is recoverable, and harder to hit by accident than a bare
 * delete button.
 */
export function ConfirmButton({
  onConfirm,
  children,
  confirmLabel = "Confirm",
  className = "btn-plain btn-sm",
  title,
}: {
  onConfirm: () => void;
  children: React.ReactNode;
  confirmLabel?: string;
  className?: string;
  title?: string;
}) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);

  return (
    <button
      type="button"
      title={title}
      className={armed ? "btn btn-destructive btn-sm animate-pop" : className}
      onClick={() => {
        if (armed) {
          onConfirm();
          setArmed(false);
        } else {
          setArmed(true);
        }
      }}
    >
      {armed ? confirmLabel : children}
    </button>
  );
}

/** Empty-state block — icon, one line of what this is, one action. */
export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: string;
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl px-6 py-14 text-center">
      <div
        aria-hidden
        className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-fill text-[26px]"
      >
        {icon}
      </div>
      <p className="text-headline font-semibold text-label">{title}</p>
      {body && <p className="mt-1.5 max-w-sm text-subhead text-label-2">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
