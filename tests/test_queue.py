from clawbench.queue import SubmissionRequest


def test_submission_request_defaults_to_single_parallel_lane():
    request = SubmissionRequest(model="openai-codex/gpt-5.4")

    assert request.max_parallel_lanes == 1
