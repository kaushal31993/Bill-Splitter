import random

import pytest

from app.splitting import BillInput, ItemInput, compute_bill, compute_event


def item(id_, total, *participants):
    return ItemInput(
        id=id_,
        name=f"item {id_}",
        total_cents=total,
        assignments={p: 1 for p in participants},
    )


class TestComputeBill:
    def test_equal_split_of_one_item(self):
        bill = BillInput(
            id=1, label="Bill 1", participant_ids=(1, 2), items=(item(1, 1000, 1, 2),)
        )
        bd = compute_bill(bill)
        assert bd.shares[1].subtotal_cents == 500
        assert bd.shares[2].subtotal_cents == 500
        assert bd.grand_total_cents == 1000

    def test_private_item_goes_entirely_to_one_person(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2, 3),
            items=(item(1, 1799, 3),),
        )
        bd = compute_bill(bill)
        assert bd.shares[3].subtotal_cents == 1799
        assert bd.shares[1].subtotal_cents == 0
        assert bd.shares[2].subtotal_cents == 0

    def test_subset_split(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2, 3, 4),
            items=(item(1, 900, 1, 2, 3),),
        )
        bd = compute_bill(bill)
        assert bd.shares[1].subtotal_cents == 300
        assert bd.shares[2].subtotal_cents == 300
        assert bd.shares[3].subtotal_cents == 300
        assert bd.shares[4].subtotal_cents == 0

    def test_tax_and_tip_are_proportional_to_subtotal(self):
        # Alice ordered $30, Bob ordered $70. A $10 tip splits 3 / 7.
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2),
            items=(item(1, 3000, 1), item(2, 7000, 2)),
            tip_cents=1000,
        )
        bd = compute_bill(bill)
        assert bd.shares[1].tip_cents == 300
        assert bd.shares[2].tip_cents == 700

    def test_discount_reduces_totals_proportionally(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2),
            items=(item(1, 3000, 1), item(2, 7000, 2)),
            discount_cents=1000,
        )
        bd = compute_bill(bill)
        assert bd.shares[1].total_cents == 3000 - 300
        assert bd.shares[2].total_cents == 7000 - 700
        assert bd.grand_total_cents == 9000

    def test_unassigned_items_are_flagged_and_block_completion(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2),
            items=(item(1, 1000, 1, 2), item(2, 500)),
            payer_id=1,
        )
        bd = compute_bill(bill)
        assert bd.unassigned_item_ids == [2]
        assert bd.is_complete is False

    def test_missing_payer_blocks_completion(self):
        bill = BillInput(
            id=1, label="Bill 1", participant_ids=(1,), items=(item(1, 100, 1),)
        )
        assert compute_bill(bill).is_complete is False

    def test_assignment_to_someone_off_the_roster_is_ignored(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2),
            items=(ItemInput(id=1, name="x", total_cents=900, assignments={1: 1, 99: 1}),),
        )
        bd = compute_bill(bill)
        assert bd.shares[1].subtotal_cents == 900
        assert 99 not in bd.shares

    def test_charges_split_equally_when_nothing_is_assigned_yet(self):
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2),
            items=(item(1, 1000),),
            tip_cents=200,
        )
        bd = compute_bill(bill)
        assert bd.shares[1].tip_cents + bd.shares[2].tip_cents == 200


class TestInvariant:
    """For every bill, the per-person totals must sum to the bill's grand total,
    to the cent, for any combination of assignments and charges."""

    def _assert_invariant(self, bill):
        bd = compute_bill(bill)
        assert sum(s.total_cents for s in bd.shares.values()) == bd.grand_total_cents
        # And the component allocations each sum to their entered amount.
        assert sum(s.tax_cents for s in bd.shares.values()) == bill.tax_cents
        assert sum(s.tip_cents for s in bd.shares.values()) == bill.tip_cents
        assert sum(s.fee_cents for s in bd.shares.values()) == bill.fee_cents
        assert sum(s.discount_cents for s in bd.shares.values()) == bill.discount_cents

    def test_worked_example_from_requirements(self):
        # 10 items, 4 people (1/2/3/4), person 1 paid.
        # 5 split 4 ways, 1 among 2/3/4, 2 between 1 and 2, 1 private to 3.
        items = (
            item(1, 1234, 1, 2, 3, 4),
            item(2, 999, 1, 2, 3, 4),
            item(3, 1500, 1, 2, 3, 4),
            item(4, 733, 1, 2, 3, 4),
            item(5, 101, 1, 2, 3, 4),
            item(6, 1875, 2, 3, 4),
            item(7, 650, 1, 2),
            item(8, 1299, 1, 2),
            item(9, 2200, 3),
            item(10, 475, 1, 2, 3, 4),
        )
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2, 3, 4),
            items=items,
            tax_cents=921,
            tip_cents=2000,
            payer_id=1,
        )
        self._assert_invariant(bill)

        bd = compute_bill(bill)
        # Person 3 holds a $22 private item, so carries a proportionally larger
        # share of tax than person 4, who only shared common items.
        assert bd.shares[3].subtotal_cents > bd.shares[4].subtotal_cents
        assert bd.shares[3].tax_cents > bd.shares[4].tax_cents
        assert bd.is_complete

    def test_awkward_amounts(self):
        # Prices and charges chosen to force remainders everywhere.
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=(1, 2, 3),
            items=(item(1, 1000, 1, 2, 3), item(2, 1, 1, 2), item(3, 7, 1, 2, 3)),
            tax_cents=1,
            tip_cents=7,
            fee_cents=1,
            discount_cents=1,
        )
        self._assert_invariant(bill)

    @pytest.mark.parametrize("seed", range(25))
    def test_randomized(self, seed):
        rng = random.Random(seed)
        n_people = rng.randint(1, 6)
        pids = tuple(range(1, n_people + 1))
        items = []
        for i in range(rng.randint(1, 15)):
            assigned = rng.sample(pids, rng.randint(1, n_people))
            items.append(item(i + 1, rng.randint(0, 25_000), *assigned))
        bill = BillInput(
            id=1,
            label="Bill 1",
            participant_ids=pids,
            items=tuple(items),
            tax_cents=rng.randint(0, 5000),
            tip_cents=rng.randint(0, 5000),
            fee_cents=rng.randint(0, 900),
            discount_cents=rng.randint(0, 900),
            payer_id=rng.choice(pids),
        )
        self._assert_invariant(bill)


class TestComputeEvent:
    def test_single_payer_everyone_owes_the_payer(self):
        bills = [
            BillInput(
                id=1,
                label="Bill 1",
                participant_ids=(1, 2, 3),
                items=(item(1, 3000, 1, 2, 3),),
                payer_id=1,
            )
        ]
        ev = compute_event(bills)
        assert ev.totals_cents == {1: 1000, 2: 1000, 3: 1000}
        assert ev.paid_cents == {1: 3000}
        assert ev.net_cents == {1: -2000, 2: 1000, 3: 1000}
        assert {(d.from_participant_id, d.to_participant_id, d.amount_cents) for d in ev.debts} == {
            (2, 1, 1000),
            (3, 1, 1000),
        }

    def test_debts_are_netted_per_pair(self):
        # 1 pays a bill 2 owes $30 on; 2 pays a bill 1 owes $10 on.
        bills = [
            BillInput(
                id=1,
                label="Bill 1",
                participant_ids=(1, 2),
                items=(item(1, 6000, 1, 2),),
                payer_id=1,
            ),
            BillInput(
                id=2,
                label="Bill 2",
                participant_ids=(1, 2),
                items=(item(2, 2000, 1, 2),),
                payer_id=2,
            ),
        ]
        ev = compute_event(bills)
        assert len(ev.debts) == 1
        d = ev.debts[0]
        assert (d.from_participant_id, d.to_participant_id, d.amount_cents) == (2, 1, 2000)

    def test_chains_are_not_collapsed(self):
        # 1 pays for 2; 2 pays for 3. A simplifying algorithm would rewrite this
        # as "3 owes 1". We deliberately keep both debts traceable.
        bills = [
            BillInput(
                id=1,
                label="Bill 1",
                participant_ids=(1, 2),
                items=(item(1, 2000, 2),),
                payer_id=1,
            ),
            BillInput(
                id=2,
                label="Bill 2",
                participant_ids=(2, 3),
                items=(item(2, 2000, 3),),
                payer_id=2,
            ),
        ]
        ev = compute_event(bills)
        pairs = {(d.from_participant_id, d.to_participant_id) for d in ev.debts}
        assert pairs == {(2, 1), (3, 2)}

    def test_event_totals_sum_to_grand_total(self):
        bills = [
            BillInput(
                id=1,
                label="Bill 1",
                participant_ids=(1, 2, 3),
                items=(item(1, 3333, 1, 2, 3),),
                tax_cents=271,
                tip_cents=666,
                payer_id=1,
            ),
            BillInput(
                id=2,
                label="Bill 2",
                participant_ids=(1, 2, 3),
                items=(item(2, 1111, 1, 2), item(3, 899, 3)),
                tip_cents=101,
                payer_id=3,
            ),
        ]
        ev = compute_event(bills)
        assert sum(ev.totals_cents.values()) == ev.grand_total_cents
        # Everything fronted equals everything owed.
        assert sum(ev.paid_cents.values()) == ev.grand_total_cents
        assert sum(ev.net_cents.values()) == 0

    def test_empty_event(self):
        ev = compute_event([])
        assert ev.grand_total_cents == 0
        assert ev.debts == []
