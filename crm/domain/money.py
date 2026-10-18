"""Currency arithmetic. Amounts are rupees rounded half-up to paise."""
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def to_paise(value):
    return int(Decimal(str(money(value))) * 100)


def allocate_discount(discount, line_totals):
    """Split a bill-level discount across lines in proportion to their totals.

    Works in whole paise using the largest-remainder method, so the shares
    always add up exactly to the discount.
    """
    total = to_paise(discount)
    weights = [to_paise(value) for value in line_totals]
    weight_total = sum(weights)
    if not total or not weight_total:
        return [0.0 for _ in weights]
    shares = [(total * weight) // weight_total for weight in weights]
    remainder = total - sum(shares)
    by_remainder = sorted(range(len(weights)), key=lambda i: (total * weights[i]) % weight_total, reverse=True)
    for index in by_remainder[:remainder]:
        shares[index] += 1
    return [share / 100 for share in shares]


def amounts_equal(a, b, tolerance=0.01):
    return abs(money(a) - money(b)) <= tolerance
