import random
from decimal import Decimal

import pytest

from app.money import allocate, format_usd, to_cents, to_dollars


class TestToCents:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("19.99", 1999),
            (Decimal("19.99"), 1999),
            (19.99, 1999),  # the float that is really 19.989999999999998
            ("0.005", 1),  # half up
            ("0.004", 0),
            ("-3.50", -350),
            (0, 0),
            (7, 700),
            ("1234567.89", 123456789),
        ],
    )
    def test_conversion(self, value, expected):
        assert to_cents(value) == expected

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            to_cents("twelve dollars")

    def test_round_trips(self):
        for cents in [0, 1, 99, 100, 12345, -6789]:
            assert to_cents(to_dollars(cents)) == cents


class TestFormat:
    @pytest.mark.parametrize(
        "cents,expected",
        [
            (0, "$0.00"),
            (5, "$0.05"),
            (123456, "$1,234.56"),
            (-2500, "-$25.00"),
        ],
    )
    def test_usd(self, cents, expected):
        assert format_usd(cents) == expected


class TestAllocate:
    def test_empty(self):
        assert allocate(1000, {}) == {}

    def test_exact_division(self):
        assert allocate(1000, {1: 1, 2: 1}) == {1: 500, 2: 500}

    def test_remainder_goes_to_lowest_key(self):
        # 10 cents / 3 -> 4, 3, 3
        assert allocate(10, {1: 1, 2: 1, 3: 1}) == {1: 4, 2: 3, 3: 3}

    def test_is_deterministic_regardless_of_insertion_order(self):
        a = allocate(100, {3: 1, 1: 1, 2: 1})
        b = allocate(100, {1: 1, 2: 1, 3: 1})
        c = allocate(100, {2: 1, 3: 1, 1: 1})
        assert a == b == c

    def test_proportional_allocation(self):
        # tip of $10 across subtotals of $30 / $70
        assert allocate(1000, {1: 3000, 2: 7000}) == {1: 300, 2: 700}

    def test_proportional_with_remainder_sums_exactly(self):
        result = allocate(1000, {1: 1, 2: 1, 3: 1})
        assert sum(result.values()) == 1000

    def test_zero_amount(self):
        assert allocate(0, {1: 5, 2: 5}) == {1: 0, 2: 0}

    def test_all_zero_weights_falls_back_to_equal_split(self):
        # A tip on a bill whose items are all $0 still has to divide.
        result = allocate(999, {1: 0, 2: 0, 3: 0})
        assert sum(result.values()) == 999
        assert result == {1: 333, 2: 333, 3: 333}

    def test_negative_amount(self):
        result = allocate(-1000, {1: 1, 2: 1})
        assert result == {1: -500, 2: -500}
        assert sum(result.values()) == -1000

    def test_negative_amount_with_remainder_sums_exactly(self):
        result = allocate(-10, {1: 1, 2: 1, 3: 1})
        assert sum(result.values()) == -10

    def test_zero_weight_participant_gets_nothing(self):
        result = allocate(1000, {1: 0, 2: 100})
        assert result == {1: 0, 2: 1000}

    def test_single_participant_takes_everything(self):
        assert allocate(1337, {42: 1}) == {42: 1337}

    def test_sums_exactly_over_many_random_cases(self):
        rng = random.Random(20260724)
        for _ in range(3000):
            n = rng.randint(1, 8)
            keys = rng.sample(range(1, 100), n)
            weights = {k: rng.randint(0, 50_000) for k in keys}
            amount = rng.randint(-500_000, 500_000)
            result = allocate(amount, weights)
            assert sum(result.values()) == amount, (amount, weights, result)
            assert set(result) == set(weights)

    def test_shares_never_differ_by_more_than_one_cent_on_equal_weights(self):
        for amount in range(0, 500):
            result = allocate(amount, {1: 1, 2: 1, 3: 1, 4: 1})
            assert max(result.values()) - min(result.values()) <= 1
