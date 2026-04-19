def summarize_inventory(lines: list[str]) -> dict[str, int]:
    """Aggregate counts per item. Case-insensitive bucketing but the output
    key uses the FIRST-seen display case (so a user-facing report keeps the
    original capitalization as entered)."""
    summary: dict[str, int] = {}
    display_name: dict[str, str] = {}  # lowercase key -> first-seen original
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_name, raw_count = line.split(",", 1)
        original = raw_name.strip()
        key = original.lower()
        count = int(raw_count.strip())
        if key not in display_name:
            display_name[key] = original
        # Aggregate under the display-name (first-seen case)
        display = display_name[key]
        summary[display] = summary.get(display, 0) + count
    return summary
