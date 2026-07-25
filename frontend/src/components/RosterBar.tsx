import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Participant } from "../api";
import { participantTint, tintStyle } from "../format";
import { useToast } from "./Toast";

export default function RosterBar({
  eventId,
  participants,
}: {
  eventId: number;
  participants: Participant[];
}) {
  const qc = useQueryClient();
  const { push, pushError } = useToast();
  const [name, setName] = useState("");
  const invalidate = () => qc.invalidateQueries({ queryKey: ["event", eventId] });

  const add = useMutation({
    mutationFn: (value: string) => api.addParticipant(eventId, value),
    onSuccess: (p) => {
      invalidate();
      push(`${p.display_name} added`, "success");
    },
    onError: pushError,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.removeParticipant(eventId, id),
    onSuccess: invalidate,
    // The API blocks removing anyone still holding items or paying a bill;
    // surfacing that reason is the whole point of the guard.
    onError: pushError,
  });

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label-caps mr-1">On this event</span>

        {participants.map((p, index) => {
          const tint = participantTint(index);
          return (
            <span
              key={p.id}
              className="chip-on animate-pop group py-1.5 pl-2.5 pr-1.5"
              style={tintStyle(tint)}
            >
              <span className="dot" style={tintStyle(tint)} aria-hidden />
              {p.display_name}
              {p.is_owner && (
                <span className="ml-0.5 text-[10px] font-semibold uppercase opacity-60">you</span>
              )}
              <button
                type="button"
                aria-label={`Remove ${p.display_name}`}
                title={`Remove ${p.display_name}`}
                disabled={remove.isPending}
                className="ml-1 flex h-4 w-4 items-center justify-center rounded-full text-[11px] leading-none opacity-40 transition-all duration-200 ease-spring hover:bg-black/10 hover:opacity-100 active:scale-90"
                onClick={() => remove.mutate(p.id)}
              >
                ✕
              </button>
            </span>
          );
        })}

        <form
          className="flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            const value = name.trim();
            if (value) {
              add.mutate(value);
              setName("");
            }
          }}
        >
          <input
            className="field w-40 py-1.5 text-footnote"
            placeholder="Add a person"
            aria-label="Add a person to this event"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="btn-tinted btn-sm"
            type="submit"
            disabled={!name.trim() || add.isPending}
          >
            Add
          </button>
        </form>
      </div>
    </div>
  );
}
