from report_client import API_PATH, REQUIRED_HEADERS


def test_reporting_api_path():
    assert API_PATH == "/v2/reports"


def test_workspace_header_is_required():
    assert "X-Workspace-Id" in REQUIRED_HEADERS

