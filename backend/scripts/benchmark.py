"""Benchmark runner: `python -m scripts.benchmark [--split dev|heldout|all] [--save]`.

Compares the dependency-graph engine with a keyword baseline on hand-labeled cases in
`benchmark/v1/`. Metric definitions are in `benchmark/v1/README.md`.
"""

import argparse
import json
import re
import statistics
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app import __version__
from app.core import graph as graph_module
from app.core.limits import Limits
from app.core.models import ChangeType, Impact, Label
from app.core.pipeline import AnalysisResult, analyze

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "benchmark" / "v1"


def load_case(case_dir: Path) -> dict:
    def read(version: str) -> dict[str, str]:
        root = case_dir / version
        return {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    return {"id": expected["id"], "expected": expected, "a": read("a"), "b": read("b")}


def load_cases(split: str = "all", dataset: Path = DATASET) -> list[dict]:
    cases = [load_case(d) for d in sorted((dataset / "cases").iterdir()) if d.is_dir()]
    return [c for c in cases if split == "all" or c["expected"]["split"] == split]


# ---- what each system reports -------------------------------------------------------------


def engine_report(result: AnalysisResult) -> dict[tuple[str, str], dict]:
    """(change key, impacted key) -> certainty and the cited location."""
    out = {}
    for change_key, impacts in result.impacts.items():
        for imp in impacts:
            ev = imp.path[-1].evidence if imp.path else None
            out[(change_key, imp.impacted_key)] = {
                "certainty": imp.certainty.value,
                "cite": (ev.file, ev.line_start) if ev else None,
            }
    return out


def baseline_report(result: AnalysisResult) -> dict[tuple[str, str], dict]:
    """Keyword retrieval: every other entity whose text mentions the changed entity's name."""
    entities = {**result.graph_a.entities, **result.graph_b.entities}
    out = {}
    for change in result.changes:
        if change.change_type is ChangeType.ADDED:
            continue
        name = entities[change.key].name
        # Whole-word match. For endpoints the name must not continue into a longer path.
        tail = r"(?![\w/{])" if change.kind.value == "endpoint" else r"(?!\w)"
        pattern = re.compile(rf"(?<!\w){re.escape(name)}{tail}", re.IGNORECASE)
        for key, entity in entities.items():
            if key != change.key and pattern.search(entity.text):
                out[(change.key, key)] = {"certainty": None, "cite": None}
    return out


# ---- evidence validity --------------------------------------------------------------------


def unsupported_reasons(impact: Impact, files: dict[str, int]) -> list[str]:
    """Why an impact is not backed by a valid evidence path. Empty means supported."""
    reasons = []
    if not impact.path:
        return ["empty evidence path"]
    if impact.path[0].target_key != impact.change_key:
        reasons.append("path does not start at the changed entity")
    if impact.path[-1].source_key != impact.impacted_key:
        reasons.append("path does not end at the impacted entity")
    for prev, nxt in zip(impact.path, impact.path[1:], strict=False):
        if nxt.target_key != prev.source_key:
            reasons.append("path edges are not chained")
    for edge in impact.path:
        total = files.get(edge.evidence.file)
        if total is None or not (1 <= edge.evidence.line_start <= edge.evidence.line_end <= total):
            reasons.append(
                f"evidence outside file: {edge.evidence.file}:{edge.evidence.line_start}"
            )
    if impact.certainty is Label.CONFIRMED and any(
        e.label is not Label.CONFIRMED for e in impact.path
    ):
        reasons.append("confirmed impact contains an inferred edge")
    return reasons


# ---- scoring ------------------------------------------------------------------------------


def score_case(case: dict, limits: Limits | None = None) -> dict:
    expected = case["expected"]
    result = analyze(case["a"], case["b"], limits)

    truth = {
        (ck, i["key"]): {
            "certainty": i["certainty"],
            "cite": (i["cite"]["file"], i["cite"]["line"]),
        }
        for ck, items in expected["impacts"].items()
        for i in items
    }
    engine = engine_report(result)
    baseline = baseline_report(result)

    line_counts = {
        name: len(text.splitlines())
        for files in (case["a"], case["b"])
        for name, text in files.items()
    }
    unsupported = [
        (i.change_key, i.impacted_key, r)
        for impacts in result.impacts.values()
        for i in impacts
        if (r := unsupported_reasons(i, line_counts))
    ]

    actual_changes = {c.key: c.classification.value for c in result.changes}
    matched_changes = set(actual_changes) & set(expected["changes"])
    n_files = len(case["a"]) + len(case["b"])
    return {
        "id": case["id"],
        "split": expected["split"],
        "engine": _compare(engine, truth),
        "baseline": _compare(baseline, truth),
        "changes": {
            "expected": len(expected["changes"]),
            "reported": len(actual_changes),
            "matched": len(matched_changes),
            "classified_correctly": sum(
                actual_changes[k] == expected["changes"][k] for k in matched_changes
            ),
        },
        "unsupported_impacts": len(unsupported),
        "unsupported_detail": unsupported,
        "impacts_reported": sum(len(v) for v in result.impacts.values()),
        "ms_per_document": round(result.stats["elapsed_ms"] / n_files, 3),
    }


def _compare(reported: dict, truth: dict) -> dict:
    tp = set(reported) & set(truth)
    confirmed = {k for k, v in reported.items() if v["certainty"] == "confirmed"}
    return {
        "reported": len(reported),
        "expected": len(truth),
        "true_positive": len(tp),
        "missed": sorted(map(list, set(truth) - set(reported))),
        "extra": sorted(map(list, set(reported) - set(truth))),
        "certainty_correct": sum(reported[k]["certainty"] == truth[k]["certainty"] for k in tp),
        "cite_correct": sum(reported[k]["cite"] == truth[k]["cite"] for k in tp),
        "confirmed_reported": len(confirmed),
        "false_confirmed": sum(
            1 for k in confirmed if k not in truth or truth[k]["certainty"] != "confirmed"
        ),
    }


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def aggregate(scores: list[dict]) -> dict:
    """Micro-averaged over all cases: counts are summed, then divided."""

    def total(system: str, field: str) -> int:
        return sum(s[system][field] for s in scores)

    out = {"cases": len(scores)}
    for system in ("engine", "baseline"):
        tp, rep, exp = (total(system, f) for f in ("true_positive", "reported", "expected"))
        out[system] = {
            "precision": _ratio(tp, rep),
            "recall": _ratio(tp, exp),
            "reported": rep,
            "true_positive": tp,
            "expected": exp,
        }
    eng_tp = total("engine", "true_positive")
    out["engine"]["certainty_accuracy"] = _ratio(total("engine", "certainty_correct"), eng_tp)
    out["engine"]["citation_accuracy"] = _ratio(total("engine", "cite_correct"), eng_tp)
    out["engine"]["false_confirmed"] = total("engine", "false_confirmed")
    out["engine"]["false_confirmed_rate"] = _ratio(
        total("engine", "false_confirmed"), total("engine", "confirmed_reported")
    )
    matched = sum(s["changes"]["matched"] for s in scores)
    out["changes"] = {
        "detection_precision": _ratio(matched, sum(s["changes"]["reported"] for s in scores)),
        "detection_recall": _ratio(matched, sum(s["changes"]["expected"] for s in scores)),
        "classification_accuracy": _ratio(
            sum(s["changes"]["classified_correctly"] for s in scores), matched
        ),
    }
    reported_impacts = sum(s["impacts_reported"] for s in scores)
    unsupported = sum(s["unsupported_impacts"] for s in scores)
    out["unsupported_impacts"] = unsupported
    out["unsupported_impact_rate"] = _ratio(unsupported, reported_impacts)
    times = [s["ms_per_document"] for s in scores]
    out["ms_per_document"] = {
        "median": round(statistics.median(times), 3) if times else None,
        "max": max(times) if times else None,
    }
    return out


def run(split: str = "all", dataset: Path = DATASET) -> dict:
    scores = [score_case(c) for c in load_cases(split, dataset)]
    meta = json.loads((dataset / "dataset.json").read_text(encoding="utf-8"))
    return {
        "dataset": {"version": meta["version"], "split": split, "cases": len(scores)},
        "run": {"date": datetime.now(UTC).isoformat(timespec="seconds"), "commit": _commit()},
        "config": {
            "engine_version": __version__,
            "limits": asdict(Limits()),
            "max_depth": 3,
            "name_confidence": graph_module.NAME_CONFIDENCE,
            "property_confidence": graph_module.PROPERTY_CONFIDENCE,
            "property_min_shared": graph_module.PROPERTY_MIN_SHARED,
            "property_min_jaccard": graph_module.PROPERTY_MIN_JACCARD,
            "baseline": "case-insensitive whole-word match of the entity name in other entities",
        },
        "aggregate": aggregate(scores),
        "by_split": {
            s: aggregate([x for x in scores if x["split"] == s])
            for s in ("dev", "heldout")
            if any(x["split"] == s for x in scores)
        },
        "cases": scores,
    }


def _commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def report(result: dict) -> str:
    rows = [
        "| split | system | precision | recall | reported | expected |",
        "|---|---|---|---|---|---|",
    ]
    for split, agg in [*result["by_split"].items(), ("all", result["aggregate"])]:
        for system in ("engine", "baseline"):
            m = agg[system]
            rows.append(
                f"| {split} | {system} | {_fmt(m['precision'])} | {_fmt(m['recall'])} "
                f"| {m['reported']} | {m['expected']} |"
            )
    a = result["aggregate"]
    e, c = a["engine"], a["changes"]
    rows += [
        "",
        f"certainty accuracy {_fmt(e['certainty_accuracy'])}, "
        f"citation accuracy {_fmt(e['citation_accuracy'])}, "
        f"false-confirmed {e['false_confirmed']} (rate {_fmt(e['false_confirmed_rate'])})",
        f"change detection precision {_fmt(c['detection_precision'])}, "
        f"recall {_fmt(c['detection_recall'])}, "
        f"classification accuracy {_fmt(c['classification_accuracy'])}",
        f"unsupported impacts {a['unsupported_impacts']} "
        f"(rate {_fmt(a['unsupported_impact_rate'])}), "
        f"ms per document median {_fmt(a['ms_per_document']['median'])}",
    ]
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    parser.add_argument(
        "--save", action="store_true", help="write benchmark/v1/results/<date>.json"
    )
    parser.add_argument("--details", action="store_true", help="list missed and extra impacts")
    args = parser.parse_args()
    result = run(args.split)
    print(report(result))
    if args.details:
        for case in result["cases"]:
            for system in ("engine", "baseline"):
                s = case[system]
                if s["missed"] or s["extra"]:
                    print(f"\n{case['id']} [{system}] missed={s['missed']} extra={s['extra']}")
    if args.save:
        out = DATASET / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{args.split}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
