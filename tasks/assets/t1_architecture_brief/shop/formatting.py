def format_cents(value: int) -> str:
    dollars = value / 100
    return f"${dollars:0.2f}"

