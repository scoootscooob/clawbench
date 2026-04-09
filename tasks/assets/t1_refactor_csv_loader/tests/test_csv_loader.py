from csv_loader import load_rows
from report_builder import summarize_inventory


def test_load_rows_skips_comments_and_normalizes_names():
    rows = load_rows(["# ignore", " Apples , 2 ", "bananas,5"])
    assert rows == [{"name": "apples", "count": 2}, {"name": "bananas", "count": 5}]


def test_summarize_inventory_aggregates_counts():
    summary = summarize_inventory(["APPLES,2", "apples,3", "pears,1"])
    assert summary == {"apples": 5, "pears": 1}
