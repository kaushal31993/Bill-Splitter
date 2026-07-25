import { createContext, useCallback, useContext, useMemo, useState } from "react";

type Tone = "error" | "success" | "info";

type Toast = { id: number; tone: Tone; message: string };

const ToastContext = createContext<{
  push: (message: string, tone?: Tone) => void;
  pushError: (error: unknown) => void;
}>({ push: () => {}, pushError: () => {} });

export const useToast = () => useContext(ToastContext);

const ICONS: Record<Tone, string> = {
  error: "!",
  success: "✓",
  info: "i",
};

const TONE_STYLES: Record<Tone, string> = {
  error: "bg-negative text-white",
  success: "bg-positive text-white",
  info: "bg-accent text-white",
};

/**
 * Transient feedback, presented the way the platform does it: a floating
 * capsule that appears over the content and gets out of the way on its own,
 * rather than a red block that shifts the layout underneath your cursor.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: Tone = "info") => {
      const id = Date.now() + Math.random();
      setToasts((current) => [...current.slice(-2), { id, tone, message }]);
      window.setTimeout(() => dismiss(id), tone === "error" ? 7000 : 3500);
    },
    [dismiss],
  );

  const pushError = useCallback(
    (error: unknown) => {
      if (!error) return;
      push(error instanceof Error ? error.message : String(error), "error");
    },
    [push],
  );

  const value = useMemo(() => ({ push, pushError }), [push, pushError]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end sm:p-6"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === "error" ? "alert" : "status"}
            className="animate-toast material pointer-events-auto flex max-w-md items-start gap-3 rounded-2xl px-4 py-3 shadow-toast ring-1 ring-separator"
          >
            <span
              aria-hidden
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[12px] font-bold ${TONE_STYLES[toast.tone]}`}
            >
              {ICONS[toast.tone]}
            </span>
            <p className="text-subhead text-label">{toast.message}</p>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss"
              className="btn-plain -mr-1 -mt-1 shrink-0 px-1.5 py-1 text-[13px]"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
