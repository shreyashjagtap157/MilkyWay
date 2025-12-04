def safe_str(value):
    """Return string representation of value, or empty string for None.

    Keeps behavior consistent across the project when concatenating or joining
    heterogeneous field types (e.g., IntegerField + CharField).
    """
    return "" if value is None else str(value)


def format_address(
    *,
    flat_no=None,
    building=None,
    street=None,
    area=None,
    village=None,
    tal=None,
    dist=None,
    city=None,
    state=None,
    pincode=None,
    extra_parts=None,
):
    """Format a postal-style address from common model fields.

    All parts are converted to strings safely and empty/None parts are omitted.
    The resulting address is a single comma-separated string.
    """
    parts = [
        safe_str(flat_no),
        safe_str(building),
        safe_str(street),
        safe_str(area),
        safe_str(village),
        safe_str(tal),
        safe_str(dist),
        safe_str(city),
        safe_str(state),
        safe_str(pincode),
    ]
    if extra_parts:
        parts.extend(safe_str(p) for p in extra_parts)
    return ", ".join(p for p in parts if p)
