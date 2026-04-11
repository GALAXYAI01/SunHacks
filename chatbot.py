"""
chatbot.py — PredictiveEng AI Assistant.

Two entry points:
  chat()      — answer any question about the analysis with exact file/line context
  fix_code()  — return a fully refactored version of a specific function
"""

import os
import json
from typing import Any


def _get_llm(max_tokens=600):
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            groq_api_key=groq_key,
            max_tokens=max_tokens,
            temperature=0.2,
        )
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            anthropic_api_key=anthropic_key,
            max_tokens=max_tokens,
            temperature=0.2,
        )
    raise EnvironmentError(
        "No AI key found. Set GROQ_API_KEY or ANTHROPIC_API_KEY in your .env file."
    )


# ── Context builder ───────────────────────────────────────────────────

def _build_context(analysis: dict) -> str:
    repo  = analysis.get("repo_info", {})
    hs    = analysis.get("health_scores", {})
    comps = hs.get("component_predictions", [])[:8]
    sec   = analysis.get("security", {})
    burn  = analysis.get("burnout", {})
    debt  = analysis.get("technical_debt", {})
    casc  = analysis.get("cascade_risk", {})

    comp_lines = []
    for c in comps:
        mc  = c.get("most_complex_function")
        pf  = c.get("problematic_functions", [])
        loc = (f" | WORST FUNCTION: {mc['function_name']}() "
               f"line {mc['line_start']} complexity {mc['complexity']}"
               if mc else "")
        others = ", ".join(
            f"{f['function_name']}() L{f['line_start']} CC={f['complexity']}"
            for f in pf[:3]
        )
        comp_lines.append(
            f"  • {c['component']}: "
            f"failure={c['failure_probability_pct']}% "
            f"risk={c['risk_level']}{loc}"
            + (f" | other issues: {others}" if others else "")
        )

    cascade_top = ""
    blast = casc.get("blast_radius_by_file", [])
    if blast:
        t = blast[0]
        loc = t.get("error_location", "")
        cascade_top = (
            f"\n  TOP CASCADE FILE: {t['file']} "
            f"blast={t['blast_radius_pct']}% "
            f"severity={t.get('severity','?')}"
            + (f" | ERROR AT: {loc}" if loc else "")
        )

    return (
        f"REPO: {repo.get('full_name')} ({repo.get('language')})\n"
        f"HEALTH: {hs.get('overall_health_score')}/100 ({hs.get('health_label')})\n"
        f"DEBT: grade={debt.get('debt_grade')} "
        f"today=${debt.get('principal_usd',0):,} "
        f"12m=${debt.get('cost_in_12_months_usd',0):,}\n"
        f"SECURITY: {sec.get('security_label')} "
        f"secrets={sec.get('secret_count')} "
        f"vulns={sec.get('vuln_count')}\n"
        f"BURNOUT: {burn.get('team_burnout_score')}/100 "
        f"after_hours={burn.get('team_after_hours_commit_pct')}%\n"
        f"CASCADE RISK: {casc.get('team_cascade_risk')}{cascade_top}\n\n"
        f"RISKY FILES WITH EXACT ERROR LOCATIONS:\n"
        + "\n".join(comp_lines)
    )


# ── Chat ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are PredictiveEng Assistant — an expert software engineer embedded in the PredictiveEng dashboard.

You have the full analysis of the repository the user is viewing.

What you can do:
1. Explain any metric, score, or finding in plain English
2. Tell the user EXACTLY which file, function, and line number has a problem
3. Explain why a high cyclomatic complexity number is dangerous
4. Suggest concrete, specific fixes — not vague advice
5. Write actual Python code when asked to refactor something
6. Prioritize what to fix first based on business cost and risk

Response rules:
- Be concise — 2-4 sentences max unless the user asks for more
- Always cite file + function + line when discussing a code problem
- Frame issues in business terms (cost of downtime, hours to fix, etc.)
- You are PredictiveEng Assistant, not Claude or any LLM brand

ANALYSIS CONTEXT:
{context}
"""


def chat(question: str, analysis: dict, history: list = None) -> str:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
        context = _build_context(analysis)
        llm     = _get_llm(max_tokens=512)

        messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
        for msg in (history or [])[-6:]:
            cls = HumanMessage if msg.get("role") == "user" else AIMessage
            messages.append(cls(content=msg["content"]))
        messages.append(HumanMessage(content=question))

        return llm.invoke(messages).content.strip()

    except EnvironmentError as e:
        return f"⚠️ Chatbot unavailable: {e}"
    except Exception as e:
        return f"Sorry, I hit an error: {type(e).__name__}: {e}"


# ── General chat (no analysis needed) ─────────────────────────────────

GENERAL_SYSTEM = """\
You are PredictiveEng Assistant — an expert software engineering AI assistant.

You are part of the PredictiveEng platform, which analyzes GitHub repositories for:
- Code health and quality
- Security vulnerabilities
- Technical debt
- Developer burnout
- Deployment readiness
- Cascade failure risk

Right now, no repository analysis is loaded. You can still help with:
1. General software engineering questions
2. Explaining code concepts (cyclomatic complexity, technical debt, etc.)
3. Best practices for code quality, testing, and deployment
4. Answering questions about how PredictiveEng works

Response rules:
- Be concise — 2-4 sentences max unless the user asks for more
- Be helpful and specific
- If the user asks about analysis results, tell them to run an analysis first
- You are PredictiveEng Assistant, not Claude or any LLM brand
"""


def general_chat(question: str, history: list = None) -> str:
    """Chat without analysis context — general software engineering assistant."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
        llm = _get_llm(max_tokens=512)

        messages = [SystemMessage(content=GENERAL_SYSTEM)]
        for msg in (history or [])[-6:]:
            cls = HumanMessage if msg.get("role") == "user" else AIMessage
            messages.append(cls(content=msg["content"]))
        messages.append(HumanMessage(content=question))

        return llm.invoke(messages).content.strip()

    except EnvironmentError as e:
        return f"⚠️ Chatbot unavailable: {e}"
    except Exception as e:
        return f"Sorry, I hit an error: {type(e).__name__}: {e}"


# ── Fix code ──────────────────────────────────────────────────────────

FIX_SYSTEM = (
    "You are an expert Python software engineer specializing in code refactoring. "
    "You always return ONLY valid JSON with no markdown fences."
)

FIX_PROMPT = """\
Refactor the following Python function to reduce cyclomatic complexity.

FILE: {file_path}
FUNCTION: {function_name}() at line {line_start}
CURRENT COMPLEXITY: {complexity} (safe threshold is ≤ 5)

ORIGINAL CODE:
{original_code}

Return a JSON object with EXACTLY this structure:
{{
  "explanation": "plain English: what makes this complex and why it is risky",
  "issues": ["issue 1", "issue 2", "issue 3"],
  "refactored_code": "the complete refactored Python code — runnable, same behavior",
  "changes_made": ["change 1", "change 2", "change 3"],
  "new_complexity_estimate": 3,
  "time_to_implement": "30 minutes"
}}

Refactoring rules:
- Preserve the exact function signature and return behavior
- Maximum nesting depth: 2 levels
- Extract nested conditions into well-named helper functions
- Replace long if-elif chains with dictionaries where appropriate
- Add descriptive variable names
- The refactored_code field must contain COMPLETE, RUNNABLE Python code
"""


def fix_code(
    file_path: str,
    function_name: str,
    line_start: int,
    complexity: int,
    original_code: str,
    analysis: dict,
) -> dict:
    """
    Returns:
      explanation, issues[], refactored_code, changes_made[],
      new_complexity_estimate, time_to_implement
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = _get_llm(max_tokens=1500)

        prompt = FIX_PROMPT.format(
            file_path=file_path,
            function_name=function_name,
            line_start=line_start,
            complexity=complexity,
            original_code=original_code,
        )
        response = llm.invoke([
            SystemMessage(content=FIX_SYSTEM),
            HumanMessage(content=prompt),
        ])

        raw = response.content.strip()
        # Strip any accidental markdown fences
        for fence in ("```json", "```python", "```"):
            raw = raw.replace(fence, "")
        raw = raw.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Build a useful fallback even when JSON parsing fails
            result = {
                "explanation": (
                    f"'{function_name}()' has cyclomatic complexity {complexity}, "
                    f"which is {complexity - 5} points above the safe threshold of 5. "
                    f"Every extra point adds another code path that can fail in production."
                ),
                "issues": [
                    f"Cyclomatic complexity {complexity} means {complexity} independent "
                    f"paths through the function — each needs its own test case.",
                    "Functions above CC=10 have statistically 40% more bugs.",
                    "High nesting makes the function hard to read, test, and modify.",
                ],
                "refactored_code": (
                    f"# Could not auto-generate. Paste this function into the chat\n"
                    f"# and ask: 'refactor {function_name} to reduce complexity'\n\n"
                    + original_code
                ),
                "changes_made": [
                    "See explanation above for manual refactoring guidance."
                ],
                "new_complexity_estimate": max(3, complexity // 2),
                "time_to_implement": "1–3 hours",
            }

        # Always attach metadata
        result.update({
            "file_path":           file_path,
            "function_name":       function_name,
            "line_start":          line_start,
            "original_complexity": complexity,
        })
        return result

    except EnvironmentError as e:
        return {
            "error":       str(e),
            "explanation": str(e),
            "refactored_code": original_code,
            "issues":     ["AI key not configured."],
            "changes_made":[],
            "new_complexity_estimate": complexity,
            "time_to_implement": "N/A",
        }
    except Exception as e:
        return {
            "error":       f"{type(e).__name__}: {e}",
            "explanation": "Could not generate fix. Check your API key and try again.",
            "refactored_code": original_code,
            "issues":     [str(e)],
            "changes_made":[],
            "new_complexity_estimate": complexity,
            "time_to_implement": "N/A",
        }