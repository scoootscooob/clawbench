from scheduler import format_run_window


def test_aware_timestamp_keeps_original_offset_before_utc_normalization():
    assert format_run_window("2026-02-01T09:30:00+02:00") == "2026-02-01T07:30:00+00:00"


def test_utc_timestamp_round_trips():
    assert format_run_window("2026-02-01T09:30:00+00:00") == "2026-02-01T09:30:00+00:00"

