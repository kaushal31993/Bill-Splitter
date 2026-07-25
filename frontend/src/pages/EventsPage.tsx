import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { useToast } from "../components/Toast";
import { EmptyState, Notice, Spinner } from "../components/ui";
import { formatCents, formatDateTime } from "../format";

function OwnerSetup() {
  const qc = useQueryClient();
  const { pushError } = useToast();
  const [name, setName] = useState("");

  const mutation = useMutation({
    mutationFn: (value: string) => api.createPerson(value, true),
    onSuccess: () => qc.invalidateQueries(),
    onError: pushError,
  });

  return (
    <div className="animate-in mx-auto max-w-lg pt-10 text-center">
      <div
        aria-hidden
        className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-3xl bg-accent text-[30px] shadow-lift"
      >
        👋
      </div>
      <h1 className="text-title1 font-bold text-label">Welcome</h1>
      <p className="mx-auto mt-3 max-w-md text-body text-label-2">
        What should we call you? You'll be on every event by default and set as the default
        payer — both stay editable.
      </p>
      <form
        className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) mutation.mutate(name.trim());
        }}
      >
        <input
          className="field max-w-xs text-center sm:text-left"
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label="Your name"
          autoFocus
        />
        <button
          className="btn-primary w-full sm:w-auto"
          type="submit"
          disabled={!name.trim() || mutation.isPending}
        >
          {mutation.isPending ? "Setting up…" : "Continue"}
        </button>
      </form>
    </div>
  );
}

export default function EventsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { pushError } = useToast();
  const [name, setName] = useState("");

  const owner = useQuery({ queryKey: ["owner"], queryFn: api.getOwner });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const events = useQuery({ queryKey: ["events"], queryFn: api.listEvents });

  const createEvent = useMutation({
    mutationFn: (value: string) => api.createEvent(value),
    onSuccess: (event) => {
      qc.invalidateQueries({ queryKey: ["events"] });
      navigate(`/events/${event.id}`);
    },
    onError: pushError,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      createEvent.mutate(name.trim());
      setName("");
    }
  };

  if (owner.isLoading) return <Spinner />;
  if (owner.error) {
    return <Notice tone="warn">Couldn't reach the API. Is the stack running?</Notice>;
  }
  if (!owner.data) return <OwnerSetup />;

  const list = events.data ?? [];

  return (
    <div className="space-y-8">
      <div className="animate-in">
        <p className="text-subhead text-label-2">Hi {owner.data.name}</p>
        <h1 className="mt-1 text-display font-bold text-label">Events</h1>
        <p className="mt-2 max-w-xl text-body text-label-2">
          An event holds one or more bills — a dinner, a weekend, a night out.
        </p>
      </div>

      {config.data && !config.data.extraction_enabled && (
        <div className="animate-in" style={{ animationDelay: "40ms" }}>
          <Notice tone="warn">
            <strong>Automatic receipt reading is off.</strong> Set{" "}
            <code className="rounded bg-fill px-1 py-0.5 font-mono text-caption">
              ANTHROPIC_API_KEY
            </code>{" "}
            to scan photos and PDFs. Bills and manual entry work either way.
          </Notice>
        </div>
      )}

      <form
        onSubmit={submit}
        className="animate-in card flex flex-col gap-2.5 p-2.5 sm:flex-row"
        style={{ animationDelay: "80ms" }}
      >
        <input
          className="field flex-1 border-0 bg-transparent ring-0 hover:bg-transparent"
          placeholder="Name a new event, e.g. Tahoe weekend"
          aria-label="Event name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          className="btn-primary"
          type="submit"
          disabled={!name.trim() || createEvent.isPending}
        >
          {createEvent.isPending ? "Creating…" : "Create event"}
        </button>
      </form>

      <section>
        {events.isLoading && <Spinner label="Loading events…" />}

        {!events.isLoading && list.length === 0 && (
          <div className="animate-in card" style={{ animationDelay: "120ms" }}>
            <EmptyState
              icon="🧾"
              title="No events yet"
              body="Create one above, add the people involved, then upload a receipt or enter items by hand."
            />
          </div>
        )}

        <ul className="grid gap-4 sm:grid-cols-2">
          {list.map((event, index) => (
            <li
              key={event.id}
              className="animate-in"
              style={{ animationDelay: `${Math.min(index, 8) * 45 + 120}ms` }}
            >
              <Link to={`/events/${event.id}`} className="card-interactive group block p-5">
                <div className="flex items-start justify-between gap-3">
                  <span className="truncate text-headline font-semibold text-label">
                    {event.name}
                  </span>
                  <span
                    aria-hidden
                    className="shrink-0 text-label-3 transition-transform duration-300 ease-spring group-hover:translate-x-0.5 group-hover:text-accent"
                  >
                    ›
                  </span>
                </div>
                <p className="tabular mt-3 text-title2 font-semibold text-label">
                  {formatCents(event.grand_total_cents)}
                </p>
                <p className="mt-2 text-footnote text-label-2">
                  {event.bill_count} bill{event.bill_count === 1 ? "" : "s"} ·{" "}
                  {event.participant_count} {event.participant_count === 1 ? "person" : "people"} ·{" "}
                  {formatDateTime(event.created_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
