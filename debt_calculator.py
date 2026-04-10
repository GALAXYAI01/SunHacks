"""
debt_calculator.py — Agent that measures technical debt using **Radon**
(cyclomatic complexity + maintainability index) and projects compound
cost growth.  Part of the PredictiveEng multi-agent AI system.
"""

import os
import math
from pathlib import Path
from typing import Dict

SKIP_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__',
             '.tox', 'dist', 'build', '.eggs', 'vendor'}
SOURCE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rb',
               '.java', '.rs', '.c', '.cpp', '.cs', '.php', '.kt', '.scala'}

HOURLY_RATE = 75          # USD per engineering hour
MONTHLY_INTEREST = 0.15   # 15 % compound rate


def calculate_debt(repo_path: str,
                   file_churn: Dict[str, int] | None = None,
                   test_ratio_pct: float = 0) -> dict:
    """
    Walk code, run Radon on Python, estimate complexity on the rest,
    and project debt growth.

    Returns a dict consumed by the front-end Debt card.
    """
    repo = Path(repo_path)
    file_churn = file_churn or {}

    complexity_hours = 0.0
    maint_hours      = 0.0
    bug_churn_hours  = 0.0
    missing_test_hrs = 0.0

    py_complexities  = []          # per-file CC scores
    mi_scores        = []          # maintainability index scores
    total_source_files = 0

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            fp = Path(root) / name
            if fp.suffix not in SOURCE_EXTS:
                continue

            rel = str(fp.relative_to(repo)).replace("\\", "/")
            total_source_files += 1

            # ── Python files → use Radon for real metrics ────
            if fp.suffix == ".py":
                try:
                    source = fp.read_text(encoding="utf-8", errors="ignore")
                    cc, mi = _radon_analyse(source)
                    py_complexities.append(cc)
                    mi_scores.append(mi)

                    # Debt from complexity  (CC > 10 → 0.5 h per excess point)
                    if cc > 10:
                        complexity_hours += (cc - 10) * 0.5

                    # Debt from low maintainability (MI < 65 → needs work)
                    if mi < 65:
                        maint_hours += (65 - mi) * 0.3
                except Exception:
                    pass

            else:
                # ── Non-Python → heuristic from file size + churn ─
                try:
                    loc = sum(1 for _ in fp.open(encoding="utf-8", errors="ignore"))
                except Exception:
                    loc = 0
                if loc > 500:
                    complexity_hours += (loc - 500) * 0.01
                if loc > 1000:
                    maint_hours += (loc - 1000) * 0.005

            # ── Bug-churn debt ───────────────────────────────
            churn = file_churn.get(rel, 0)
            if churn > 10:
                bug_churn_hours += (churn - 10) * 0.3

    # ── Missing-tests debt ───────────────────────────────────
    if test_ratio_pct < 30:
        missing_test_hrs = total_source_files * (30 - test_ratio_pct) * 0.05

    # ── Totals ───────────────────────────────────────────────
    total_hours = complexity_hours + maint_hours + bug_churn_hours + missing_test_hrs
    total_hours = max(1, round(total_hours))
    principal   = round(total_hours * HOURLY_RATE)

    # ── Compound projection ──────────────────────────────────
    projection = []
    for m in range(1, 7):
        proj_usd = round(principal * math.pow(1 + MONTHLY_INTEREST, m))
        projection.append({"month": f"Month {m}", "debt_usd": proj_usd})

    cost_6m  = projection[5]["debt_usd"] if len(projection) >= 6 else principal
    cost_12m = round(principal * math.pow(1 + MONTHLY_INTEREST, 12))
    growth   = round(cost_12m / max(principal, 1), 1)

    # ── Grade ────────────────────────────────────────────────
    grade = _grade(total_hours)

    # ── Breakdown ────────────────────────────────────────────
    breakdown = {
        "complexity":     round(complexity_hours * HOURLY_RATE),
        "maintainability": round(maint_hours * HOURLY_RATE),
        "bug_churn":      round(bug_churn_hours * HOURLY_RATE),
        "missing_tests":  round(missing_test_hrs * HOURLY_RATE),
    }

    savings = cost_12m - principal

    return {
        "debt_grade":             grade,
        "principal_hours":        total_hours,
        "principal_usd":          principal,
        "cost_in_6_months_usd":  cost_6m,
        "cost_in_12_months_usd": cost_12m,
        "growth_multiple_12m":   growth,
        "monthly_projection":    projection,
        "debt_breakdown_usd":    breakdown,
        "loan_analogy":
            "Technical debt works like a high-interest credit card. "
            "Every month you delay, the compounding interest makes the "
            "eventual payoff more expensive — and your team slower.",
        "roi_of_paying_now":
            f"Paying down this debt today costs ${principal:,}. "
            f"Waiting 12 months turns it into ${cost_12m:,} — "
            f"that's ${savings:,} wasted on 'interest'.",
    }


# ── Radon wrapper ────────────────────────────────────────────────────

def _radon_analyse(source: str):
    """Return (average cyclomatic complexity, maintainability index)."""
    from radon.complexity import cc_visit
    from radon.metrics import mi_visit

    blocks = cc_visit(source)
    if blocks:
        avg_cc = sum(b.complexity for b in blocks) / len(blocks)
    else:
        avg_cc = 1.0

    mi = mi_visit(source, multi=False)
    return round(avg_cc, 2), round(mi, 2)


# ── Grading ──────────────────────────────────────────────────────────

def _grade(hours: float) -> str:
    if hours <= 20:   return "A+"
    if hours <= 50:   return "A"
    if hours <= 120:  return "B"
    if hours <= 300:  return "C"
    if hours <= 600:  return "D"
    return "F"
