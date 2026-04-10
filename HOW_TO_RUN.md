# HOW TO RUN PredictiveEng — Complete Step by Step

---

## STEP 1 — Make sure you have Python installed

Open terminal and run:
    python --version

You need Python 3.10 or higher.
If not installed: download from https://python.org

---

## STEP 2 — Put all files in one folder

Create a folder called predictiveeng and place all these files inside it:
    analyzer.py
    ai_reporter.py
    burnout_detector.py
    cascade_analyzer.py
    debt_calculator.py
    deployment_readiness.py
    security_scanner.py
    main.py
    requirements.txt

---

## STEP 3 — Create a virtual environment

In your terminal, go into the folder:
    cd predictiveeng

Create virtual environment:
    python -m venv venv

Activate it:
    Windows:   venv\Scripts\activate
    Mac/Linux: source venv/bin/activate

You should see (venv) at the start of your terminal line.

---

## STEP 4 — Install all dependencies

    pip install -r requirements.txt

This will take 2–3 minutes. Wait for it to finish.
If you see any red errors, run this instead:
    pip install -r requirements.txt --no-cache-dir

---

## STEP 5 — Create your .env file

In the predictiveeng folder, create a new file called exactly:
    .env

Open it and add this one line:
    ANTHROPIC_API_KEY=your_actual_api_key_here

Replace your_actual_api_key_here with your real Anthropic API key.
Get it from: https://console.anthropic.com/settings/keys

Save the file.

IMPORTANT: The GitHub token is NOT in the .env file anymore.
Users provide their own token through the UI. This was the judge's suggestion.

---

## STEP 6 — Start the server

    python main.py

You should see:
    INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process

The server is now running.

---

## STEP 7 — Test it is working

Open your browser and go to:
    http://localhost:8000

You should see:
    {"service":"Predictive Engineering Intelligence Platform","version":"2.0.0",...}

Open interactive API docs at:
    http://localhost:8000/docs

---

## STEP 8 — Test with a real repo (from the docs page or curl)

Using the /docs page:
1. Click POST /api/analyze
2. Click "Try it out"
3. Paste this body:
    {
      "repo_url": "https://github.com/pallets/flask",
      "github_token": "your_github_pat_here",
      "include_ai_report": true
    }
4. Click Execute
5. Copy the job_id from the response
6. Go to GET /api/jobs/{job_id} and paste the job_id
7. Keep clicking Execute until status = "completed"
8. Then try GET /api/jobs/{job_id}/health to see results

---

## HOW TO GET A GITHUB TOKEN

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name like "predictiveeng-test"
4. Check the "repo" scope checkbox
5. Click "Generate token"
6. Copy the token (starts with ghp_)
7. Paste it in the UI or API request

For PUBLIC repos, the token still helps avoid rate limiting.
For PRIVATE repos, the token must have repo access.

---

## COMMON ERRORS AND FIXES

Error: ModuleNotFoundError: No module named 'langchain_anthropic'
Fix: pip install langchain-anthropic

Error: ModuleNotFoundError: No module named 'pydriller'
Fix: pip install pydriller

Error: EnvironmentError: ANTHROPIC_API_KEY not set
Fix: Make sure your .env file is in the same folder as main.py and contains
     ANTHROPIC_API_KEY=your_key

Error: git.exc.GitCommandNotFound
Fix: Install Git from https://git-scm.com/downloads

Error: port 8000 already in use
Fix: python main.py --port 8001
     Or kill whatever is using port 8000

---

## FILE STRUCTURE WHEN EVERYTHING IS CORRECT

predictiveeng/
├── main.py
├── analyzer.py
├── ai_reporter.py
├── burnout_detector.py
├── cascade_analyzer.py
├── debt_calculator.py
├── deployment_readiness.py
├── security_scanner.py
├── requirements.txt
└── .env                    ← you create this manually

---

## FOR THE DEMO — USE THIS TEST REPO

https://github.com/pallets/flask

It is public, has 4+ years of commit history, reasonable complexity,
multiple contributors — gives good results for all 10 analysis modules.

Analysis takes about 45–90 seconds for this repo.

---

## QUICK REFERENCE — ALL ENDPOINTS

POST /api/analyze                    Start analysis
GET  /api/jobs/{id}                  Check progress
GET  /api/jobs/{id}/health           Health score + AI summary
GET  /api/jobs/{id}/ceo-brief        Full CEO brief
GET  /api/jobs/{id}/components       Component failure predictions
GET  /api/jobs/{id}/security         Security scan results
GET  /api/jobs/{id}/bus-factor       Bus factor + contributors
GET  /api/jobs/{id}/test-coverage    Test coverage heuristic
GET  /api/jobs/{id}/burnout          Developer burnout index
GET  /api/jobs/{id}/cascade          Blast radius mapping
GET  /api/jobs/{id}/debt             Technical debt compound interest
GET  /api/jobs/{id}/deployment       Deployment readiness
