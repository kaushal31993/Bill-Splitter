import { type Participant, type Totals } from "../api";
import { formatCents, participantTint, tintStyle } from "../format";
import { Notice } from "./ui";

/**
 * When the owner fronted every bill — the common case — the settlement
 * collapses to "each person owes you X", and a balance graph for that would be
 * noise. Only when payers actually differ do we show net positions.
 */
export default function TotalsPanel({
  totals,
  participants,
  ownerId,
}: {
  totals: Totals;
  participants: Participant[];
  ownerId: number | null;
}) {
  const names = new Map(participants.map((p) => [p.id, p.display_name]));
  const tints = new Map(participants.map((p, i) => [p.id, participantTint(i)]));
  const payers = new Set(Object.keys(totals.paid_cents).map(Number));
  const singlePayerIsOwner = ownerId !== null && payers.size === 1 && payers.has(ownerId);

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-3 p-5 pb-4">
        <div>
          <p className="label-caps">Event total</p>
          <p className="tabular mt-1 text-display font-bold text-label">
            {formatCents(totals.grand_total_cents)}
          </p>
        </div>
        {totals.is_complete && totals.debts.length > 0 && (
          <span
            className="chip-on"
            style={tintStyle("#34C759")}
          >
            ✓ All items assigned
          </span>
        )}
      </div>

      {!totals.is_complete && (
        <div className="px-5 pb-4">
          <Notice tone="warn">
            Provisional — some items have nobody on them, or a bill has no payer.
          </Notice>
        </div>
      )}

      {totals.debts.length === 0 ? (
        <p className="px-5 pb-5 text-subhead text-label-2">
          Nothing outstanding yet. Add bills and assign items to see who owes what.
        </p>
      ) : (
        <div className="border-t border-separator px-5 py-4">
          <p className="text-subhead text-label-2">
            {singlePayerIsOwner
              ? "You paid for everything. You're owed:"
              : "Payers differ across bills, so these are netted per pair:"}
          </p>
          <ul className="mt-3 space-y-2">
            {totals.debts.map((d) => (
              <li
                key={`${d.from_participant_id}-${d.to_participant_id}`}
                className="flex items-center justify-between gap-3 rounded-xl bg-fill px-3.5 py-2.5"
              >
                <span className="flex min-w-0 items-center gap-2 text-subhead text-label">
                  <span
                    className="dot"
                    aria-hidden
                    style={tintStyle(tints.get(d.from_participant_id) ?? "#8E8E93")}
                  />
                  <span className="truncate font-medium">
                    {names.get(d.from_participant_id) ?? "?"}
                  </span>
                  {!singlePayerIsOwner && (
                    <>
                      <span aria-hidden className="text-label-3">
                        →
                      </span>
                      <span className="truncate font-medium">
                        {names.get(d.to_participant_id) ?? "?"}
                      </span>
                    </>
                  )}
                </span>
                <span className="tabular shrink-0 text-headline font-semibold text-label">
                  {formatCents(d.amount_cents)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="group border-t border-separator">
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-subhead font-medium text-label-2 transition-colors hover:text-label">
          Per-person breakdown
          <span
            aria-hidden
            className="text-label-3 transition-transform duration-300 ease-spring group-open:rotate-90"
          >
            ›
          </span>
        </summary>
        <div className="px-5 pb-5">
          <table className="w-full text-subhead">
            <thead>
              <tr className="label-caps text-left">
                <th className="pb-2 pr-3 font-semibold">Person</th>
                <th className="hidden pb-2 pr-3 text-right font-semibold sm:table-cell">Owes</th>
                <th className="hidden pb-2 pr-3 text-right font-semibold sm:table-cell">Paid</th>
                <th className="pb-2 text-right font-semibold">Net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-separator">
              {participants.map((p) => {
                const net = totals.net_cents[String(p.id)] ?? 0;
                return (
                  <tr key={p.id}>
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-2">
                        <span
                          className="dot"
                          aria-hidden
                          style={tintStyle(tints.get(p.id) ?? "#8E8E93")}
                        />
                        {p.display_name}
                      </span>
                    </td>
                    <td className="tabular hidden py-2 pr-3 text-right text-label-2 sm:table-cell">
                      {formatCents(totals.totals_cents[String(p.id)] ?? 0)}
                    </td>
                    <td className="tabular hidden py-2 pr-3 text-right text-label-2 sm:table-cell">
                      {formatCents(totals.paid_cents[String(p.id)] ?? 0)}
                    </td>
                    <td
                      className={`tabular py-2 text-right font-semibold ${
                        net > 0 ? "text-negative" : net < 0 ? "text-positive" : "text-label-3"
                      }`}
                    >
                      {formatCents(net)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-caption text-label-3">
            Positive net means they owe; negative means they're owed.
          </p>
        </div>
      </details>
    </div>
  );
}
