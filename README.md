# 🎓 Google Scholar → University Professor Mapping Pipeline

> **Ambitio Data Engineer Assignment** — Vedant Gokhe

A 3-phase data pipeline that takes a list of universities and produces a structured, confidence-scored dataset of Google Scholar profiles mapped to verified current university professors.

---

## 📌 Problem Statement

Google Scholar is one of the richest public sources of academic author data — but it's messy, unverified, and not directly linked to university faculty listings. A profile might say "Stanford University" but belong to a PhD student, a visiting researcher, or someone who left five years ago.

**Input:** A list of university names (e.g., MIT, Stanford, University of Toronto)  
**Output:** A clean, structured CSV where each row is a Google Scholar profile confidence-scored and mapped to a verified university professor.

---

## 🏗️ Architecture Overview

```
Universities List
       │
       ▼
┌─────────────────────────────────┐
│  Phase 1 — COLLECT              │
│  SerpAPI Google Scholar search  │
│  + per-author profile enrichment│
└────────────────┬────────────────┘
                 │ raw_profiles.json
                 ▼
┌─────────────────────────────────┐
│  Phase 2 — FILTER               │
│  Rule-based scoring             │
│  + Groq LLM for ambiguous cases │
└────────────────┬────────────────┘
                 │ filtered_profiles.json
                 ▼
┌─────────────────────────────────┐
│  Phase 3 — VERIFY               │
│  SerpAPI Google Search          │
│  Official domain URL matching   │
└────────────────┬────────────────┘
                 │
                 ▼
          final_output.csv
       (62 verified professors)
```

---

## 📁 Repository Structure

```
ambitio-assignment/
│
├── pipeline.py            # Master runner — executes Phase 1 → 2 → 3 end to end
├── phase1_collect.py      # Collect & enrich Scholar profiles via SerpAPI
├── phase2_filter.py       # Rule-based scoring + Groq LLM classification
├── phase3_verify.py       # Verify against official university domains
├── config.py              # Central config (universities, thresholds, file paths)
├── requirements.txt       # Python dependencies
├── writeup.md             # Full approach, tradeoffs, and design decisions
│
└── data/
    ├── raw_profiles.json       # Phase 1 output — all collected Scholar profiles
    ├── filtered_profiles.json  # Phase 2 output — professor-only profiles
    └── final_output.csv        # Phase 3 output — final verified dataset (62 professors)
```

---

## ⚙️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/VedantGokhe/ambitio-assignment.git
cd ambitio-assignment
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the root directory:
```env
SERPAPI_KEY=your_serpapi_key_here
GROQ_API_KEY=your_groq_api_key_here
```

| Key | Where to get it |
|-----|----------------|
| `SERPAPI_KEY` | [serpapi.com](https://serpapi.com) — free tier available |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free tier available |

### 4. Run the pipeline
```bash
python pipeline.py
```

---

## 🔧 Configuration (`config.py`)

All pipeline settings are centralized in `config.py`:

```python
UNIVERSITIES = [
    "University of Toronto",
    "MIT",
    "Stanford University"
]

MIN_CONFIDENCE       = 0.4    # Minimum score to appear in final output
MAX_PROFILES_PER_UNI = 40     # Scholar profiles fetched per university
GROQ_MODEL           = "llama-3.1-8b-instant"
AMBIGUOUS_SCORE_MIN  = 20     # Rule score below this → auto drop
AMBIGUOUS_SCORE_MAX  = 60     # Rule score above this → auto keep
```

To run for different universities, just edit the `UNIVERSITIES` list and re-run `pipeline.py`.

---

## 🔍 Phase Breakdown

### Phase 1 — Collect (`phase1_collect.py`)

Uses **SerpAPI** with targeted department-level queries to find Scholar profiles:
```
"computer science professor MIT"
"machine learning professor Stanford University"
"physics professor University of Toronto"
...
```

For each discovered author, a second SerpAPI call (`google_scholar_author` engine) fetches their full profile — affiliation text, verified email domain, citation count, and h-index.

> **Why targeted queries?** Searching just `"MIT"` returns random papers that mention MIT anywhere — co-authors from other institutions flood the results. Targeted queries dramatically improve signal-to-noise ratio.

---

### Phase 2 — Filter (`phase2_filter.py`)

A hybrid scoring system that avoids sending every profile to an LLM:

**Rule-based scoring (fast & free):**

| Signal | Score |
|--------|-------|
| Affiliation contains "Professor", "Faculty", "Lecturer" | +30 |
| Verified institutional email present | +15 |
| Has any affiliation text | +5 |
| Citations > 5,000 | +20 |
| Citations > 1,000 | +15 |
| Citations > 300 | +8 |
| H-index > 30 | +15 |
| H-index > 15 | +10 |
| "PhD student", "graduate student" in bio | −30 |
| "university student" in affiliation | −40 |
| Very low citations AND no h-index | −20 |

**Decision logic:**
- Score **> 60** → Auto KEEP (clearly a professor)
- Score **20–60** → Send to **Groq LLM** (`llama-3.1-8b-instant`) for smart classification
- Score **< 20** → Auto DROP (clearly not a professor)

The LLM receives profile affiliation, citation count, paper title, and snippet — and returns structured JSON with `label`, `confidence`, and `reason`.

---

### Phase 3 — Verify (`phase3_verify.py`)

Verifies each filtered professor by searching Google for:
```
"{name} {university} professor"
```
and checking if an official university domain URL (`mit.edu`, `stanford.edu`, `utoronto.ca`) appears in the top 5 results — with the professor's last name in the title or snippet.

**Final confidence score formula:**
```
confidence = 0.20 (base)
           + rule_score/100 × 0.30
           + llm_confidence × 0.25
           + 0.25 (if faculty page verified)
```

Profiles with `final_confidence < 0.4` are excluded from the final output.

---

## 📊 Sample Output

The final CSV (`data/final_output.csv`) contains **62 verified professor profiles** across MIT, Stanford, and University of Toronto:

| Column | Description |
|--------|-------------|
| `name` | Professor's full name |
| `scholar_id` | Unique Google Scholar author ID |
| `university` | University searched |
| `affiliation_text` | Raw affiliation from Scholar profile |
| `scholar_url` | Link to Scholar profile |
| `email_domain` | Verified institutional email (if available) |
| `research_interests` | Comma-separated research areas |
| `citations` | Total citation count |
| `hindex` | H-index |
| `rule_score` | Phase 2 rule-based score (0–100) |
| `llm_label` | Groq LLM classification |
| `llm_confidence` | LLM confidence (0.0–1.0) |
| `faculty_page_match` | Whether a university domain URL was found |
| `verified_url` | The matched official URL |
| `final_confidence` | Combined final confidence score |
| `verified` | ✅ Yes / ❌ No |

---

## 🚧 Real-World Challenges Encountered

**1. `scholarly` library blocked immediately**  
Google blocks direct Scholar scraping. Switched to SerpAPI as a managed, reliable alternative.

**2. SerpAPI deprecated `google_scholar_profiles` engine mid-build**  
Adapted on the fly — switched to `google_scholar` search + `google_scholar_author` enrichment. This is a real operational risk in data pipelines built on unofficial sources.

**3. JavaScript-rendered faculty pages**  
IIT Bombay's faculty page is JS-rendered — the scraper returned an empty page. Replaced with University of Toronto (static HTML). At scale, this requires Playwright or Selenium.

**4. Co-author contamination**  
Papers by MIT professors appear with co-authors from other institutions. Phase 2 affiliation scoring and Phase 3 domain verification catch and filter these out.

**5. Non-Latin script names**  
Profiles with Chinese character names (e.g., `孟心飛`) cause fuzzy matching failures. The pipeline handles these gracefully with low confidence scores rather than crashing.

---

## 📈 Scaling to 500 Universities

At 500 universities × 40 profiles = **~30,000 API calls**. Key changes needed:

- **Async requests** — `asyncio` + rate limiting for 10–20x speedup
- **University name normalization** — ROR (Research Organization Registry) to handle "Stanford" vs "Stanford University" vs "Stanford CS"
- **Incremental refresh** — `last_verified` timestamps + scheduled re-verification for records older than 30 days
- **Tiered verification** — skip SerpAPI Phase 3 for clearly high-confidence profiles
- **Faculty-first data flow** — scrape official faculty directories first, use Scholar as enrichment (reverses current flow for higher precision)
- **Confidence score calibration** — use labeled ground truth + logistic regression to learn optimal scoring weights

---

## 🛠️ Tech Stack

| Tool | Purpose |
|------|---------|
| [SerpAPI](https://serpapi.com) | Google Scholar search + author enrichment + verification |
| [Groq](https://groq.com) (`llama-3.1-8b-instant`) | LLM classification for ambiguous profiles |
| `pandas` | Data processing and CSV output |
| `rapidfuzz` | Fuzzy name matching for verification |
| `python-dotenv` | Environment variable management |

---

## 📝 Full Writeup

For the complete approach, assumptions, tradeoffs, and edge case analysis, see [`writeup.md`](./writeup.md).

---

## 👤 Author

**Vedant Gokhe**  
Submitted for Ambitio Data Engineer Assignment —04 March 2026