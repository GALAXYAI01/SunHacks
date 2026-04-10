"""
ai_reporter.py  —  CEO-grade AI brief via LangChain + Claude.
"""

import os
import json
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import ResponseSchema, StructuredOutputParser   # FIXED: was langchain_classic

_llm: Any = None


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY not set. Add it to your .env file.")
        _llm = ChatGroq(
            model="llama-3.1-70b-versatile",
            groq_api_key=api_key,
            max_tokens=1024,
            temperature=0.2,
        )
    return _llm


_response_schemas = [
    ResponseSchema(name="executive_summary",
                   description="2-3 sentence plain-English summary for a non-technical CEO"),
    ResponseSchema(name="business_risk_level",
                   description="One of: CRITICAL, HIGH, MEDIUM, LOW"),
    ResponseSchema(name="predicted_incident_probability_30d_pct",
                   description="Integer 0-100: chance of a production incident in 30 days"),
    ResponseSchema(name="critical_finding",
                   description="The single most important finding in one sentence"),
    ResponseSchema(name="health_analogy",
                   description="One vivid analogy comparing codebase health to something non-technical"),
    ResponseSchema(name="top_actions",
                   description='JSON array of 3 objects: [{"action":"...","timeline":"...","estimated_savings_usd":0}]'),
    ResponseSchema(name="cost_summary",
                   description='JSON object: {"fix_now_usd":0,"cost_if_delayed_usd":0}'),
]

_output_parser = StructuredOutputParser.from_response_schemas(_response_schemas)
_format_instructions = _output_parser.get_format_instructions()

_PROMPT = ChatPromptTemplate.from_template(
    """You are a senior engineering consultant writing a concise executive brief for a non-technical CEO.

Repository     : {full_name}
Language       : {language}
Stars / Issues : {stars} / {open_issues}

HEALTH METRICS
  Overall Score  : {overall_health_score}/100  ({health_label})
  Quality Score  : {quality_score}
  Stability Score: {stability_score}
  Activity Score : {activity_score}
  Cost of Inaction: ${total_cost_usd}

BUS FACTOR
  Bus Number : {bus_number}  ({bus_risk})
  Top author owns {top_author_pct}% of files — {bus_interpretation}

SECURITY
  Label: {security_label} | Secrets: {secret_count} | Vulns: {vuln_count}

TEST COVERAGE
  Source / Test files: {source_files} / {test_files}  ({test_ratio}%  {coverage_label})

DEPENDENCY RISK
  Total: {total_deps} | Outdated: {outdated_count} | Risk: {dep_risk}

DEVELOPER BURNOUT
  Team Burnout Score : {team_burnout_score}/100  ({team_burnout_risk})
  After-hours commits: {after_hours_pct}% of all commits
  Revert storms      : {revert_storm_count}
  Narrative          : {burnout_narrative}

CASCADE FAILURE BLAST RADIUS
  Team Cascade Risk  : {team_cascade_risk}
  Highest risk file  : {top_cascade_file}  blast radius {top_blast_pct}% of codebase
  Summary            : {cascade_summary}

TECHNICAL DEBT
  Debt Grade         : {debt_grade}
  Current Debt       : {debt_hours} hours  (${debt_usd_now:,})
  In 12 months       : ${debt_usd_12m:,}  ({debt_growth_multiple}x today)

DEPLOYMENT READINESS
  Score  : {deploy_score}/100  ({deploy_label})
  Missing: {deploy_missing}

TOP RISKY COMPONENTS
{components_json}

{format_instructions}
"""
)


def generate_ceo_report(raw_data: dict) -> dict:
    try:
        repo   = raw_data.get("repo_info", {})
        hs     = raw_data.get("health_scores", {})
        bus    = raw_data.get("commit_analysis", {}).get("bus_factor", {})
        sec    = raw_data.get("security", {})
        test   = raw_data.get("test_coverage", {})
        dep    = raw_data.get("dependency_risk", {})
        burn   = raw_data.get("burnout", {})
        casc   = raw_data.get("cascade_risk", {})
        debt   = raw_data.get("technical_debt", {})
        deploy = raw_data.get("deployment_readiness", {})
        comps  = hs.get("component_predictions", [])[:5]

        blast_list  = casc.get("blast_radius_by_file", [])
        top_cascade = blast_list[0] if blast_list else {}
        missing     = [c["check"] for c in deploy.get("checks", []) if not c.get("passed")][:3]

        chain    = _PROMPT | _get_llm()
        response = chain.invoke({
            "full_name":            repo.get("full_name", "Unknown"),
            "language":             repo.get("language", "Unknown"),
            "stars":                repo.get("stars", 0),
            "open_issues":          repo.get("open_issues", 0),
            "overall_health_score": hs.get("overall_health_score", "N/A"),
            "health_label":         hs.get("health_label", "UNKNOWN"),
            "quality_score":        hs.get("quality_score", "N/A"),
            "stability_score":      hs.get("stability_score", "N/A"),
            "activity_score":       hs.get("activity_score", "N/A"),
            "total_cost_usd":       f"{hs.get('total_cost_of_inaction_usd', 0):,}",
            "bus_number":           bus.get("bus_number", "N/A"),
            "bus_risk":             bus.get("risk_level", ""),
            "top_author_pct":       bus.get("top_author_owns_pct", 0),
            "bus_interpretation":   bus.get("interpretation", ""),
            "security_label":       sec.get("security_label", "UNKNOWN"),
            "secret_count":         sec.get("secret_count", 0),
            "vuln_count":           sec.get("vuln_count", 0),
            "source_files":         test.get("source_files", 0),
            "test_files":           test.get("test_files", 0),
            "test_ratio":           test.get("test_to_source_ratio_pct", 0),
            "coverage_label":       test.get("coverage_label", "UNKNOWN"),
            "total_deps":           dep.get("total_dependencies", 0),
            "outdated_count":       dep.get("outdated_count", 0),
            "dep_risk":             dep.get("risk_level", "UNKNOWN"),
            "team_burnout_score":   burn.get("team_burnout_score", 0),
            "team_burnout_risk":    burn.get("team_risk_level", "UNKNOWN"),
            "after_hours_pct":      burn.get("team_after_hours_commit_pct", 0),
            "revert_storm_count":   len(burn.get("revert_storms", [])),
            "burnout_narrative":    burn.get("narrative", "No burnout data."),
            "team_cascade_risk":    casc.get("team_cascade_risk", "UNKNOWN"),
            "top_cascade_file":     top_cascade.get("file", "N/A"),
            "top_blast_pct":        top_cascade.get("blast_radius_pct", 0),
            "cascade_summary":      casc.get("summary", "No cascade data."),
            "debt_grade":           debt.get("debt_grade", "N/A"),
            "debt_hours":           debt.get("principal_hours", 0),
            "debt_usd_now":         debt.get("principal_usd", 0),
            "debt_usd_12m":         debt.get("cost_in_12_months_usd", 0),
            "debt_growth_multiple": debt.get("growth_multiple_12m", 1),
            "deploy_score":         deploy.get("readiness_score", 0),
            "deploy_label":         deploy.get("readiness_label", "UNKNOWN"),
            "deploy_missing":       ", ".join(missing) if missing else "None",
            "components_json":      json.dumps(comps, indent=2),
            "format_instructions":  _format_instructions,
        })

        parsed = _output_parser.parse(response.content.strip())

        for key in ("top_actions", "cost_summary"):
            if isinstance(parsed.get(key), str):
                try:
                    parsed[key] = json.loads(parsed[key])
                except Exception:
                    pass

        try:
            parsed["predicted_incident_probability_30d_pct"] = int(
                parsed.get("predicted_incident_probability_30d_pct", 0)
            )
        except (ValueError, TypeError):
            parsed["predicted_incident_probability_30d_pct"] = 0

        return parsed

    except EnvironmentError as e:
        return {"error": str(e), "executive_summary": "AI report unavailable — GROQ_API_KEY not set."}
    except Exception as e:
        return {"error": f"AI report generation failed: {type(e).__name__}: {e}"}
