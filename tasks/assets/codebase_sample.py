"""Sample codebase for review and testing tasks."""


def calculate_average(numbers: list[float]) -> float:
    """Calculate the average of a list of numbers."""
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)  # Bug: division by zero if empty list


def find_duplicates(items: list) -> list:
    """Find duplicate items in a list."""
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        seen.add(item)
    return duplicates


def merge_dicts(dict_a: dict, dict_b: dict) -> dict:
    """Merge two dictionaries. Values from dict_b take precedence."""
    result = dict_a.copy()
    result.update(dict_b)
    return result


def parse_csv_line(line: str) -> list[str]:
    """Parse a single CSV line into fields."""
    return line.split(",")  # Bug: doesn't handle quoted fields with commas


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value between minimum and maximum."""
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
