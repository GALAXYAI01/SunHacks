"""
burnout_detector.py — Agent that detects developer burnout from commit-time
patterns, revert storms, and per-developer intensity signals.
Part of the PredictiveEng multi-agent AI system.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any


def analyze_burnout(commits: List[Dict[str, Any]]) -> dict:
    """
    Analyse commit timestamps for burnout signals.

    Parameters
    ----------
    commits : list of dicts
        Each dict has: author, date (datetime), is_merge (bool),
        message (str), files_changed (int).

    Returns
    -------
    dict  with team_burnout_score, team_risk_level, per-developer breakdown,
          revert_storms, and narrative.
    """
    if not commits:
        return _empty()

    dev = defaultdict(lambda: {
        "total": 0, "after_hours": 0, "weekend": 0,
        "reverts": 0, "files_changed": 0, "hours": [],
        "dates": [],
    })

    total = 0
    total_ah = 0
    total_wk = 0
    revert_dates: List[datetime] = []

    for c in commits:
        if c.get("is_merge"):
            continue

        author = c.get("author", "Unknown")
        dt     = c.get("date")
        msg    = (c.get("message") or "").lower()

        total += 1
        s = dev[author]
        s["total"] += 1
        s["files_changed"] += c.get("files_changed", 0)

        if dt:
            h  = dt.hour
            wd = dt.weekday()           # 0 = Mon … 6 = Sun
            s["hours"].append(h)
            s["dates"].append(dt)

            if h < 7 or h >= 21:        # before 7 am / after 9 pm
                total_ah += 1
                s["after_hours"] += 1

            if wd >= 5:                  # Saturday / Sunday
                total_wk += 1
                s["weekend"] += 1

        if any(kw in msg for kw in ("revert", "rollback", "undo", "back out")):
            s["reverts"] += 1
            if dt:
                revert_dates.append(dt)

    after_hours_pct = round(total_ah / max(total, 1) * 100, 1)
    weekend_pct     = round(total_wk / max(total, 1) * 100, 1)

    # ── Revert-storm detection (3+ reverts in 48 h) ──────────
    revert_storms = _detect_revert_storms(revert_dates)

    # ── Per-developer scores ─────────────────────────────────
    developer_scores = []
    for author, s in dev.items():
        if s["total"] < 3:
            continue

        ah_pct  = s["after_hours"] / max(s["total"], 1) * 100
        wk_pct  = s["weekend"]     / max(s["total"], 1) * 100
        rev_pct = s["reverts"]     / max(s["total"], 1) * 100
        intensity = min(s["files_changed"] / max(s["total"], 1) / 10, 1) * 100

        score = min(100, int(
            ah_pct    * 0.40 +
            wk_pct    * 0.30 +
            rev_pct   * 1.00 +       # reverts are a strong signal
            intensity * 0.10
        ))

        risk = (
            "HIGH"    if score >= 60 else
            "MEDIUM"  if score >= 40 else
            "LOW"     if score >= 20 else
            "MINIMAL"
        )

        peak = max(set(s["hours"]), key=s["hours"].count) if s["hours"] else 12

        developer_scores.append({
            "author":          author,
            "burnout_score":   score,
            "after_hours_pct": round(ah_pct, 1),
            "weekend_pct":     round(wk_pct, 1),
            "commits":         s["total"],
            "peak_hour":       f"{peak}:00",
            "risk_level":      risk,
        })

    developer_scores.sort(key=lambda d: d["burnout_score"], reverse=True)

    # ── Team aggregate ───────────────────────────────────────
    if developer_scores:
        weights = [d["commits"] for d in developer_scores[:10]]
        tw = sum(weights) or 1
        team_score = int(
            sum(d["burnout_score"] * d["commits"]
                for d in developer_scores[:10]) / tw
        )
    else:
        team_score = 0

    team_risk = (
        "HIGH"    if team_score >= 60 else
        "MEDIUM"  if team_score >= 40 else
        "LOW"     if team_score >= 20 else
        "MINIMAL"
    )

    narrative = _narrative(team_score, after_hours_pct, weekend_pct,
                           revert_storms, developer_scores)

    return {
        "team_burnout_score":          team_score,
        "team_risk_level":             team_risk,
        "team_after_hours_commit_pct": after_hours_pct,
        "team_weekend_commit_pct":     weekend_pct,
        "revert_storms":               revert_storms,
        "narrative":                    narrative,
        "developer_scores":            developer_scores[:10],
    }


# ── helpers ──────────────────────────────────────────────────────────

def _detect_revert_storms(dates: List[datetime]) -> list:
    """Return clusters of ≥ 3 reverts within a 48-hour window."""
    if len(dates) < 3:
        return []
    storms = []
    sd = sorted(dates)
    i = 0
    while i < len(sd):
        end = sd[i] + timedelta(hours=48)
        cluster = [sd[i]]
        j = i + 1
        while j < len(sd) and sd[j] <= end:
            cluster.append(sd[j])
            j += 1
        if len(cluster) >= 3:
            storms.append({
                "date_range":   f"{cluster[0]:%Y-%m-%d} to {cluster[-1]:%Y-%m-%d}",
                "revert_count": len(cluster),
            })
            i = j
        else:
            i += 1
    return storms


def _narrative(score, ah, wk, storms, devs):
    p = []
    if score >= 60:
        p.append("The team is showing significant signs of burnout.")
    elif score >= 40:
        p.append("The team is under moderate stress with some concerning patterns.")
    else:
        p.append("The team appears to be working at a sustainable pace.")

    if ah > 30:
        p.append(f"{ah}% of commits happen outside normal business hours, suggesting overwork or timezone spread.")
    if wk > 20:
        p.append(f"Weekend work ({wk}%) indicates deadline pressure or understaffing.")
    if storms:
        p.append(f"Detected {len(storms)} revert storm(s) — rapid code rollbacks signal rushed, error-prone development.")
    if devs and devs[0]["burnout_score"] >= 70:
        p.append(f"Highest-risk individual: {devs[0]['author']} (score {devs[0]['burnout_score']}/100).")

    return " ".join(p) or "No significant burnout signals detected."


def _empty():
    return {
        "team_burnout_score": 0, "team_risk_level": "MINIMAL",
        "team_after_hours_commit_pct": 0, "team_weekend_commit_pct": 0,
        "revert_storms": [], "narrative": "No commit data available for burnout analysis.",
        "developer_scores": [],
    }
