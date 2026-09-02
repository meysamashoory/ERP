from django import template

from catalog.naming_registry import column_label_map_for_table, resolve_label

register = template.Library()


@register.simple_tag
def system_label(key: str, default: str = "") -> str:
    """Resolve a system naming-key label (falls back to default)."""
    return resolve_label(str(key or ""), default=str(default or ""))


@register.simple_tag(takes_context=True)
def system_col(context, table_key: str, column_key: str, default: str = "") -> str:
    """Resolve a table column label from the naming registry (one query per table)."""
    tk = str(table_key or "")
    ck = str(column_key or "")
    cache = context.render_context.setdefault("_system_col_maps", {})
    if tk not in cache:
        cache[tk] = column_label_map_for_table(tk)
    labels = cache[tk]
    if ck in labels:
        return labels[ck]
    return default or ck
