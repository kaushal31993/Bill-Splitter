"""The splitting math.

This is the core of the application and the place where bugs are most costly,
so the whole calculation lives here in pure functions over plain data — no ORM,
no I/O — and is covered directly by tests.

The pipeline, per bill:

1. Split each line item equally among the people assigned to it. Remainder
   cents are distributed deterministically, so shares always sum to the item
   total exactly.
2. Sum each person's item shares into their subtotal for the bill.
3. Allocate tax, tip, fees, and discounts in proportion to those subtotals,
   again by largest remainder so the allocations sum to the entered amount.
4. A person's bill total is their subtotal plus their share of each charge,
   minus their share of any discount.

Then, per event: every non-payer's bill total is a debt to that bill's payer.
Debts are netted per pair of people across all bills — not collapsed into a
minimal set of transfers, so every balance stays traceable to specific bills.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .money import allocate


@dataclass(frozen=True)
class ItemInput:
    id: int
    name: str
    total_cents: int
    # participant id -> weight (always 1 in v1)
    assignments: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BillInput:
    id: int
    label: str
    participant_ids: tuple[int, ...]
    items: tuple[ItemInput, ...]
    tax_cents: int = 0
    tip_cents: int = 0
    fee_cents: int = 0
    discount_cents: int = 0
    payer_id: int | None = None


@dataclass
class ParticipantBillShare:
    participant_id: int
    subtotal_cents: int = 0
    tax_cents: int = 0
    tip_cents: int = 0
    fee_cents: int = 0
    discount_cents: int = 0

    @property
    def total_cents(self) -> int:
        return (
            self.subtotal_cents
            + self.tax_cents
            + self.tip_cents
            + self.fee_cents
            - self.discount_cents
        )


@dataclass
class BillBreakdown:
    bill_id: int
    label: str
    items_total_cents: int
    grand_total_cents: int
    payer_id: int | None
    shares: dict[int, ParticipantBillShare]
    # Item id -> {participant id -> cents}. Powers the per-bill matrix in the
    # Excel export and the assignment grid in the UI.
    item_shares: dict[int, dict[int, int]]
    unassigned_item_ids: list[int]

    @property
    def is_complete(self) -> bool:
        return not self.unassigned_item_ids and self.payer_id is not None


def compute_bill(bill: BillInput) -> BillBreakdown:
    participants = list(bill.participant_ids)

    subtotals: dict[int, int] = {pid: 0 for pid in participants}
    item_shares: dict[int, dict[int, int]] = {}
    unassigned: list[int] = []
    items_total = 0

    for item in bill.items:
        items_total += item.total_cents

        weights = {
            pid: w
            for pid, w in item.assignments.items()
            if pid in subtotals and w > 0
        }
        if not weights:
            unassigned.append(item.id)
            item_shares[item.id] = {}
            continue

        shares = allocate(item.total_cents, weights)
        item_shares[item.id] = shares
        for pid, cents in shares.items():
            subtotals[pid] += cents

    result = {pid: ParticipantBillShare(participant_id=pid, subtotal_cents=subtotals[pid])
              for pid in participants}

    # Charges are allocated across the people who actually have a subtotal, in
    # proportion to it. When nothing is assigned yet, allocate() falls back to
    # an equal split over the roster.
    tax = allocate(bill.tax_cents, subtotals)
    tip = allocate(bill.tip_cents, subtotals)
    fee = allocate(bill.fee_cents, subtotals)
    discount = allocate(bill.discount_cents, subtotals)

    for pid in participants:
        result[pid].tax_cents = tax.get(pid, 0)
        result[pid].tip_cents = tip.get(pid, 0)
        result[pid].fee_cents = fee.get(pid, 0)
        result[pid].discount_cents = discount.get(pid, 0)

    grand_total = (
        items_total
        + bill.tax_cents
        + bill.tip_cents
        + bill.fee_cents
        - bill.discount_cents
    )

    return BillBreakdown(
        bill_id=bill.id,
        label=bill.label,
        items_total_cents=items_total,
        grand_total_cents=grand_total,
        payer_id=bill.payer_id,
        shares=result,
        item_shares=item_shares,
        unassigned_item_ids=unassigned,
    )


@dataclass
class Debt:
    from_participant_id: int
    to_participant_id: int
    amount_cents: int


@dataclass
class EventBreakdown:
    bills: list[BillBreakdown]
    # participant id -> total owed across every bill
    totals_cents: dict[int, int]
    # participant id -> total they fronted as payer
    paid_cents: dict[int, int]
    # positive means they owe, negative means they are owed
    net_cents: dict[int, int]
    debts: list[Debt]
    grand_total_cents: int

    @property
    def is_complete(self) -> bool:
        return all(b.is_complete for b in self.bills)


def compute_event(bills: list[BillInput]) -> EventBreakdown:
    breakdowns = [compute_bill(b) for b in bills]

    totals: dict[int, int] = {}
    paid: dict[int, int] = {}
    # (debtor, creditor) -> cents
    pairs: dict[tuple[int, int], int] = {}
    grand_total = 0

    for bd in breakdowns:
        grand_total += bd.grand_total_cents
        if bd.payer_id is not None:
            paid[bd.payer_id] = paid.get(bd.payer_id, 0) + bd.grand_total_cents

        for pid, share in bd.shares.items():
            totals[pid] = totals.get(pid, 0) + share.total_cents
            if bd.payer_id is None or pid == bd.payer_id or share.total_cents == 0:
                continue
            key = (pid, bd.payer_id)
            pairs[key] = pairs.get(key, 0) + share.total_cents

    net = {pid: totals.get(pid, 0) - paid.get(pid, 0) for pid in set(totals) | set(paid)}

    # Net each pair against its reverse, so "A owes B $30, B owes A $10" is
    # reported once as "A owes B $20". Chains are deliberately NOT collapsed —
    # every remaining debt still traces back to specific bills.
    debts: list[Debt] = []
    seen: set[tuple[int, int]] = set()
    for (debtor, creditor), amount in sorted(pairs.items()):
        if (debtor, creditor) in seen:
            continue
        seen.add((debtor, creditor))
        seen.add((creditor, debtor))
        reverse = pairs.get((creditor, debtor), 0)
        netted = amount - reverse
        if netted > 0:
            debts.append(Debt(debtor, creditor, netted))
        elif netted < 0:
            debts.append(Debt(creditor, debtor, -netted))

    debts.sort(key=lambda d: (-d.amount_cents, d.from_participant_id, d.to_participant_id))

    return EventBreakdown(
        bills=breakdowns,
        totals_cents=totals,
        paid_cents=paid,
        net_cents=net,
        debts=debts,
        grand_total_cents=grand_total,
    )
