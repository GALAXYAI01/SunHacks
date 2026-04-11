"""
analyzer.py — Core analysis engine for PredictiveEng.

No GitHub token required. Works entirely with:
  - GitHub public REST API  (unauthenticated, 60 req/hr)
  - GitPython clone         (public HTTPS, no auth)
  - PyDriller               (local commit traversal)
  - Radon                   (local complexity analysis)

Privacy: zero credentials ever touch the server.
"""

import os
import re
import json
import shutil
import tempfile
import requests
import concurrent.futures
from datetime import datetime
from collections import defaultdict

from git import Repo
from pydriller import Repository
from radon.complexity import cc_visit, cc_rank
from radon.metrics import mi_visit
from radon.raw import analyze as radon_raw


class GitHubAnalyzer:

    def parse_repo_url(self, url: str):
        """Extract owner/repo from any github.com URL."""
        url = url.rstrip("/").replace(".git", "")
        # Handle https://github.com/owner/repo and github.com/owner/repo
        if "github.com" not in url:
            raise ValueError("Only GitHub repositories are supported.")
        parts = url.split("github.com/")[-1].split("/")
        if len(parts) < 2:
            raise ValueError("URL must be in the form https://github.com/owner/repo")
        return parts[0], parts[1]

    def get_repo_info(self, owner: str, repo: str) -> dict:
        """Fetch public repo metadata — uses GITHUB_TOKEN if available."""
        url  = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.get(url, timeout=10, headers=headers)
        except Exception:
            # Network error — return minimal info, cloning can still try
            return {"name": repo, "full_name": f"{owner}/{repo}",
                    "language": "Unknown", "private": False}
        if resp.status_code == 200:
            d = resp.json()
            return {
                "name":           d.get("name"),
                "full_name":      d.get("full_name"),
                "description":    d.get("description", ""),
                "language":       d.get("language", "Unknown"),
                "stars":          d.get("stargazers_count", 0),
                "forks":          d.get("forks_count", 0),
                "open_issues":    d.get("open_issues_count", 0),
                "default_branch": d.get("default_branch", "main"),
                "created_at":     d.get("created_at", ""),
                "updated_at":     d.get("updated_at", ""),
                "size_kb":        d.get("size", 0),
                "private":        d.get("private", False),
            }
        if resp.status_code == 404:
            raise ValueError(f"Repository {owner}/{repo} not found or is private. "
                             "Only public repositories are supported.")
        if resp.status_code == 403:
            # Rate limited — return minimal info, cloning can still work
            print(f"[INFO] GitHub API rate-limited. Proceeding with clone-only mode.")
            return {"name": repo, "full_name": f"{owner}/{repo}",
                    "language": "Unknown", "private": False}
        return {"name": repo, "full_name": f"{owner}/{repo}", "language": "Unknown",
                "private": False}

    def clone_repo(self, owner: str, repo: str) -> str:
        """Clone public repo to temp dir. Uses token for auth if available."""
        tmp = tempfile.mkdtemp(prefix="pred_eng_")
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            clone_url = f"https://{token}@github.com/{owner}/{repo}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo}.git"
        try:
            Repo.clone_from(clone_url, tmp, depth=30)
        except Exception as e:
            # Clean up temp dir on failure
            shutil.rmtree(tmp, ignore_errors=True)
            raise ValueError(
                f"Failed to clone repository. Make sure '{owner}/{repo}' exists "
                f"and is a public repository. Error: {e}"
            )
        return tmp

    # ── Commit analysis ───────────────────────────────────────────────

    def analyze_commits(self, repo_path: str) -> dict:
        commit_count   = 0
        file_changes   = defaultdict(int)
        file_bug_fixes = defaultdict(int)
        author_counts  = defaultdict(int)
        author_files   = defaultdict(set)
        weekly         = defaultdict(int)
        bug_kw = {"fix","bug","error","crash","fail","broken","patch","hotfix","revert"}

        try:
            for commit in Repository(repo_path).traverse_commits():
                commit_count += 1
                week = commit.author_date.strftime("%Y-%W")
                weekly[week] += 1
                author_counts[commit.author.name] += 1
                is_bug = any(k in commit.msg.lower() for k in bug_kw)
                for mod in commit.modified_files:
                    if mod.filename:
                        file_changes[mod.filename]     += 1
                        author_files[commit.author.name].add(mod.filename)
                        if is_bug:
                            file_bug_fixes[mod.filename] += 1
        except Exception as e:
            print(f"[Commit Warning] {e}")

        hotspots = sorted([
            {"file": f,
             "total_changes":      file_changes[f],
             "bug_related_changes":file_bug_fixes.get(f, 0),
             "churn_score":        file_bug_fixes.get(f, 0)*3 + file_changes[f]}
            for f in set(file_changes) | set(file_bug_fixes)
        ], key=lambda x: x["churn_score"], reverse=True)

        sorted_weeks = sorted(weekly.keys())[-12:]
        commit_trend = [{"week": w, "commits": weekly[w]} for w in sorted_weeks]

        return {
            "total_commits":       commit_count,
            "total_files_changed": len(file_changes),
            "top_hotspots":        hotspots[:10],
            "commit_trend":        commit_trend,
            "top_contributors":    sorted(
                [{"author": k, "commits": v} for k, v in author_counts.items()],
                key=lambda x: x["commits"], reverse=True)[:5],
            "bug_fix_ratio":       round(
                sum(file_bug_fixes.values()) / max(commit_count, 1), 3),
            "bus_factor":          self._bus_factor(author_files),
            # expose raw churn map for cascade + debt modules
            "_file_churn":         dict(file_changes),
        }

    def _bus_factor(self, author_files: dict) -> dict:
        total = len(set().union(*author_files.values())) if author_files else 1
        by_size = sorted(author_files.items(), key=lambda x: len(x[1]), reverse=True)
        seen, n = set(), 0
        for author, files in by_size:
            seen |= files
            n    += 1
            if len(seen) / max(total, 1) >= 0.5:
                break
        top = by_size[0] if by_size else ("Unknown", set())
        risk = "CRITICAL" if n == 1 else "HIGH" if n <= 2 else "MEDIUM" if n <= 3 else "LOW"
        return {
            "bus_number":         n,
            "risk_level":         risk,
            "top_author":         top[0],
            "top_author_owns_pct":round(len(top[1]) / max(total, 1)*100, 1),
            "interpretation":     f"{n} developer(s) own 50%+ of the codebase.",
        }

    # ── Code quality — function-level detail ──────────────────────────

    def analyze_code_quality(self, repo_path: str) -> dict:
        """
        Returns per-file complexity with EXACT function names and line numbers.
        This data feeds both the component table and the cascade card.
        """
        results, total_loc, total_cc, count = [], 0, 0, 0
        low_mi = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and
                       d not in ("node_modules","venv",".git","__pycache__")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                rel   = os.path.relpath(fpath, repo_path)
                try:
                    code = open(fpath, encoding="utf-8", errors="ignore").read()
                    if not code.strip():
                        continue

                    blocks = cc_visit(code)
                    avg_cc = (sum(b.complexity for b in blocks) /
                              len(blocks)) if blocks else 0
                    max_cc = max((b.complexity for b in blocks), default=0)
                    mi     = mi_visit(code, multi=True)
                    loc    = radon_raw(code).lloc

                    total_loc += loc
                    total_cc  += avg_cc
                    count     += 1

                    # ── Per-function hotspots with exact location ──
                    fn_hotspots = []
                    for b in sorted(blocks, key=lambda x: x.complexity, reverse=True)[:8]:
                        rank = cc_rank(b.complexity)
                        fn_hotspots.append({
                            "function_name": b.name,
                            "line_start":    b.lineno,
                            "line_end":      getattr(b, "endline", b.lineno),
                            "complexity":    b.complexity,
                            "rank":          rank,
                            "type":          b.letter,
                            "is_problematic":b.complexity > 5,
                            "fix_suggestion":_fix_hint(b.name, b.complexity, rank),
                        })

                    risk = ("CRITICAL" if avg_cc > 10 or mi < 20 else
                            "HIGH"     if avg_cc >  5 or mi < 50 else
                            "MEDIUM"   if avg_cc >  3 or mi < 65 else "LOW")

                    problematic = [f for f in fn_hotspots if f["is_problematic"]]
                    worst       = fn_hotspots[0] if fn_hotspots else None

                    entry = {
                        "file":                  rel,
                        "loc":                   loc,
                        "avg_complexity":        round(avg_cc, 2),
                        "max_complexity":        max_cc,
                        "maintainability_index": round(mi, 2),
                        "risk_level":            risk,
                        "function_hotspots":     fn_hotspots,
                        "most_complex_function": worst,
                        "problematic_functions": problematic,
                        "error_summary":         _error_summary(rel, worst, problematic),
                    }
                    results.append(entry)
                    if mi < 50:
                        low_mi.append(entry)
                except Exception:
                    continue

        results.sort(key=lambda x: x["avg_complexity"], reverse=True)
        return {
            "total_python_files":       count,
            "total_loc":                total_loc,
            "avg_cyclomatic_complexity":round(total_cc / max(count, 1), 2),
            "files_by_risk":            results[:15],
            "low_maintainability_files":sorted(low_mi,
                key=lambda x: x["maintainability_index"])[:5],
        }

    # ── Test coverage heuristic ───────────────────────────────────────

    def analyze_test_coverage(self, repo_path: str) -> dict:
        src, tst = [], []
        test_re = re.compile(r"(test_|_test\.|spec\.|\.spec\.|__tests__)", re.I)
        exts    = {".py",".js",".ts",".go",".rb",".java",".cs"}
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs
                       if d not in (".git","node_modules","venv","__pycache__")]
            for f in files:
                if not any(f.endswith(e) for e in exts):
                    continue
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                (tst if test_re.search(rel) else src).append(rel)
        ratio = round(len(tst) / max(len(src), 1)*100, 1)
        return {
            "source_files":            len(src),
            "test_files":              len(tst),
            "test_to_source_ratio_pct":ratio,
            "coverage_label":          ("EXCELLENT" if ratio >= 70 else
                                        "GOOD"      if ratio >= 40 else
                                        "FAIR"      if ratio >= 20 else "POOR"),
        }

    # ── Health scoring ────────────────────────────────────────────────

    def calculate_health_scores(self, commit_data, quality_data, repo_info) -> dict:
        avg_cc    = quality_data.get("avg_cyclomatic_complexity", 0)
        all_files = quality_data.get("files_by_risk", [])
        risky     = [f for f in all_files if f["risk_level"] in ("HIGH","CRITICAL")]
        cc_score  = max(0, 100 - avg_cc*10)
        q_score   = round(cc_score * (1 - len(risky)/max(len(all_files),1)*0.5))

        bug_ratio  = commit_data.get("bug_fix_ratio", 0)
        churn_sc   = max(0, round(100 - bug_ratio*200))

        trend = commit_data.get("commit_trend", [])
        act_sc = min(100, round(
            sum(w["commits"] for w in trend[-4:]) / max(len(trend[-4:]),1) * 5
        )) if trend else 50

        overall = round(q_score*0.45 + churn_sc*0.35 + act_sc*0.20)
        q_map   = {f["file"]: f for f in all_files}
        comps   = []

        for hs in commit_data.get("top_hotspots", [])[:8]:
            fname = hs["file"]
            qd    = q_map.get(fname, {})
            cc    = qd.get("avg_complexity", 3)
            mi    = qd.get("maintainability_index", 70)
            churn = hs["churn_score"]
            bugs  = hs["bug_related_changes"]
            prob  = min(98, round(
                (cc/20*35) + ((100-mi)/100*25) +
                (min(churn,50)/50*25) + (min(bugs,10)/10*15)
            ))
            now   = max(500, churn*120)
            worst = qd.get("most_complex_function")
            comps.append({
                "component":              fname,
                "health_score":           max(0, 100-prob),
                "failure_probability_pct":prob,
                "predicted_failure_days": max(7, round(90*(1-prob/100))),
                "risk_level":             qd.get("risk_level","MEDIUM"),
                "bug_related_changes":    bugs,
                "fix_cost_now_usd":       now,
                "fix_cost_later_usd":     now*4,
                "cost_of_inaction_usd":   now*3,
                # ── exact error location fields ──
                "most_complex_function":  worst,
                "problematic_functions":  qd.get("problematic_functions", [])[:3],
                "error_summary":          qd.get("error_summary",""),
            })

        comps.sort(key=lambda x: x["failure_probability_pct"], reverse=True)
        total_cost = sum(c["cost_of_inaction_usd"] for c in comps)

        return {
            "overall_health_score":      overall,
            "quality_score":             q_score,
            "stability_score":           churn_sc,
            "activity_score":            act_sc,
            "health_label":             ("CRITICAL" if overall < 40 else
                                         "POOR"     if overall < 60 else
                                         "FAIR"     if overall < 75 else
                                         "GOOD"     if overall < 90 else "EXCELLENT"),
            "component_predictions":     comps,
            "total_cost_of_inaction_usd":total_cost,
            "immediate_action_required": [c for c in comps
                                          if c["failure_probability_pct"] >= 70],
        }

    # ── Full pipeline ─────────────────────────────────────────────────

    def run_full_analysis(self, repo_url: str) -> dict:
        from security_scanner    import scan_security, analyze_dependencies
        from burnout_detector    import analyze_burnout
        from cascade_analyzer    import analyze_cascade
        from debt_calculator     import calculate_debt
        from deployment_readiness import check_deployment_readiness

        owner, repo_name = self.parse_repo_url(repo_url)
        repo_info = self.get_repo_info(owner, repo_name)

        if repo_info.get("private"):
            raise ValueError("This repository is private. "
                             "PredictiveEng only analyzes public repositories.")

        tmp = None
        try:
            tmp = self.clone_repo(owner, repo_name)

            # ── Stage 1: commit + quality analysis run in parallel ─────
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f_commit  = pool.submit(self.analyze_commits, tmp)
                f_quality = pool.submit(self.analyze_code_quality, tmp)

                commit_data  = f_commit.result()
                quality_data = f_quality.result()

            health_data = self.calculate_health_scores(
                              commit_data, quality_data, repo_info)
            file_churn  = commit_data.get("_file_churn", {})

            # ── Stage 2: independent modules run in parallel ───────────
            # Security, test coverage, cascade, and burnout do not
            # depend on each other — run all 4 at the same time.
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                f_sec     = pool.submit(scan_security, tmp)
                f_test    = pool.submit(self.analyze_test_coverage, tmp)
                f_cascade = pool.submit(analyze_cascade, tmp, file_churn)
                f_burnout = pool.submit(
                    lambda: analyze_burnout(_extract_raw_commits(tmp)))

                security     = f_sec.result()
                test_cov     = f_test.result()
                cascade_data = f_cascade.result()
                burnout      = f_burnout.result()

            # Enrich cascade with function-level detail from quality analysis
            cascade = _enrich_cascade(cascade_data, quality_data)

            # ── Stage 3: modules that depend on stage-2 results ────────
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                f_dep    = pool.submit(analyze_dependencies, tmp)
                f_deploy = pool.submit(
                    check_deployment_readiness, tmp,
                    test_cov.get("test_files", 0) > 0,
                    security.get("security_label", "UNKNOWN"))
                f_debt   = pool.submit(
                    calculate_debt, tmp, file_churn,
                    test_cov.get("test_to_source_ratio_pct", 0))

                dep_risk = f_dep.result()
                deploy   = f_deploy.result()
                debt     = f_debt.result()

            return {
                "repo_info":            repo_info,
                "commit_analysis":      {k: v for k, v in commit_data.items()
                                         if k != "_file_churn"},
                "code_quality":         quality_data,
                "health_scores":        health_data,
                "security":             security,
                "dependency_risk":      dep_risk,
                "test_coverage":        test_cov,
                "burnout":              burnout,
                "cascade_risk":         cascade,
                "technical_debt":       debt,
                "deployment_readiness": deploy,
                "analyzed_at":          datetime.utcnow().isoformat() + "Z",
            }
        finally:
            if tmp and os.path.exists(tmp):
                shutil.rmtree(tmp, ignore_errors=True)


# ── Module-level helpers ──────────────────────────────────────────────

def _extract_raw_commits(repo_path: str) -> list:
    """Convert PyDriller commits to the flat list burnout_detector expects."""
    commits = []
    try:
        for c in Repository(repo_path).traverse_commits():
            commits.append({
                "author":        c.author.name,
                "date":          c.author_date,
                "message":       c.msg,
                "is_merge":      c.merge,
                "files_changed": len(c.modified_files),
            })
    except Exception:
        pass
    return commits


def _enrich_cascade(cascade: dict, quality: dict) -> dict:
    """
    Attach function-level error detail to each cascade file entry
    so the UI can show EXACTLY where the problem is.
    """
    q_map = {f["file"]: f for f in quality.get("files_by_risk", [])}
    for entry in cascade.get("blast_radius_by_file", []):
        fname = entry.get("file", "")
        qd    = q_map.get(fname, {})
        worst = qd.get("most_complex_function")
        prob  = qd.get("problematic_functions", [])
        entry["most_complex_function"] = worst
        entry["problematic_functions"] = prob[:3]
        entry["error_summary"]         = qd.get("error_summary", "")
        # human-readable location string for the UI chip
        if worst:
            entry["error_location"] = (
                f"{worst['function_name']}() "
                f"line {worst['line_start']} "
                f"(complexity {worst['complexity']})"
            )
        else:
            entry["error_location"] = ""
    return cascade


def _fix_hint(name: str, cc: int, rank: str) -> str:
    if rank in ("A","B"):
        return f"'{name}' is fine (CC={cc})."
    if rank == "C":
        return f"Consider splitting '{name}' — CC={cc} is borderline."
    if rank == "D":
        return f"Refactor '{name}' (CC={cc}): too many branches, high bug risk."
    return (f"URGENT: '{name}' CC={cc} is nearly untestable. "
            f"Break into 3–4 focused helper functions.")


def _error_summary(fname: str, worst: dict, problematic: list) -> str:
    if not worst:
        return ""
    return (f"Worst: {worst['function_name']}() at line {worst['line_start']} "
            f"(complexity {worst['complexity']}). "
            f"{len(problematic)} function(s) exceed safe threshold.")