"""Input parsing and validation shared by all services."""
import datetime as dt
import math
import re

from crm.errors import ValidationError

TRUE_WORDS = ('1', 'true', 'yes', 'on')
BOOL_WORDS = TRUE_WORDS + ('0', 'false', 'no', 'off', '')
PHONE_RE = re.compile(r'\d{10}')


def text(value, max_length=500):
    """Trimmed string ('' for None), capped to a sane length."""
    return str(value if value is not None else '').strip()[:max_length]


def optional_text(value, max_length=500):
    return text(value, max_length) or None


def required_text(value, field, max_length=500):
    result = text(value, max_length)
    if not result:
        raise ValidationError(f'{field} is required.')
    return result


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in TRUE_WORDS


def strict_bool(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in BOOL_WORDS:
        return parse_bool(value)
    raise ValidationError(f'{field} must be true or false.')


def number(value, default=0.0):
    """Lenient number parsing for spreadsheet-style input ('1,200', '₹50')."""
    if value is None or value == '':
        return default
    try:
        result = float(str(value).replace(',', '').replace('₹', '').strip())
    except ValueError:
        return default
    return result if math.isfinite(result) else default


def amount(value, field, minimum=0.0, allow_equal=True, default=None):
    """A finite number with a lower bound; raises a clear error otherwise."""
    if (value is None or value == '') and default is not None:
        return default
    result = number(value, default=float('nan'))
    if math.isnan(result):
        raise ValidationError(f'{field} must be a number.')
    if result < minimum or (not allow_equal and result == minimum):
        comparison = 'at least' if allow_equal else 'greater than'
        raise ValidationError(f'{field} must be {comparison} {minimum:g}.')
    return result


def positive(value, field):
    return amount(value, field, minimum=0, allow_equal=False)


def integer_id(value, field):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'{field} is required.')
    if result <= 0:
        raise ValidationError(f'{field} is required.')
    return result


def iso_date(value, field, required=False):
    raw = text(value, 20)
    if not raw:
        if required:
            raise ValidationError(f'{field} is required.')
        return None
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValidationError(f'{field} must be a valid date (YYYY-MM-DD).')


def phone(value):
    result = text(value, 20)
    if result and not PHONE_RE.fullmatch(result):
        raise ValidationError('Mobile number must be exactly 10 digits.')
    return result


def one_of(value, choices, field, default=None):
    result = text(value, 50).upper() or default
    if result not in choices:
        raise ValidationError(f'{field} must be one of: {", ".join(choices)}.')
    return result
