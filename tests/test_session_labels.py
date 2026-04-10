from clawbench.session_labels import unique_session_label


def test_unique_session_label_preserves_prefix_shape_and_uniqueness():
    label_a = unique_session_label("clawbench-startup-probe")
    label_b = unique_session_label("clawbench-startup-probe")

    assert label_a.startswith("clawbench-startup-probe-")
    assert label_b.startswith("clawbench-startup-probe-")
    assert label_a != label_b


def test_unique_session_label_normalizes_unsafe_characters():
    label = unique_session_label("clawbench judge / task:1")

    assert label.startswith("clawbench-judge-task-1-")
