"""Evaluate the rule classifier on the synthetic fixture: python scripts/eval_jobs_classifier.py

Messages rejected by the keyword prefilter count as noise. Exit code 1 if precision is below the J2 thresholds.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.jobs_radar_keywords import KEYWORDS  # noqa: E402
from app.jobs_radar.classifier import LABELS, RuleClassifier  # noqa: E402
from app.jobs_radar.prefilter import check  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "jobs_messages.jsonl"
THRESHOLDS = {"agency_vacancy": 0.85, "seeker_question": 0.80}


def load(path: Path = FIXTURES) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def predict(rows: list[dict]) -> list[str]:
    include = [t for t, _, k in KEYWORDS if k == "include"]
    exclude = [t for t, _, k in KEYWORDS if k == "exclude"]
    clf = RuleClassifier()
    out = []
    for row in rows:
        if not check(row["text"], include, exclude).passed:
            out.append("noise")
        else:
            out.append(clf.classify_sync(row["text"]).label)
    return out


def metrics(pairs: list[tuple[bool, bool]]) -> tuple[int, int, int, int]:
    """pairs are (expected, predicted); returns TP, FP, FN, TN."""
    tp = sum(e and g for e, g in pairs)
    fp = sum((not e) and g for e, g in pairs)
    fn = sum(e and not g for e, g in pairs)
    tn = sum((not e) and (not g) for e, g in pairs)
    return tp, fp, fn, tn


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def evaluate(rows: list[dict]) -> dict[str, dict[str, float]]:
    expected = [r["label"] for r in rows]
    got = predict(rows)
    result = {}
    for label in LABELS:
        tp, fp, fn, _ = metrics([(e == label, g == label) for e, g in zip(expected, got)])
        prec, rec, f1 = prf(tp, fp, fn)
        result[label] = {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn,
                         "support": sum(e == label for e in expected)}
    return result


def confusion(rows: list[dict]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for r, g in zip(rows, predict(rows)):
        counts[(r["label"], g)] = counts.get((r["label"], g), 0) + 1
    return counts


def report(rows: list[dict]) -> None:
    res = evaluate(rows)
    print(f"{'label':<18}{'precision':>10}{'recall':>10}{'F1':>8}{'support':>9}")
    for label in LABELS:
        m = res[label]
        print(f"{label:<18}{m['precision']:>10.2f}{m['recall']:>10.2f}{m['f1']:>8.2f}{int(m['support']):>9}")
    print("\nconfusion (expected -> predicted):")
    for (exp, got), n in sorted(confusion(rows).items()):
        if exp != got:
            print(f"  {exp} -> {got}: {n}")
    clf = RuleClassifier()
    graded = [(r, clf.classify_sync(r["text"])) for r in rows if r["label"] in ("agency_vacancy", "seeker_question")]
    for field in ("city", "profession", "language"):
        hits = sum(getattr(c, field) == r[{"language": "lang"}.get(field, field)] for r, c in graded)
        print(f"{field} accuracy on agency/seeker rows: {hits}/{len(graded)}")


def main() -> int:
    rows = load()
    report(rows)
    res = evaluate(rows)
    failed = [f"{k} precision {res[k]['precision']:.2f} < {v:.2f}" for k, v in THRESHOLDS.items() if res[k]["precision"] < v]
    for line in failed:
        print("FAIL:", line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
