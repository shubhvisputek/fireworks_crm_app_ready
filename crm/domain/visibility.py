"""Hide data a user may not see. Applied by services before data leaves the server."""

# Fields that reveal cost or profit.
PROFIT_FIELDS = frozenset({'cogs', 'gross_profit', 'gross_margin', 'net_profit', 'profit', 'cost_price', 'cost_snapshot',
                           'inventory_cost', 'unit_cost', 'cost', 'cost_total', 'total_cost'})


def strip_fields(data, fields=PROFIT_FIELDS):
    """A copy of dicts/lists with the given keys removed at every level."""
    if isinstance(data, dict):
        return {key: strip_fields(value, fields) for key, value in data.items() if key not in fields}
    if isinstance(data, list):
        return [strip_fields(item, fields) for item in data]
    return data
