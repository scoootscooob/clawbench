def summarize_inventory(lines: list[str]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_name, raw_count = line.split(",", 1)
        name = raw_name.strip().lower()
        count = int(raw_count.strip())
        summary[name] = summary.get(name, 0) + count
    return summary

