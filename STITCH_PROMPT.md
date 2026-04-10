# STITCH UI PROMPT — PredictiveEng Dashboard
# Copy everything below this line into Google Stitch

Build a dark-themed single-page dashboard called PredictiveEng.
Backend runs at http://localhost:8000.

---

## GLOBAL STYLE
Background: #0a0a0f
Card background: #13131f
Border: 1px solid #1e1e30
Accent purple: #7c6ef2
Font: Inter, system-ui
Border radius on all cards: 14px
Text primary: #e8e8f0
Text secondary: #8888aa
Danger red: #e84545
Warning amber: #f0a500
Success green: #3dba6e

---

## SECTION 1 — HERO INPUT BAR (full width, top of page)

Left side: Logo area
- Icon: two angle brackets </> in accent purple, 28px
- App name: "PredictiveEng" in white, 22px bold
- Tagline below: "Predict failures before they happen" in secondary text, 13px

Center: Input row (horizontal, all on one line)
- Text input, placeholder: "GitHub repo URL  e.g. https://github.com/pallets/flask"
  Width: 380px, dark background #1a1a2e, border accent purple on focus
- Password input, placeholder: "Your GitHub Personal Access Token"
  Width: 260px, same style
  Info icon tooltip on hover: "Your token is used only for this request and never stored on our servers. Generate at github.com/settings/tokens with repo scope."
- Button: "Analyze" — solid accent purple background, white text, 14px bold
  On click: POST to /api/analyze with repo_url and github_token
  Get job_id from response, start polling

Below inputs, small text centered in secondary color:
"🔒 Your token is never stored. It is used only to clone your repository."

Right side: "Batch Analyze" link — opens a small modal with a textarea
for multiple repo URLs (one per line) and the token field.
On submit: POST to /api/analyze/portfolio

---

## SECTION 2 — PROGRESS BAR (visible only while job is running)

Full-width card, centered content:
- Repo name as heading
- Animated purple progress bar using progress_pct value
- Status message text below bar in secondary color
- Polling: GET /api/jobs/{job_id} every 2.5 seconds
- Stop polling when status = "completed" or "failed"
- On "failed": show red error card with the error message
- On "completed": hide this section, show Section 3

---

## SECTION 3 — RESULTS DASHBOARD (10 cards, 3-column grid on desktop, 1 column mobile)

When status = "completed", fire all these fetches in parallel using Promise.all:
  GET /api/jobs/{id}/health
  GET /api/jobs/{id}/ceo-brief
  GET /api/jobs/{id}/components
  GET /api/jobs/{id}/security
  GET /api/jobs/{id}/bus-factor
  GET /api/jobs/{id}/test-coverage
  GET /api/jobs/{id}/burnout
  GET /api/jobs/{id}/cascade
  GET /api/jobs/{id}/debt
  GET /api/jobs/{id}/deployment

---

### CARD 1 — Overall Health (row 1, col 1)

Data: /health

- Repo full_name as card title, gray text, 13px
- Large circular gauge (SVG or canvas), 160px diameter
  Value: overall_health_score out of 100
  Color: red if score < 40, amber if < 75, green if >= 75
  Number in center: big bold white
- health_label badge below gauge: pill shape, same color
- Three mini stat pills in a row below badge:
  "Quality: X" | "Stability: X" | "Activity: X"
- health_analogy from ceo_brief in italic, 13px, left purple border, below stats

---

### CARD 2 — CEO Intelligence Brief (row 1, col 2, spans 2 columns)

Data: /ceo-brief

- Card title: "AI Intelligence Brief" with small Claude logo spark icon
- executive_summary as paragraph, 15px, line-height 1.7
- Row of two badges: business_risk_level (colored) + predicted_incident_probability_30d_pct shown as "XX% incident risk in 30 days"
- critical_finding in italic amber text, 13px
- "Top Actions" heading, then numbered list (1, 2, 3):
  Each action: action text bold + timeline chip (outline pill) + "saves $X" in green
- Bottom row: two side-by-side boxes
  Left box dark red tint: "Cost if ignored: $X"
  Right box dark green tint: "Fix now: $X"

---

### CARD 3 — Component Risk Table (row 2, col 1)

Data: /components

- Card title: "Component Failure Predictions"
- total_cost_of_inaction_usd shown bold as "Total risk exposure: $X"
- Table:
  Columns: File | Failure % | Days | Risk | Fix Now
  Sort by failure_probability_pct descending
  Row background by risk_level:
    CRITICAL: rgba(232,69,69,0.15)
    HIGH: rgba(240,165,0,0.12)
    MEDIUM: rgba(255,220,0,0.08)
    LOW: transparent
  Risk column: colored badge pill

---

### CARD 4 — Security Report (row 2, col 2)

Data: /security

- Card title: "Security Scan"
- security_label as large colored badge, centered
- Four mini stat boxes in a 2x2 grid:
  Total findings | Secrets found | Vulnerabilities | Security score
- Severity bar: horizontal row showing CRITICAL / HIGH / MEDIUM counts
  Each segment proportional width, colored accordingly
- Top 5 findings list:
  Each row: type badge (SECRET / VULN) + label + file:line
- Divider then "Dependency Risk" sub-section:
  total_dependencies, outdated_count as stats
  risk_level badge

---

### CARD 5 — Bus Factor (row 2, col 3)

Data: /bus-factor

- Card title: "Bus Factor — Knowledge Risk"
- Giant number: bus_number, 64px, centered
  Color: red if bus_number = 1, amber if = 2, yellow if = 3, green if > 3
- risk_level badge below the number
- interpretation text in italic, secondary color, 13px, centered
- "Top Contributors" heading
- Horizontal bar chart: top 5 contributors, bar proportional to commit count
  Each bar: author name left, commit count right, bar in accent purple

---

### CARD 6 — Test Coverage + Commit Trend (row 3, col 1)

Data: /test-coverage and /health

Top half: Test Coverage
- Donut chart: test_files (purple) vs source_files (dark)
  Center label: test_to_source_ratio_pct + "%"
- coverage_label badge
- Two stats: "Source files: X" and "Test files: X"

Bottom half: Commit Trend
- Line chart using Chart.js
  X axis: last 12 weeks (week labels)
  Y axis: commit count
  Line color: accent purple, fill area semi-transparent
- Chart title: "Commit Activity — Last 12 Weeks"

---

### CARD 7 — Developer Burnout Index (row 3, col 2)

Data: /burnout

- Card title: "Developer Burnout Index 🔥"
- Large burnout score gauge same style as Card 1
  team_burnout_score out of 100
  Red if >= 60, amber if >= 40, yellow if >= 20, green if < 20
- team_risk_level badge
- Three stats in a row: After-hours % | Weekend % | Revert storms
- narrative in italic, secondary color, 13px
- "Developer Breakdown" mini table:
  Columns: Name | Score | After-hours % | Peak Hour | Risk
  Sort by burnout_score descending
  Risk badge colored per level
- If revert_storms array not empty: show a warning box
  "⚠ Revert Storm Detected" with date range and revert count

---

### CARD 8 — Cascade Blast Radius (row 3, col 3)

Data: /cascade

- Card title: "Cascade Failure Blast Radius 💥"
- team_cascade_risk as large badge
- summary text in amber italic
- Blast Radius table from blast_radius_by_file:
  Columns: File | Failure % | Blast % | Severity | Business Impact
  Color severity: CATASTROPHIC=dark red, SEVERE=red, HIGH=amber, MODERATE=yellow
  Each row is clickable — on click expand below row to show:
    direct_dependents list and full business_impact text
- "Critical Hub Files" section below table:
  Each hub file as a tag pill: "filename (imported by N files)"
  Label above: "⚠ Shared Infrastructure — highest ripple risk"

---

### CARD 9 — Technical Debt Calculator (row 4, col 1-2, spans 2 columns)

Data: /debt

- Card title: "Technical Debt — Compound Interest Engine 📈"
- debt_grade as very large letter badge left-aligned
  A+=green, A=teal, B=blue, C=amber, D=red
- Three big metric boxes in a row:
  "Today" → principal_usd formatted as $X,XXX
  "6 Months" → cost_in_6_months_usd
  "12 Months" → cost_in_12_months_usd in red
  Each box dark background, value big and bold, label small secondary above
- Subtitle: "At 15% monthly compound interest — same math as a credit card"
- Line chart from monthly_projection (Chart.js):
  X: Month 1–6, Y: debt_usd
  Line: red, fill area red at 15% opacity (looks alarming)
  Axis labels in secondary color
- Stacked horizontal bar: debt_breakdown_usd
  Segments: Complexity | Maintainability | Bug Churn | Missing Tests
  Each segment different shade of purple/amber/red
  Show USD value inside each segment if wide enough
- loan_analogy blockquote:
  Background: rgba(240,165,0,0.08), left border 3px amber, padding 16px
  Text italic, 13px
- roi_of_paying_now in green highlight box at bottom

---

### CARD 10 — Deployment Readiness (row 4, col 3)

Data: /deployment

- Card title: "Deployment Readiness"
- readiness_score as circular gauge (same component as Card 1)
- readiness_label as badge
- "X/15 checks passed" in secondary text
- Four category bars (infrastructure, security, observability, hygiene):
  Each: category name left, score_pct right, bar fills proportionally
  Bar color: green if >= 75, amber if >= 50, red if < 50
- Fix List heading, then numbered list from fix_list:
  Each: priority number + check name + severity badge + effort estimate
  Sort by weight descending (already sorted)
- If production_blocker is true: red banner at top of card
  "🚨 Production Blocker Detected"

---

## CHART.JS SETUP

Load Chart.js from CDN:
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>

All chart defaults:
  backgroundColor: transparent
  gridLines color: #1e1e30
  tick color: #8888aa
  legend text: #e8e8f0

---

## API CALL SEQUENCE

Step 1: POST /api/analyze → { job_id, status }
Step 2: setInterval every 2500ms → GET /api/jobs/{job_id}
        Stop when status = "completed" or "failed"
Step 3: Promise.all([
          fetch(/health), fetch(/ceo-brief), fetch(/components),
          fetch(/security), fetch(/bus-factor), fetch(/test-coverage),
          fetch(/burnout), fetch(/cascade), fetch(/debt), fetch(/deployment)
        ])
Step 4: Render all 10 cards from the resolved data

Never call GET /api/jobs/{id}/report — it returns the full payload and is too heavy.
