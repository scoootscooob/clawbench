from csv_loader import load_rows
from report_builder import summarize_inventory


def test_load_rows_skips_comments_and_normalizes_names():
    # load_rows returns lowercase-normalized names (matches stored SKU keys).
    rows = load_rows(["# ignore", " Apples , 2 ", "bananas,5"])
    assert rows == [{"name": "apples", "count": 2}, {"name": "bananas", "count": 5}]


def test_summarize_inventory_aggregates_case_insensitively_preserving_display_case():
    # summarize_inventory aggregates case-insensitively BUT keeps the first-seen
    # original display case (APPLES + apples both roll up under "APPLES").
    # This is distinct from load_rows's lowercase normalization — any shared
    # helper must accommodate BOTH behaviors without duplicating the parsing.
    summary = summarize_inventory(["APPLES,2", "apples,3", "pears,1"])
    assert summary == {"APPLES": 5, "pears": 1}


def test_summarize_inventory_preserves_first_seen_case_across_variants():
    summary = summarize_inventory(["Bread,1", "BREAD,2", "bread,3"])
    assert summary == {"Bread": 6}
