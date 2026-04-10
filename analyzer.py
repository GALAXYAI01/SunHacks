"""
analyzer.py — Main orchestrator for the PredictiveEng multi-agent AI system.

Coordinates six specialised analysis agents:
    1. Security Agent      (security_scanner.py)
    2. Burnout Agent       (burnout_detector.py)
    3. Cascade Agent       (cascade_analyzer.py)
    4. Debt Agent          (debt_calculator.py)   — uses **Radon**
    5. Deployment Agent    (deployment_readiness.py)
    6. AI Reporter Agent   (ai_reporter.py)       — uses **LangChain + Groq / LLM**

Uses: GitHub REST API, PyDriller (commit mining), Radon (complexity),
      GitPython (cloning).
"""

import os
import re
import tempfile
import shutil
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List

import requests
import git
from pydriller import Repository

from security_scanner import scan_security, analyze_dependencies
from burnout_detector import analyze_burnout
from cascade_analyzer import analyze_cascade
from debt_calculator import calculate_debt
from deployment_readiness import check_deployment_readiness

# ── Constants ────────────────────────────────────────────────────────
SOURCE_EXTS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rb', '.java', '.rs',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.swift', '.kt', '.scala', '.php',
    '.vue', '.svelte',
}
TEST_KEYWORDS = [
    'test_', '_test.', '.test.', 'spec.', '_spec.',
    'tests/', 'test/', '__tests__/', 'spec/',
]
SKIP_DIRS = {
    '.git', 'node_modules', 'venv', '.venv', '__pycache__',
    '.tox', 'dist', 'build', '.eggs', 'vendor', '.next',
}


class GitHubAnalyzer:
    """
    Multi-agent orchestrator.

    Each sub-analyser is an independent *agent* that examines one dimension
    of code health.  This orchestrator clones the repo, mines commit history
    with **PyDriller**, then dispatches data to every agent and synthesises
    a unified health report.
    """

    def __init__(self, github_token: str):
        self.token = github_token
        self.headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    # ═══════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ═══════════════════════════════════════════════════════════════════

    def run_full_analysis(self, repo_url: str) -> Dict[str, Any]:
        """
        Full pipeline:
            clone → mine commits → run all 5 agents → score → predict → return.
        """
        owner, name = self._parse_url(repo_url)
        repo_info = self._fetch_repo_info(owner, name)

        temp_dir = tempfile.mkdtemp(prefix="predictiveeng_")
        try:
            # ── Clone ─────────────────────────────────────────
            self._clone_repo(repo_url, temp_dir)

            # ── Agent 0: Commit mining (PyDriller) ────────────
            since = datetime.now() - timedelta(days=365)
            commits, file_churn, weekly_commits, contrib = \
                self._mine_commits(temp_dir, since)

            bus_factor      = self._compute_bus_factor(contrib)
            top_contributors = self._top_contributors(contrib)
            test_coverage   = self._test_coverage(temp_dir)

            # ── Agent 1: Security ─────────────────────────────
            security        = scan_security(temp_dir)
            dependency_risk = analyze_dependencies(temp_dir)

            # ── Agent 2: Burnout ──────────────────────────────
            burnout = analyze_burnout(commits)

            # ── Agent 3: Cascade ──────────────────────────────
            cascade_risk = analyze_cascade(temp_dir, file_churn)

            # ── Agent 4: Technical Debt (Radon) ───────────────
            technical_debt = calculate_debt(
                temp_dir, file_churn,
                test_coverage.get("test_to_source_ratio_pct", 0),
            )

            # ── Agent 5: Deployment Readiness ─────────────────
            deployment = check_deployment_readiness(
                temp_dir,
                has_tests=test_coverage.get("test_files", 0) > 0,
                security_label=security.get("security_label", "UNKNOWN"),
            )

            # ── Orchestrator: Health scoring ──────────────────
            health_scores = self._health_scores(
                security, dependency_risk, test_coverage,
                burnout, cascade_risk, technical_debt,
                deployment, file_churn, contrib,
                weekly_commits, commits,
            )

            return {
                "repo_info":             repo_info,
                "analyzed_at":           datetime.utcnow().isoformat() + "Z",
                "health_scores":         health_scores,
                "commit_analysis": {
                    "bus_factor":        bus_factor,
                    "top_contributors":  top_contributors,
                    "total_commits":     len(commits),
                    "weekly_commits":    weekly_commits,
                },
                "security":              security,
                "dependency_risk":       dependency_risk,
                "test_coverage":         test_coverage,
                "burnout":               burnout,
                "cascade_risk":          cascade_risk,
                "technical_debt":        technical_debt,
                "deployment_readiness":  deployment,
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — repo helpers
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _parse_url(url: str):
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        parts = url.split("/")
        return parts[-2], parts[-1]

    def _fetch_repo_info(self, owner: str, name: str) -> dict:
        """Fetch metadata via the GitHub REST API."""
        fallback = {
            "full_name": f"{owner}/{name}", "language": "Unknown",
            "stars": 0, "open_issues": 0, "description": "",
            "default_branch": "main", "size_kb": 0, "forks": 0,
            "created_at": "",
        }
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{name}",
                headers=self.headers, timeout=15,
            )
            if r.status_code == 200:
                d = r.json()
                return {
                    "full_name":      d.get("full_name", fallback["full_name"]),
                    "language":       d.get("language") or "Unknown",
                    "stars":          d.get("stargazers_count", 0),
                    "open_issues":    d.get("open_issues_count", 0),
                    "description":    d.get("description", ""),
                    "default_branch": d.get("default_branch", "main"),
                    "size_kb":        d.get("size", 0),
                    "forks":          d.get("forks_count", 0),
                    "created_at":     d.get("created_at", ""),
                }
        except Exception:
            pass
        return fallback

    def _clone_repo(self, repo_url: str, dest: str):
        """Clone with token-based HTTPS auth."""
        url = repo_url
        if "github.com" in url:
            url = url.replace("https://", f"https://x-access-token:{self.token}@")
        elif "gitlab.com" in url:
            url = url.replace("https://", f"https://oauth2:{self.token}@")
        if not url.endswith(".git"):
            url += ".git"
        git.Repo.clone_from(url, dest)

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — commit mining (PyDriller)
    # ═══════════════════════════════════════════════════════════════════

    def _mine_commits(self, repo_path, since):
        commits:   List[dict]       = []
        churn:     Dict[str, int]   = defaultdict(int)
        weekly:    Dict[str, int]   = defaultdict(int)
        contrib:   Dict[str, dict]  = defaultdict(lambda: {
            "commits": 0, "files_touched": set(),
            "lines_added": 0, "lines_deleted": 0,
        })

        try:
            for c in Repository(repo_path, since=since).traverse_commits():
                author = c.author.name
                dt     = c.author_date

                n_files = 0
                for m in c.modified_files:
                    if m.new_path:
                        churn[m.new_path] += 1
                        contrib[author]["files_touched"].add(m.new_path)
                    n_files += 1
                    contrib[author]["lines_added"]   += m.added_lines   or 0
                    contrib[author]["lines_deleted"]  += m.deleted_lines or 0

                commits.append({
                    "author": author, "date": dt,
                    "message": c.msg or "",
                    "is_merge": c.merge,
                    "files_changed": n_files,
                    "hash": c.hash[:8],
                })
                contrib[author]["commits"] += 1
                if dt:
                    weekly[dt.strftime("%Y-W%U")] += 1
        except Exception as exc:
            print(f"[PyDriller] Warning: {exc}")

        sorted_weeks = sorted(weekly.items())[-12:]
        weekly_list  = [{"week": w, "commits": n} for w, n in sorted_weeks]

        return commits, dict(churn), weekly_list, dict(contrib)

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — bus factor
    # ═══════════════════════════════════════════════════════════════════

    def _compute_bus_factor(self, contrib: dict) -> dict:
        if not contrib:
            return {"bus_number": 0, "risk_level": "CRITICAL",
                    "top_author_owns_pct": 100,
                    "interpretation": "No contributor data available."}

        ranked = sorted(contrib.items(),
                        key=lambda x: x[1]["commits"], reverse=True)
        all_files = set()
        for _, s in ranked:
            all_files |= s["files_touched"]
        total = len(all_files) or 1

        cumul = set()
        bus = 0
        for _, s in ranked:
            cumul |= s["files_touched"]
            bus += 1
            if len(cumul) >= total * 0.5:
                break

        top_pct = round(
            len(ranked[0][1]["files_touched"]) / total * 100, 1
        ) if ranked else 0

        if bus <= 1:
            risk, interp = "CRITICAL", (
                "A single developer controls the majority of the codebase. "
                "This is a critical knowledge-concentration risk."
            )
        elif bus <= 2:
            risk, interp = "HIGH", (
                "Only two developers share critical knowledge. "
                "Cross-training is strongly recommended."
            )
        elif bus <= 3:
            risk, interp = "MEDIUM", (
                "Knowledge is somewhat concentrated. "
                "Broader code ownership would reduce risk."
            )
        else:
            risk, interp = "LOW", (
                "Knowledge is well distributed across the team. "
                "No single individual poses a catastrophic risk."
            )

        return {
            "bus_number": bus,
            "risk_level": risk,
            "top_author_owns_pct": top_pct,
            "interpretation": interp,
        }

    @staticmethod
    def _top_contributors(contrib: dict) -> list:
        ranked = sorted(contrib.items(),
                        key=lambda x: x[1]["commits"], reverse=True)
        return [
            {
                "author": a,
                "commits": s["commits"],
                "files_touched": len(s["files_touched"]),
                "lines_added": s["lines_added"],
                "lines_deleted": s["lines_deleted"],
            }
            for a, s in ranked[:10]
        ]

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — test coverage heuristic
    # ═══════════════════════════════════════════════════════════════════

    def _test_coverage(self, repo_path: str) -> dict:
        repo = Path(repo_path)
        src = tst = 0
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                fp = Path(root) / name
                if fp.suffix not in SOURCE_EXTS:
                    continue
                rel = str(fp.relative_to(repo)).replace("\\", "/").lower()
                if any(k in rel for k in TEST_KEYWORDS):
                    tst += 1
                else:
                    src += 1

        ratio = round(tst / max(src, 1) * 100, 1)
        label = (
            "EXCELLENT" if ratio >= 60 else
            "GOOD"      if ratio >= 40 else
            "FAIR"      if ratio >= 20 else
            "POOR"      if ratio >=  5 else
            "CRITICAL"
        )
        return {
            "source_files": src, "test_files": tst,
            "test_to_source_ratio_pct": ratio,
            "coverage_label": label,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — health score synthesis
    # ═══════════════════════════════════════════════════════════════════

    def _health_scores(self, security, dep_risk, test_cov, burnout,
                       cascade, debt, deploy, file_churn, contrib,
                       weekly, commits):

        # Quality (40 %)
        sec_s  = {"GOOD": 90, "FAIR": 60, "POOR": 30, "CRITICAL": 10
                  }.get(security.get("security_label", ""), 50)
        tst_s  = min(100, test_cov.get("test_to_source_ratio_pct", 0) * 1.5)
        debt_s = {"A+": 95, "A": 85, "B": 70, "C": 50, "D": 30, "F": 10
                  }.get(debt.get("debt_grade", "C"), 50)
        quality = int(sec_s * 0.35 + tst_s * 0.35 + debt_s * 0.30)

        # Stability (35 %)
        burn_inv = max(0, 100 - burnout.get("team_burnout_score", 0))
        casc_s   = {"LOW": 90, "MEDIUM": 65, "HIGH": 35, "CRITICAL": 10
                    }.get(cascade.get("team_cascade_risk", ""), 50)
        rev_pen  = min(30, len(burnout.get("revert_storms", [])) * 15)
        stability = int(burn_inv * 0.40 + casc_s * 0.40 + (100 - rev_pen) * 0.20)

        # Activity (25 %)
        recent  = sum(w.get("commits", 0) for w in weekly[-4:]) if weekly else 0
        act_raw = min(100, recent * 3)
        div     = min(100, len(contrib) * 15)
        activity = int(act_raw * 0.6 + div * 0.4)

        overall = max(0, min(100,
            int(quality * 0.40 + stability * 0.35 + activity * 0.25)))

        label = (
            "EXCELLENT" if overall >= 80 else
            "GOOD"      if overall >= 65 else
            "FAIR"      if overall >= 45 else
            "POOR"      if overall >= 25 else
            "CRITICAL"
        )

        preds = self._predict_components(file_churn, cascade)
        cost  = debt.get("cost_in_12_months_usd", 0) + len(commits) * 5

        return {
            "overall_health_score":       overall,
            "health_label":               label,
            "quality_score":              quality,
            "stability_score":            stability,
            "activity_score":             activity,
            "total_cost_of_inaction_usd": cost,
            "component_predictions":      preds,
            "immediate_action_required":  any(
                c.get("risk_level") == "CRITICAL" for c in preds[:5]),
            "weekly_commits":             weekly,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE — 90-day component failure prediction
    # ═══════════════════════════════════════════════════════════════════

    def _predict_components(self, file_churn, cascade):
        blast_map = {
            b["file"]: b
            for b in cascade.get("blast_radius_by_file", [])
        }
        preds = []

        for fp, churn in file_churn.items():
            blast = blast_map.get(fp, {})
            bpct  = blast.get("blast_radius_pct", 0)

            prob = min(95, int(churn * 1.5 + bpct * 0.8))
            if prob < 10:
                continue

            days = max(3, int(90 * (1 - prob / 100)))
            cost = int(prob * 50)
            risk = (
                "CRITICAL" if prob >= 60 else
                "HIGH"     if prob >= 40 else
                "MEDIUM"   if prob >= 20 else
                "LOW"
            )

            preds.append({
                "file": fp,
                "failure_probability_pct":   prob,
                "estimated_days_to_failure": days,
                "risk_level":                risk,
                "churn_count":               churn,
                "blast_radius_pct":          bpct,
                "estimated_cost_usd":        cost,
            })

        preds.sort(key=lambda x: x["failure_probability_pct"], reverse=True)
        return preds[:20]
