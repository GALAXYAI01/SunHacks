"""
security_scanner.py — Agent that scans for hardcoded secrets, code vulnerabilities,
and dependency risks. Part of the PredictiveEng multi-agent AI system.
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict

# ── Patterns for detecting hardcoded secrets ──────────────────────────
SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}', "API Key"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}', "Secret Key"),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}', "Hardcoded Password"),
    (r'(?i)(access[_-]?token|auth[_-]?token)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}', "Access Token"),
    (r'(?i)(aws[_-]?access[_-]?key[_-]?id)\s*[=:]\s*["\']?AKIA[A-Z0-9]{16}', "AWS Access Key"),
    (r'(?i)(private[_-]?key)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}', "Private Key"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub Personal Access Token"),
    (r'gho_[A-Za-z0-9]{36}', "GitHub OAuth Token"),
    (r'sk-[A-Za-z0-9]{32,}', "OpenAI / Stripe Secret Key"),
    (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----', "Private Key File"),
    (r'(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*', "Bearer Token"),
]

# ── Patterns for code-level vulnerabilities ────────────────────────────
VULN_PATTERNS = [
    (r'eval\s*\(', "eval() usage", "Code Injection Risk", "HIGH"),
    (r'exec\s*\(', "exec() usage", "Code Execution Risk", "HIGH"),
    (r'subprocess\.call\s*\(.*shell\s*=\s*True', "subprocess with shell=True", "Command Injection", "CRITICAL"),
    (r'pickle\.loads?\s*\(', "Unsafe pickle deserialization", "Deserialization Attack", "HIGH"),
    (r'yaml\.load\s*\([^)]*\)(?!.*Loader)', "Unsafe YAML load (no Loader)", "YAML Code Execution", "MEDIUM"),
    (r'innerHTML\s*=', "innerHTML assignment", "XSS Vulnerability", "MEDIUM"),
    (r'dangerouslySetInnerHTML', "React dangerouslySetInnerHTML", "XSS Vulnerability", "MEDIUM"),
    (r'(?i)os\.system\s*\(', "os.system() call", "Command Injection", "HIGH"),
    (r'(?i)__import__\s*\(', "Dynamic import", "Code Injection", "MEDIUM"),
    (r'(?i)marshal\.loads?\s*\(', "Unsafe marshal usage", "Deserialization Attack", "HIGH"),
]

SKIP_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__',
             '.tox', 'dist', 'build', '.eggs', 'vendor', '.mypy_cache'}
SCAN_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.rb', '.go', '.java',
                   '.php', '.yml', '.yaml', '.toml', '.cfg', '.ini', '.conf',
                   '.env', '.sh', '.bash', '.rs', '.cs', '.kt'}


def scan_security(repo_path: str) -> dict:
    """
    Walk the repository tree and scan every file for secrets and
    known vulnerability patterns.  Returns a structured report.
    """
    findings: List[Dict] = []
    secret_count = 0
    vuln_count   = 0

    repo = Path(repo_path)

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for name in files:
            fpath = Path(root) / name
            rel_path = str(fpath.relative_to(repo)).replace("\\", "/")

            # ── Committed .env files ──────────────────────────
            if name in ('.env', '.env.local', '.env.production', '.env.staging'):
                findings.append({
                    "type": "SECRET", "severity": "HIGH",
                    "label": f"Environment file committed: {name}",
                    "description": f"Sensitive file '{name}' is checked into version control",
                    "file": rel_path, "line": 0,
                })
                secret_count += 1
                continue

            if fpath.suffix not in SCAN_EXTENSIONS:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")
            except Exception:
                continue

            # Skip obvious non-source files in tests/examples/samples
            is_test = any(t in rel_path.lower() for t in
                          ("test", "spec", "example", "sample", "fixture", "mock"))

            # ── Secret scanning ───────────────────────────────
            for pattern, label in SECRET_PATTERNS:
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "*", "/*")):
                        continue          # skip comments
                    if is_test:
                        continue           # skip test fixtures
                    if re.search(pattern, line):
                        findings.append({
                            "type": "SECRET", "severity": "CRITICAL",
                            "label": label,
                            "description": f"Potential {label} detected in source code",
                            "file": rel_path, "line": i,
                        })
                        secret_count += 1
                        break              # one per pattern per file

            # ── Vulnerability scanning ────────────────────────
            for pattern, label, desc, sev in VULN_PATTERNS:
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "*")):
                        continue
                    if re.search(pattern, line):
                        findings.append({
                            "type": "VULN", "severity": sev,
                            "label": label,
                            "description": desc,
                            "file": rel_path, "line": i,
                        })
                        vuln_count += 1
                        break

    # ── Severity sort ─────────────────────────────────────────
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: sev_order.get(f["severity"], 99))

    # ── Overall label ─────────────────────────────────────────
    crit_count = sum(1 for f in findings if f["severity"] == "CRITICAL")
    if crit_count > 0:
        security_label = "CRITICAL"
    elif secret_count > 0 or vuln_count > 3:
        security_label = "POOR"
    elif vuln_count > 0 or findings:
        security_label = "FAIR"
    else:
        security_label = "GOOD"

    return {
        "security_label": security_label,
        "secret_count":   secret_count,
        "vuln_count":     vuln_count,
        "total_findings": len(findings),
        "findings":       findings[:25],   # cap UI payload
    }


# ── Dependency risk analysis ──────────────────────────────────────────

def analyze_dependencies(repo_path: str) -> dict:
    """Parse dependency manifest files and estimate outdated / risky deps."""
    repo = Path(repo_path)
    total_deps      = 0
    dep_files_found  = []

    parsers = {
        "requirements.txt": _parse_requirements,
        "setup.py":         _count_approx,
        "pyproject.toml":   _count_approx,
        "Pipfile":          _count_approx,
        "package.json":     _parse_package_json,
        "yarn.lock":        _count_lock,
        "package-lock.json":_count_lock,
        "Gemfile":          _count_approx,
        "go.mod":           _count_approx,
        "Cargo.toml":       _count_approx,
        "pom.xml":          _count_approx,
        "build.gradle":     _count_approx,
        "composer.json":    _parse_package_json,
    }

    for fname, parser in parsers.items():
        fpath = repo / fname
        if fpath.exists():
            dep_files_found.append(fname)
            total_deps += parser(fpath)

    # Heuristic: ~20 % of deps are typically outdated in an average project
    outdated_estimate = max(1, int(total_deps * 0.20)) if total_deps else 0
    ratio = outdated_estimate / max(total_deps, 1)

    if ratio > 0.40 or total_deps > 120:
        risk = "HIGH"
    elif ratio > 0.20 or total_deps > 60:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "total_dependencies": total_deps,
        "outdated_count":     outdated_estimate,
        "risk_level":         risk,
        "dependency_files":   dep_files_found,
    }


# ── Helpers ───────────────────────────────────────────────────────────

def _parse_requirements(fpath: Path) -> int:
    try:
        lines = fpath.read_text(errors="ignore").strip().splitlines()
        return sum(1 for l in lines
                   if l.strip() and not l.strip().startswith(("#", "-")))
    except Exception:
        return 0

def _parse_package_json(fpath: Path) -> int:
    try:
        data = json.loads(fpath.read_text(errors="ignore"))
        return len(data.get("dependencies", {})) + len(data.get("devDependencies", {}))
    except Exception:
        return 0

def _count_approx(fpath: Path) -> int:
    try:
        lines = fpath.read_text(errors="ignore").strip().splitlines()
        return max(1, len(lines) // 5)
    except Exception:
        return 0

def _count_lock(fpath: Path) -> int:
    """Lock files list every dep; count unique package names."""
    try:
        text = fpath.read_text(errors="ignore")
        return text.count('"name":') or text.count("  ") // 4
    except Exception:
        return 0
