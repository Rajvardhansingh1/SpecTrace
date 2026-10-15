import copy
import json

import pytest

from app.core.models import Edge, Impact, Label, Location
from app.core.pipeline import analyze
from scripts import benchmark as bm


def strip_volatile(result: dict) -> dict:
    out = copy.deepcopy(result)
    out["run"] = {}
    out["aggregate"]["ms_per_document"] = {}
    for scope in out["by_split"].values():
        scope["ms_per_document"] = {}
    for case in out["cases"]:
        case["ms_per_document"] = 0
    return out


@pytest.fixture(scope="module")
def full_run():
    return bm.run("all")


def test_dataset_files_match_dataset_json():
    meta = json.loads((bm.DATASET / "dataset.json").read_text(encoding="utf-8"))
    cases = bm.load_cases()
    assert len(cases) == meta["cases"]
    listed = {c.split("-")[0] for names in meta["splits"].values() for c in names}
    assert {c["id"].split("-")[0] for c in cases} == listed
    for c in cases:
        split = c["expected"]["split"]
        assert c["id"].split("-")[0] in meta["splits"][split]


def test_every_label_points_at_the_quoted_line():
    for case in bm.load_cases():
        side = case["a"] if case["id"] == "c03-endpoint-removed" else case["b"]
        for items in case["expected"]["impacts"].values():
            for item in items:
                cite = item["cite"]
                line = side[cite["file"]].splitlines()[cite["line"] - 1]
                assert line.strip() == cite["text"], (case["id"], item["key"])


def test_labeled_entities_exist_in_the_cases():
    for case in bm.load_cases():
        result = analyze(case["a"], case["b"])
        known = {**result.graph_a.entities, **result.graph_b.entities}
        for change_key, items in case["expected"]["impacts"].items():
            assert change_key in known, (case["id"], change_key)
            for item in items:
                assert item["key"] in known, (case["id"], item["key"])


def test_no_unsupported_impacts_and_no_false_confirmed(full_run):
    agg = full_run["aggregate"]
    assert agg["unsupported_impacts"] == 0
    assert agg["engine"]["false_confirmed"] == 0
    assert agg["changes"]["detection_recall"] == 1.0


def test_benchmark_is_reproducible(full_run):
    again = bm.run("all")
    assert strip_volatile(full_run) == strip_volatile(again)


def test_result_records_dataset_version_and_configuration(full_run):
    assert full_run["dataset"] == {"version": "v1", "split": "all", "cases": 14}
    cfg = full_run["config"]
    assert cfg["max_depth"] == 3 and cfg["property_min_jaccard"] == 0.75
    assert set(full_run["by_split"]) == {"dev", "heldout"}


def test_split_filter_selects_only_that_split():
    assert {c["expected"]["split"] for c in bm.load_cases("heldout")} == {"heldout"}


def test_engine_does_not_report_generic_word_as_impact(full_run):
    case = next(c for c in full_run["cases"] if c["id"] == "c06-unrelated-generic-word")
    assert case["engine"]["reported"] == 0
    assert case["baseline"]["extra"], "the keyword baseline should be fooled by the word 'item'"


def test_baseline_matches_whole_words_and_exact_endpoint_paths():
    files_a = {"a.md": "## Pets\nUse `GET /pets` here.\n\nUse `GET /pets/{id}` there.\n"}
    files_b = {"a.md": files_a["a.md"]}
    spec_a = (
        "openapi: 3.0.0\npaths:\n  /pets:\n    get:\n      summary: x\n      responses:\n"
        '        "200":\n          description: ok\n'
    )
    spec_b = spec_a.replace("summary: x", "summary: x\n      deprecated: true").replace(
        "responses:",
        "parameters:\n        - name: q\n          in: query\n          required: true\n"
        "          schema:\n            type: string\n      responses:",
        1,
    )
    result = analyze({**files_a, "o.yaml": spec_a}, {**files_b, "o.yaml": spec_b})
    report = bm.baseline_report(result)
    assert ("endpoint:GET /pets", "section:a.md#pets") in report
    # A longer path is not a mention of the shorter one: only one section entity matches, once.
    assert len([k for k in report if k[1].startswith("section:")]) == 1


def _edge(src, dst, label=Label.CONFIRMED, line=1, file="a.md"):
    return Edge(
        source_key=src,
        target_key=dst,
        relation="r",
        label=label,
        confidence=1.0,
        evidence=Location(file=file, line_start=line, line_end=line),
        reason="t",
    )


def _impact(path, certainty=Label.CONFIRMED, change="c", impacted="i"):
    return Impact(
        change_key=change,
        impacted_key=impacted,
        certainty=certainty,
        confidence=1.0,
        path=path,
        confirmed_breaking=False,
        summary="s",
    )


def test_unsupported_reasons_flags_each_kind_of_broken_evidence():
    files = {"a.md": 5}
    good = _impact([_edge("i", "c")])
    assert bm.unsupported_reasons(good, files) == []
    assert bm.unsupported_reasons(_impact([]), files) == ["empty evidence path"]
    assert any(
        "does not start" in r for r in bm.unsupported_reasons(_impact([_edge("i", "x")]), files)
    )
    assert any(
        "does not end" in r for r in bm.unsupported_reasons(_impact([_edge("x", "c")]), files)
    )
    assert any(
        "outside file" in r
        for r in bm.unsupported_reasons(_impact([_edge("i", "c", line=9)]), files)
    )
    assert any(
        "outside file" in r
        for r in bm.unsupported_reasons(_impact([_edge("i", "c", file="z.md")]), files)
    )
    mixed = _impact([_edge("m", "c"), _edge("i", "m", Label.INFERRED)])
    assert any("inferred edge" in r for r in bm.unsupported_reasons(mixed, files))
    unchained = _impact([_edge("m", "c"), _edge("i", "other")])
    assert any("not chained" in r for r in bm.unsupported_reasons(unchained, files))


def test_aggregate_is_micro_averaged_and_handles_empty_denominators():
    def system(tp, rep, exp, conf=0, false_conf=0):
        return {
            "true_positive": tp,
            "reported": rep,
            "expected": exp,
            "certainty_correct": tp,
            "cite_correct": tp,
            "confirmed_reported": conf,
            "false_confirmed": false_conf,
            "missed": [],
            "extra": [],
        }

    changes = {"expected": 1, "reported": 1, "matched": 1, "classified_correctly": 1}

    def case(eng, base):
        return {
            "engine": eng,
            "baseline": base,
            "changes": changes,
            "unsupported_impacts": 0,
            "impacts_reported": eng["reported"],
            "ms_per_document": 1.0,
            "split": "dev",
        }

    scores = [case(system(1, 1, 1), system(0, 1, 1)), case(system(3, 4, 4), system(1, 1, 4))]
    agg = bm.aggregate(scores)
    assert agg["engine"]["precision"] == 0.8 and agg["engine"]["recall"] == 0.8
    assert agg["baseline"]["precision"] == 0.5 and agg["baseline"]["recall"] == 0.2
    empty = bm.aggregate([case(system(0, 0, 0), system(0, 0, 0))])
    assert empty["engine"]["precision"] is None and empty["engine"]["recall"] is None
    assert empty["engine"]["false_confirmed_rate"] is None


def test_report_text_and_saved_file(tmp_path, monkeypatch, full_run, capsys):
    text = bm.report(full_run)
    assert "| all | engine |" in text and "unsupported impacts 0" in text
    monkeypatch.setattr(bm, "DATASET", tmp_path)
    monkeypatch.setattr("sys.argv", ["benchmark", "--split", "heldout", "--save"])
    monkeypatch.setattr(
        bm, "run", lambda split: {**full_run, "dataset": {**full_run["dataset"], "split": split}}
    )
    bm.main()
    assert "heldout" in capsys.readouterr().out
    saved = list((tmp_path / "results").glob("*-heldout.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["dataset"]["split"] == "heldout"
