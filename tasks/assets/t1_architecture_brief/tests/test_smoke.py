from app import render_total


def test_render_total():
    assert render_total(1299, 2) == "$25.98"

