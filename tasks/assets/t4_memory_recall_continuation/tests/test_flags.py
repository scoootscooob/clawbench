from flags import BETA_REGIONS, RETRY_BUDGET


def test_beta_regions():
    assert BETA_REGIONS == ["us", "eu"]


def test_retry_budget():
    assert RETRY_BUDGET == 3

