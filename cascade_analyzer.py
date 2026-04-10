"""
cascade_analyzer.py — Agent that builds file-level dependency / import graphs
and computes blast-radius for every source file.
Part of the PredictiveEng multi-agent AI system.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set

SKIP_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__',
             '.tox', 'dist', 'build', '.eggs', 'vendor', '.next', '.nuxt'}
SOURCE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rb',
               '.java', '.rs', '.php', '.vue', '.svelte'}

# ── Import regex per language family ──────────────────────────────────
_PY  = [re.compile(r'^(?:from\s+(\S+)\s+)?import\s+(\S+)', re.M)]
_JS  = [re.compile(
    r'(?:import\s+.*?from\s+["\']([^"\']+)["\']'
    r'|require\s*\(\s*["\']([^"\']+)["\']\s*\))', re.M)]
_GO  = [re.compile(r'"([^"]+)"', re.M)]
_RB  = [re.compile(r'require\s+["\']([^"\']+)["\']', re.M)]
_JV  = [re.compile(r'import\s+([\w.]+)', re.M)]
_RS  = [re.compile(r'(?:use|mod)\s+([\w:]+)', re.M)]

IMPORT_PATTERNS = {
    '.py': _PY, '.js': _JS, '.ts': _JS, '.jsx': _JS, '.tsx': _JS,
    '.go': _GO, '.rb': _RB, '.java': _JV, '.rs': _RS,
    '.vue': _JS, '.svelte': _JS, '.php': _JS,
}


def analyze_cascade(repo_path: str,
                    file_churn: Dict[str, int] | None = None) -> dict:
    """
    Build an import graph, compute blast radii, and find critical hub files.

    Parameters
    ----------
    repo_path  : path to the cloned repository root.
    file_churn : optional {filepath: churn_count} from commit mining.
    """
    repo = Path(repo_path)
    file_churn = file_churn or {}

    # 1. Discover source files ────────────────────────────────
    source_files = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            fp = Path(root) / name
            if fp.suffix in SOURCE_EXTS:
                rel = str(fp.relative_to(repo)).replace("\\", "/")
                source_files.append((rel, fp))

    total_files = len(source_files) or 1

    # 2. Build dependency graph ───────────────────────────────
    # importers[file] = set of files that *import* that file
    importers: Dict[str, Set[str]] = defaultdict(set)
    file_imports: Dict[str, set]   = {}

    # Build a lookup:  basename | no-ext path | dotted form → rel path
    file_lookup: Dict[str, str] = {}
    for rel, _ in source_files:
        file_lookup[rel] = rel
        file_lookup[Path(rel).stem] = rel
        no_ext = str(Path(rel).with_suffix("")).replace("\\", "/")
        file_lookup[no_ext] = rel
        file_lookup[no_ext.replace("/", ".")] = rel

    for rel, abspath in source_files:
        patterns = IMPORT_PATTERNS.get(abspath.suffix, [])
        if not patterns:
            continue
        try:
            content = abspath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        imports: set = set()
        for pat in patterns:
            for m in pat.finditer(content):
                for g in m.groups():
                    if g:
                        imports.add(_normalise(g))

        file_imports[rel] = imports

    # Resolve → actual files
    for importer, imps in file_imports.items():
        for imp in imps:
            resolved = _resolve(imp, file_lookup)
            if resolved and resolved != importer:
                importers[resolved].add(importer)

    # 3. Blast-radius BFS ─────────────────────────────────────
    blast_data = []
    for rel, _ in source_files:
        direct = importers.get(rel, set())

        visited: set = set()
        queue = list(direct)
        while queue:
            dep = queue.pop(0)
            if dep in visited:
                continue
            visited.add(dep)
            queue.extend(importers.get(dep, set()) - visited)

        blast_pct = round(len(visited) / total_files * 100, 1)
        churn = file_churn.get(rel, 0)

        failure_prob = min(95, int(churn * 1.5 + blast_pct * 0.5))

        severity = (
            "CATASTROPHIC" if blast_pct >= 30 or failure_prob >= 70 else
            "SEVERE"       if blast_pct >= 15 or failure_prob >= 50 else
            "HIGH"         if blast_pct >=  5 or failure_prob >= 30 else
            "MODERATE"     if blast_pct >=  1 else
            "LOW"
        )

        if blast_pct > 0 or churn > 3:
            blast_data.append({
                "file":                    rel,
                "failure_probability_pct": failure_prob,
                "blast_radius_pct":        blast_pct,
                "severity":                severity,
                "direct_dependents":       sorted(direct)[:10],
                "business_impact":
                    f"Failure affects {len(visited)} file(s) "
                    f"({blast_pct}% of codebase)",
            })

    blast_data.sort(key=lambda x: x["blast_radius_pct"], reverse=True)

    # 4. Critical hub files ───────────────────────────────────
    hub_files = sorted(
        ((f, len(deps)) for f, deps in importers.items() if len(deps) >= 2),
        key=lambda x: x[1], reverse=True,
    )[:10]
    critical_hubs = [{"file": f, "imported_by": n} for f, n in hub_files]

    # 5. Team-level risk ──────────────────────────────────────
    max_blast = blast_data[0]["blast_radius_pct"] if blast_data else 0
    risk = (
        "CRITICAL" if max_blast >= 30 else
        "HIGH"     if max_blast >= 15 else
        "MEDIUM"   if max_blast >=  5 else
        "LOW"
    )

    top = blast_data[0] if blast_data else None
    summary = (
        f"Highest-risk file is {top['file']} with {top['blast_radius_pct']}% "
        f"blast radius."
        if top else "No significant cascade risks detected."
    )

    return {
        "team_cascade_risk":   risk,
        "summary":             summary,
        "blast_radius_by_file": blast_data[:15],
        "critical_hub_files":  critical_hubs,
    }


# ── helpers ──────────────────────────────────────────────────────────

def _normalise(imp: str) -> str:
    imp = imp.lstrip(".")
    imp = imp.replace(".", "/")
    imp = re.sub(r"^\.+/", "", imp)
    return imp

def _resolve(imp: str, lookup: dict):
    if imp in lookup:
        return lookup[imp]
    for variant in (imp.split("/")[-1], imp.replace("/", ".")):
        if variant in lookup:
            return lookup[variant]
    return None
