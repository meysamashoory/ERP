from django import template
import json

from planning.uid import parse_program_number
from planning.utils import format_jdate

register = template.Library()


@register.filter(name="jdate")
def jdate_filter(value):
    """Format a Jalali date as YYYY/MM/DD."""
    return format_jdate(value)


@register.filter(name="program_no")
def program_no_filter(value):
    """Numeric program number for display (e.g. BP-159 → 159)."""
    try:
        return parse_program_number(value)
    except Exception:
        return value or ""


@register.filter(name="as_json")
def as_json_filter(value):
    """Serialize a value to a JSON string for HTML data attributes."""
    return json.dumps(value if value is not None else [], ensure_ascii=False)
