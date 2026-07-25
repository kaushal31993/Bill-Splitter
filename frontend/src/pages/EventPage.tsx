import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import BillCard from "../components/BillCard";
import RosterBar from "../components/RosterBar";
import { useToast } from "../components/Toast";
import TotalsPanel from "../components/TotalsPanel";
import { ConfirmButton, EmptyState, Notice, Spinner, TextField } from "../components/ui";

export default function EventPage() {
  const { eventId: raw } = useParams();
  const eventId = Number(raw);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { push, pushError } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const event = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.getEvent(eventId),
    enabled: Number.isFinite(eventId),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["event", eventId] });

  const rename = useMutation({
    mutationFn: (name: string) => api.renameEvent(eventId, name),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["events"] });
    },
    onError: pushError,
  });

  const addBill = useMutation({
    mutationFn: () => api.createBill(eventId),
    onSuccess: invalidate,
    onError: pushError,
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadBill(eventId, file),
    onSuccess: (bill) => {
      invalidate();
      if (bill.extraction_status === "ok") {
        push(`Read ${bill.items.length} items from the receipt`, "success");
      } else if (bill.extraction_status === "failed") {
        push("Couldn't read that receipt — the bill is ready for manual entry", "info");
      }
    },
    onError: pushError,
  });

  const removeEvent = useMutation({
    mutationFn: () => api.deleteEvent(eventId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      navigate("/");
    },
    onError: pushError,
  });

  if (event.isLoading) return <Spinner label="Loading event…" />;
  if (event.error) {
    return <Notice tone="warn">Couldn't load this event. It may have been deleted.</Notice>;
  }
  if (!event.data) return null;

  const { participants, bills, totals } = event.data;
  const ownerId = participants.find((p) => p.is_owner)?.id ?? null;
  const breakdowns = new Map((totals?.bills ?? []).map((b) => [b.bill_id, b]));
  const maxMb = config.data?.max_upload_mb ?? 15;
  const canAddBills = participants.length > 0;

  const handleFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const file = files[0];
    if (file.size > maxMb * 1024 * 1024) {
      pushError(new Error(`"${file.name}" is larger than the ${maxMb} MB limit.`));
      return;
    }
    upload.mutate(file);
  };

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------- title */}
      <div className="animate-in">
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-subhead text-accent transition-opacity hover:opacity-70"
        >
          <span aria-hidden>‹</span> All events
        </Link>
        {/* The title gets its own row on narrow screens; sharing one with the
            buttons squeezed it down to a few characters on a phone. */}
        <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <TextField
            value={event.data.name}
            ariaLabel="Event name"
            className="field-ghost -ml-1.5 w-full min-w-0 text-title1 font-bold sm:flex-1 sm:text-display"
            onCommit={(name) => name.trim() && rename.mutate(name.trim())}
          />
          <div className="flex shrink-0 items-center gap-2">
            <a className="btn-tinted flex-1 sm:flex-none" href={api.exportUrl(eventId)}>
              <span aria-hidden>↓</span> Export to Excel
            </a>
            <ConfirmButton
              onConfirm={() => removeEvent.mutate()}
              className="btn-secondary btn-sm"
              confirmLabel="Delete event?"
            >
              Delete
            </ConfirmButton>
          </div>
        </div>
      </div>

      <div className="animate-in" style={{ animationDelay: "40ms" }}>
        <RosterBar eventId={eventId} participants={participants} />
      </div>

      {!canAddBills && (
        <Notice tone="warn">Add at least one person before creating a bill.</Notice>
      )}

      {totals && (
        <div className="animate-in" style={{ animationDelay: "80ms" }}>
          <TotalsPanel totals={totals} participants={participants} ownerId={ownerId} />
        </div>
      )}

      {/* ------------------------------------------------------------ upload */}
      <div
        className="animate-in"
        style={{ animationDelay: "120ms" }}
        onDragOver={(e) => {
          e.preventDefault();
          if (canAddBills) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (canAddBills) handleFiles(e.dataTransfer.files);
        }}
      >
        <div
          className={`card border-2 border-dashed p-6 text-center transition-all duration-300 ease-spring ${
            dragging
              ? "scale-[1.01] border-accent shadow-lift"
              : "border-transparent ring-1 ring-separator"
          }`}
          style={dragging ? { backgroundColor: "rgb(var(--accent) / 0.06)" } : undefined}
        >
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            accept=".jpg,.jpeg,.png,.webp,.gif,.heic,.heif,.pdf"
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = "";
            }}
          />

          {upload.isPending ? (
            <div className="flex flex-col items-center gap-3 py-2">
              <span className="h-7 w-7 animate-spin rounded-full border-2 border-label-3/30 border-t-accent" />
              <p className="text-subhead font-medium text-label">Reading the receipt…</p>
              <p className="text-footnote text-label-2">
                Extracting line items. This usually takes a few seconds.
              </p>
            </div>
          ) : (
            <>
              <div
                aria-hidden
                className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-fill text-[20px]"
              >
                {dragging ? "📥" : "📄"}
              </div>
              <p className="text-subhead font-medium text-label">
                {dragging ? "Drop to upload" : "Drop a receipt here, or"}
              </p>
              <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={!canAddBills}
                  onClick={() => fileInput.current?.click()}
                >
                  Choose photo or PDF
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={!canAddBills || addBill.isPending}
                  onClick={() => addBill.mutate()}
                >
                  Add empty bill
                </button>
              </div>
              <p className="mt-3 text-caption text-label-3">
                JPG, PNG, WEBP, GIF, HEIC or PDF · up to {maxMb} MB
                {config.data && !config.data.extraction_enabled && (
                  <> · automatic reading is off, items entered by hand</>
                )}
              </p>
            </>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------- bills */}
      {bills.length === 0 ? (
        <div className="card animate-in" style={{ animationDelay: "160ms" }}>
          <EmptyState
            icon="🧮"
            title="No bills yet"
            body="Upload a receipt to have the items read for you, or add an empty bill and type them in."
          />
        </div>
      ) : (
        <div className="space-y-5">
          {bills.map((bill, i) => (
            <BillCard
              key={bill.id}
              index={i}
              eventId={eventId}
              bill={bill}
              breakdown={breakdowns.get(bill.id)}
              participants={participants}
            />
          ))}
        </div>
      )}
    </div>
  );
}
