import json
from pathlib import Path

from scripts.run_combined_safety_check import _concat_jsonl


def test_concat_jsonl_merges_and_counts(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    dest = tmp_path / "merged.jsonl"

    a.write_text(json.dumps({"id": 1}) + "\n" + json.dumps({"id": 2}) + "\n", encoding="utf-8")
    b.write_text(json.dumps({"id": 3}) + "\n", encoding="utf-8")

    count = _concat_jsonl([a, b], dest)

    assert count == 3
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == [1, 2, 3]


def test_concat_jsonl_skips_missing_files(tmp_path):
    a = tmp_path / "a.jsonl"
    missing = tmp_path / "does_not_exist.jsonl"
    dest = tmp_path / "merged.jsonl"

    a.write_text(json.dumps({"id": 1}) + "\n", encoding="utf-8")

    count = _concat_jsonl([a, missing], dest)

    assert count == 1
    assert dest.exists()


def test_concat_jsonl_skips_blank_lines(tmp_path):
    a = tmp_path / "a.jsonl"
    dest = tmp_path / "merged.jsonl"
    a.write_text(json.dumps({"id": 1}) + "\n\n   \n" + json.dumps({"id": 2}) + "\n", encoding="utf-8")

    count = _concat_jsonl([a], dest)

    assert count == 2


def test_concat_jsonl_no_sources_creates_empty_dest(tmp_path):
    dest = tmp_path / "merged.jsonl"
    count = _concat_jsonl([], dest)
    assert count == 0
    assert dest.read_text(encoding="utf-8") == ""
