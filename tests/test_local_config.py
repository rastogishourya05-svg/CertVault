import json

from apps.api.local_config import replace_private, write_private


def test_replace_private_atomically_preserves_latest_value(tmp_path):
    path = tmp_path / "pipeline.json"
    write_private(path, json.dumps({"version": 1}))
    replace_private(path, json.dumps({"version": 2}))
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}
    assert sorted(item.name for item in tmp_path.iterdir()) == ["pipeline.json"]
