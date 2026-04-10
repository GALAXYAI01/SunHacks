"""
deployment_readiness.py — Agent that runs 15 deployment-readiness checks
covering infrastructure, security, observability, and repo hygiene.
Part of the PredictiveEng multi-agent AI system.
"""

import os
from pathlib import Path
from typing import List


def check_deployment_readiness(repo_path: str,
                               has_tests: bool = False,
                               security_label: str = "UNKNOWN") -> dict:
    """
    Run every check against the repo on disk.
    Returns readiness_score (0-100), per-category scores, fix list,
    and a production_blocker flag.
    """
    repo = Path(repo_path)
    checks: List[dict] = []

    # ── Infrastructure ───────────────────────────────────────
    checks.append(_check(
        "Dockerfile",
        _any_exists(repo, ["Dockerfile", "dockerfile", "Containerfile"]),
        "infrastructure", "HIGH", "30 min", 8,
    ))
    checks.append(_check(
        "Docker Compose",
        _any_exists(repo, ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]),
        "infrastructure", "MEDIUM", "20 min", 5,
    ))
    checks.append(_check(
        "CI/CD Pipeline",
        _has_ci(repo),
        "infrastructure", "HIGH", "1 hour", 9,
    ))
    checks.append(_check(
        "Environment Config Template",
        _any_exists(repo, [".env.example", ".env.sample", "env.template"]),
        "infrastructure", "LOW", "10 min", 3,
    ))

    # ── Security ─────────────────────────────────────────────
    checks.append(_check(
        ".gitignore present",
        (repo / ".gitignore").exists(),
        "security", "HIGH", "5 min", 7,
    ))
    checks.append(_check(
        "No .env committed",
        not (repo / ".env").exists(),
        "security", "CRITICAL", "5 min", 10,
    ))
    checks.append(_check(
        "Security scan clean",
        security_label in ("GOOD", "FAIR"),
        "security", "HIGH", "2 hours", 9,
    ))
    checks.append(_check(
        "Dependency lock file",
        _any_exists(repo, [
            "requirements.txt", "Pipfile.lock", "poetry.lock",
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "Gemfile.lock", "go.sum", "Cargo.lock",
        ]),
        "security", "MEDIUM", "15 min", 6,
    ))

    # ── Observability ────────────────────────────────────────
    checks.append(_check(
        "Logging configuration",
        _has_logging(repo),
        "observability", "MEDIUM", "1 hour", 5,
    ))
    checks.append(_check(
        "Health-check endpoint or script",
        _any_exists(repo, ["healthcheck.py", "healthcheck.sh", "health.py"]) or _grep_exists(repo, "healthcheck", [".py",".js",".ts",".go"]),
        "observability", "HIGH", "30 min", 7,
    ))
    checks.append(_check(
        "Error tracking setup",
        _grep_exists(repo, "sentry", [".py",".js",".ts",".toml",".json"]),
        "observability", "LOW", "1 hour", 4,
    ))

    # ── Hygiene ──────────────────────────────────────────────
    checks.append(_check(
        "README present",
        _any_exists(repo, ["README.md", "README.rst", "README.txt", "README"]),
        "hygiene", "LOW", "30 min", 4,
    ))
    checks.append(_check(
        "CONTRIBUTING guide",
        _any_exists(repo, ["CONTRIBUTING.md", "CONTRIBUTING.rst"]),
        "hygiene", "LOW", "20 min", 2,
    ))
    checks.append(_check(
        "LICENSE file",
        _any_exists(repo, ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]),
        "hygiene", "LOW", "5 min", 3,
    ))
    checks.append(_check(
        "Automated tests exist",
        has_tests,
        "hygiene", "HIGH", "4 hours", 8,
    ))

    # ── Scoring ──────────────────────────────────────────────
    total_weight  = sum(c["weight"] for c in checks)
    passed_weight = sum(c["weight"] for c in checks if c["passed"])
    readiness     = round(passed_weight / max(total_weight, 1) * 100)

    label = (
        "READY"        if readiness >= 85 else
        "MOSTLY READY" if readiness >= 60 else
        "NOT READY"    if readiness >= 35 else
        "BLOCKER"
    )

    # Category sub-scores
    cats = {}
    for cat in ("infrastructure", "security", "observability", "hygiene"):
        cat_checks = [c for c in checks if c["category"] == cat]
        tw = sum(c["weight"] for c in cat_checks) or 1
        pw = sum(c["weight"] for c in cat_checks if c["passed"])
        cats[cat] = round(pw / tw * 100)

    # Production blocker?
    blocker = any(not c["passed"] and c["severity"] == "CRITICAL" for c in checks)

    # Fix list (failed checks, sorted by weight desc)
    fix_list = sorted(
        [c for c in checks if not c["passed"]],
        key=lambda c: c["weight"],
        reverse=True,
    )

    passed_count = sum(1 for c in checks if c["passed"])

    return {
        "readiness_score":   readiness,
        "readiness_label":   label,
        "checks":            checks,
        "passed_count":      passed_count,
        "total_checks":      len(checks),
        "production_blocker": blocker,
        "category_scores":   cats,
        "fix_list":          fix_list,
    }


# ── helpers ──────────────────────────────────────────────────────────

def _check(name, passed, category, severity, effort, weight):
    return {
        "check":    name,
        "passed":   bool(passed),
        "category": category,
        "severity": severity,
        "effort":   effort,
        "weight":   weight,
    }


def _any_exists(repo: Path, names: list) -> bool:
    for n in names:
        if (repo / n).exists():
            return True
    return False


def _has_ci(repo: Path) -> bool:
    ci_paths = [
        ".github/workflows",
        ".gitlab-ci.yml",
        ".circleci",
        "Jenkinsfile",
        ".travis.yml",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        ".buildkite",
    ]
    for p in ci_paths:
        full = repo / p
        if full.exists():
            return True
    return False


def _has_logging(repo: Path) -> bool:
    """Check if there's any logging setup (crude heuristic)."""
    markers = ["logging.config", "logging.basicConfig", "getLogger",
               "winston", "pino", "log4j", "slog", "logrus"]
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in
                   {'.git','node_modules','venv','__pycache__','dist'}]
        for name in files:
            fp = Path(root) / name
            if fp.suffix in (".py", ".js", ".ts", ".go", ".java"):
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")[:5000]
                    if any(m in text for m in markers):
                        return True
                except Exception:
                    pass
    return False


def _grep_exists(repo: Path, needle: str, exts: list) -> bool:
    """Quick grep for a keyword across the repo."""
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in
                   {'.git','node_modules','venv','__pycache__','dist'}]
        for name in files:
            fp = Path(root) / name
            if fp.suffix in exts:
                try:
                    if needle.lower() in fp.read_text(encoding="utf-8", errors="ignore")[:5000].lower():
                        return True
                except Exception:
                    pass
    return False
