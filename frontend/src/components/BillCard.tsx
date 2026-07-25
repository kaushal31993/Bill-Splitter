import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Bill, type BillBreakdown, type Participant } from "../api";
import {
  formatCents,
  formatDate,
  parseMoneyToCents,
  participantTint,
  tintStyle,
} from "../format";
import { useToast } from "./Toast";
import { ConfirmButton, MoneyInput, Notice, TextField } from "./ui";

const CHARGES = [
  { key: "tax_cents", label: "Tax" },
  { key: "tip_cents", label: "Tip" },
  { key: "fee_cents", label: "Fees" },
  { key: "discount_cents", label: "Discount" },
] as const;

export default function BillCard({
  eventId,
  bill,
  breakdown,
  participants,
  index,
}: {
  eventId: number;
  bill: Bill;
  breakdown: BillBreakdown | undefined;
  participants: Participant[];
  index: number;
}) {
  const qc = useQueryClient();
  const { push, pushError } = useToast();
  const [newItemName, setNewItemName] = useState("");
  const [newItemPrice, setNewItemPrice] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["event", eventId] });
  const mutationOpts = { onSuccess: invalidate, onError: pushError };

  const updateBill = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.updateBill(bill.id, patch),
    ...mutationOpts,
  });
  const deleteBill = useMutation({
    mutationFn: () => api.deleteBill(bill.id),
    onSuccess: () => {
      invalidate();
      push(`${bill.label} deleted`, "success");
    },
    onError: pushError,
  });
  const createItem = useMutation({
    mutationFn: (item: Record<string, unknown>) => api.createItem(bill.id, item),
    ...mutationOpts,
  });
  const updateItem = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.updateItem(id, patch),
    ...mutationOpts,
  });
  const deleteItem = useMutation({
    mutationFn: (id: number) => api.deleteItem(id),
    ...mutationOpts,
  });
  const setAssignments = useMutation({
    mutationFn: ({ id, ids }: { id: number; ids: number[] }) => api.setAssignments(id, ids),
    ...mutationOpts,
  });
  const assignAll = useMutation({
    mutationFn: (onlyUnassigned: boolean) =>
      api.assignAll(
        bill.id,
        participants.map((p) => p.id),
        onlyUnassigned,
      ),
    ...mutationOpts,
  });

  const itemsTotal = bill.items.reduce((sum, i) => sum + i.total_cents, 0);
  const grandTotal =
    itemsTotal + bill.tax_cents + bill.tip_cents + bill.fee_cents - bill.discount_cents;
  const mismatch =
    bill.extracted_total_cents != null && bill.extracted_total_cents !== grandTotal
      ? bill.extracted_total_cents - grandTotal
      : null;

  const unassigned = new Set(breakdown?.unassigned_item_ids ?? []);
  const tints = new Map(participants.map((p, i) => [p.id, participantTint(i)]));
  const shareFor = (itemId: number, participantId: number) =>
    breakdown?.item_shares?.[String(itemId)]?.[String(participantId)] ?? 0;

  const toggle = (itemId: number, current: number[], participantId: number) => {
    const next = current.includes(participantId)
      ? current.filter((id) => id !== participantId)
      : [...current, participantId];
    setAssignments.mutate({ id: itemId, ids: next });
  };

  const addItem = () => {
    const name = newItemName.trim();
    const cents = parseMoneyToCents(newItemPrice) ?? 0;
    if (!name && cents === 0) return;
    createItem.mutate({
      name: name || "Item",
      quantity: 1,
      unit_price_cents: cents,
      total_cents: cents,
      participant_ids: [],
    });
    setNewItemName("");
    setNewItemPrice("");
  };

  return (
    <section
      className="animate-in card overflow-hidden"
      style={{ animationDelay: `${Math.min(index, 6) * 50}ms` }}
    >
      {/* ------------------------------------------------------------ header */}
      <header className="bg-surface-2 px-4 py-4 sm:px-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <TextField
              value={bill.label}
              ariaLabel="Bill label"
              className="field-ghost -ml-1.5 w-full min-w-0 text-title3 font-semibold"
              onCommit={(label) => label.trim() && updateBill.mutate({ label: label.trim() })}
            />
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 pl-0.5 text-footnote text-label-2">
              {bill.merchant && <span>{bill.merchant}</span>}
              {bill.bill_date && <span>{formatDate(bill.bill_date)}</span>}
              {bill.source_filename && (
                <a
                  className="inline-flex min-w-0 items-center gap-1 text-accent transition-opacity hover:opacity-70"
                  href={api.sourceUrl(bill.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span aria-hidden>📎</span>
                  <span className="truncate">{bill.source_filename}</span>
                </a>
              )}
            </div>
          </div>
          <span className="tabular shrink-0 text-title3 font-semibold text-label">
            {formatCents(grandTotal)}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <label className="flex min-w-0 items-center gap-2 text-footnote">
            <span className="whitespace-nowrap text-label-2">Paid by</span>
            <select
              className="select min-w-0"
              aria-label={`Who paid ${bill.label}`}
              value={bill.payer_id ?? ""}
              onChange={(e) =>
                updateBill.mutate({ payer_id: e.target.value ? Number(e.target.value) : null })
              }
            >
              <option value="">— not set —</option>
              {participants.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
          <ConfirmButton
            onConfirm={() => deleteBill.mutate()}
            title="Delete this bill"
            confirmLabel="Delete bill?"
          >
            Delete
          </ConfirmButton>
        </div>
      </header>

      <div className="space-y-4 p-5">
        {bill.extraction_status === "failed" && (
          <Notice tone="warn">
            <strong>Couldn't read this receipt automatically.</strong> {bill.extraction_error} The
            upload is saved — add the items below by hand.
          </Notice>
        )}
        {bill.extraction_status === "ok" && (
          <Notice>
            Read from {bill.source_filename ?? "the upload"} — check every line before assigning
            people.
          </Notice>
        )}
        {mismatch !== null && (
          <Notice tone="warn">
            The printed total is {formatCents(bill.extracted_total_cents!)} but these lines add up
            to {formatCents(grandTotal)} — off by {formatCents(Math.abs(mismatch))}. Something was
            probably misread.
          </Notice>
        )}

        {/* ------------------------------------------------------------ items
            A grid rather than a table: at sm+ it reads as columns, and below
            that each item reflows into a stacked card. A table here forced
            horizontal scrolling on every phone. */}
        <div>
          <div className="label-caps hidden border-b border-separator pb-2 sm:grid sm:grid-cols-[minmax(7rem,1.3fr)_3.5rem_6.5rem_minmax(9rem,1.5fr)_1.75rem] sm:gap-3">
            <span>Item</span>
            <span className="text-right">Qty</span>
            <span className="text-right">Total</span>
            <span>Shared by</span>
            <span />
          </div>

          <ul className="divide-y divide-separator">
            {bill.items.map((item) => (
              <li
                key={item.id}
                className="group relative grid gap-2.5 py-3 sm:grid-cols-[minmax(7rem,1.3fr)_3.5rem_6.5rem_minmax(9rem,1.5fr)_1.75rem] sm:items-start sm:gap-3"
                style={
                  unassigned.has(item.id)
                    ? { backgroundColor: "rgb(var(--orange) / 0.06)" }
                    : undefined
                }
              >
                <TextField
                  value={item.name}
                  ariaLabel={`Name of item ${item.name || item.id}`}
                  title={item.name}
                  placeholder="Item name"
                  className="field-ghost w-full min-w-0 pr-8 text-subhead font-medium sm:-ml-1.5 sm:pr-1.5 sm:font-normal"
                  onCommit={(name) => updateItem.mutate({ id: item.id, patch: { name } })}
                />

                {/* Qty and total sit side by side on a phone; `sm:contents`
                    dissolves this wrapper so they become real grid cells. */}
                <div className="flex items-center gap-2 sm:contents">
                  <label className="flex items-center gap-1.5 sm:block">
                    <span className="label-caps sm:hidden">Qty</span>
                    <input
                      type="number"
                      min={1}
                      className="field tabular w-16 py-1.5 text-right text-subhead sm:w-full"
                      aria-label={`Quantity of ${item.name || "item"}`}
                      defaultValue={item.quantity}
                      key={`qty-${item.id}-${item.quantity}`}
                      onBlur={(e) => {
                        const quantity = Math.max(1, Number(e.target.value) || 1);
                        if (quantity !== item.quantity) {
                          updateItem.mutate({ id: item.id, patch: { quantity } });
                        }
                      }}
                    />
                  </label>
                  <label className="flex flex-1 items-center gap-1.5 sm:block">
                    <span className="label-caps sm:hidden">Total</span>
                    <MoneyInput
                      className="flex-1 sm:w-full"
                      valueCents={item.total_cents}
                      ariaLabel={`Total for ${item.name || "item"}`}
                      onCommit={(total_cents) =>
                        updateItem.mutate({ id: item.id, patch: { total_cents } })
                      }
                    />
                  </label>
                </div>

                <div className="min-w-0">
                  <div className="flex flex-wrap gap-1.5">
                    {participants.map((p) => {
                      const on = item.participant_ids.includes(p.id);
                      const share = shareFor(item.id, p.id);
                      return (
                        <button
                          key={p.id}
                          type="button"
                          aria-pressed={on}
                          title={
                            on
                              ? `${p.display_name}: ${formatCents(share)}`
                              : `Add ${p.display_name}`
                          }
                          onClick={() => toggle(item.id, item.participant_ids, p.id)}
                          className={on ? "chip-on" : "chip-off"}
                          style={on ? tintStyle(tints.get(p.id) ?? "#8E8E93") : undefined}
                        >
                          {p.display_name}
                          {on && share > 0 && (
                            <span className="tabular ml-0.5 opacity-60">
                              {formatCents(share)}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                  {unassigned.has(item.id) && (
                    <p className="mt-1.5 text-caption text-caution">Nobody is on this item.</p>
                  )}
                </div>

                {/* Tucked into the name row on mobile so it costs no vertical
                    space; a plain grid cell, hover-revealed, on wider screens. */}
                <button
                  type="button"
                  className="icon-btn absolute right-0 top-2 sm:static sm:justify-self-end sm:opacity-0 sm:focus-visible:opacity-100 sm:group-hover:opacity-100"
                  aria-label={`Delete ${item.name || "item"}`}
                  onClick={() => deleteItem.mutate(item.id)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>

          {/* ------------------------------------------------------------ add */}
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              className="field min-w-0 text-subhead sm:flex-1"
              placeholder="Add an item…"
              aria-label="New item name"
              value={newItemName}
              onChange={(e) => setNewItemName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addItem()}
            />
            <div className="flex items-center gap-2">
              <input
                className="field tabular w-28 text-right text-subhead"
                placeholder="0.00"
                inputMode="decimal"
                aria-label="New item price"
                value={newItemPrice}
                onChange={(e) => setNewItemPrice(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addItem()}
              />
              <button
                type="button"
                className="btn-tinted btn-sm flex-1 sm:flex-none"
                onClick={addItem}
                disabled={createItem.isPending}
              >
                + Add item
              </button>
            </div>
          </div>
        </div>

        {participants.length > 0 && bill.items.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => assignAll.mutate(false)}
            >
              Everyone on everything
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => assignAll.mutate(true)}
            >
              Fill the unassigned only
            </button>
          </div>
        )}

        {/* ---------------------------------------------------------- charges */}
        <div className="rounded-2xl bg-fill p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {CHARGES.map((charge) => (
              <label key={charge.key} className="block">
                <span className="label-caps mb-1.5 block">{charge.label}</span>
                <MoneyInput
                  valueCents={bill[charge.key]}
                  ariaLabel={`${charge.label} for ${bill.label}`}
                  onCommit={(cents) => updateBill.mutate({ [charge.key]: cents })}
                />
              </label>
            ))}
          </div>
          <p className="mt-3 text-caption text-label-2">
            Tax, tip, and fees are split in proportion to what each person ordered.
          </p>
        </div>

        {/* ------------------------------------------- per-person, this bill */}
        {breakdown && breakdown.shares.length > 0 && (
          <div>
            <table className="w-full text-subhead">
              <thead>
                <tr className="label-caps text-left">
                  <th className="pb-2 pr-3 font-semibold">Person</th>
                  <th className="hidden pb-2 pr-3 text-right font-semibold sm:table-cell">Items</th>
                  <th className="hidden pb-2 pr-3 text-right font-semibold sm:table-cell">Tax</th>
                  <th className="hidden pb-2 pr-3 text-right font-semibold sm:table-cell">Tip</th>
                  <th className="pb-2 text-right font-semibold">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-separator">
                {breakdown.shares.map((share) => {
                  const person = participants.find((p) => p.id === share.participant_id);
                  if (!person) return null;
                  return (
                    <tr key={share.participant_id}>
                      <td className="py-2 pr-3">
                        <span className="flex items-center gap-2">
                          <span
                            className="dot"
                            aria-hidden
                            style={tintStyle(tints.get(person.id) ?? "#8E8E93")}
                          />
                          {person.display_name}
                          {bill.payer_id === person.id && (
                            <span className="text-caption text-label-3">paid</span>
                          )}
                        </span>
                      </td>
                      <td className="tabular hidden py-2 pr-3 text-right text-label-2 sm:table-cell">
                        {formatCents(share.subtotal_cents)}
                      </td>
                      <td className="tabular hidden py-2 pr-3 text-right text-label-2 sm:table-cell">
                        {formatCents(share.tax_cents)}
                      </td>
                      <td className="tabular hidden py-2 pr-3 text-right text-label-2 sm:table-cell">
                        {formatCents(share.tip_cents)}
                      </td>
                      <td className="tabular py-2 text-right font-semibold text-label">
                        {formatCents(share.total_cents)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
