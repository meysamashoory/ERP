from django import template

from catalog.naming_registry import column_label_map_for_table, resolve_label

register = template.Library()


@register.simple_tag
def system_label(key: str, default: str = "") -> str:
    """Resolve a system naming-key label (falls back to default)."""
    return resolve_label(str(key or ""), default=str(default or ""))


@register.simple_tag
def system_col(table_key: str, column_key: str, default: str = "") -> str:
    """Resolve a table column label from the naming registry."""
    labels = column_label_map_for_table(str(table_key or ""))
    ck = str(column_key or "")
    if ck in labels:
        return labels[ck]
    return default or ck
