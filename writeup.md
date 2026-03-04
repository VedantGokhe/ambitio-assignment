# Writeup — Google Scholar to University Professor Mapping Pipeline

**Submitted by:** Vedant Gokhe  
**Assignment:** Ambitio Data Engineer Assignment  
**Date:** 04 March 2026

---

## 1. My Approach and Why I Chose It

The core problem is a **data bridging problem** — Google Scholar is a rich but unverified source, and university faculty pages are verified but hard to scrape at scale. The challenge is connecting these two worlds reliably.

I designed a **3-phase pipeline:**

### Phase 1 — Collect
I initially tried `scholarly` (a Python library that scrapes Google Scholar directly) but Google blocked it immediately, returning zero results. I then switched to **SerpAPI**, which provides a reliable, managed interface to Google Scholar search results.

The key insight in Phase 1 was that searching broadly for `"MIT"` returns random papers mentioning MIT anywhere — not professor profiles. I fixed this by using **targeted department queries** like `"computer science professor MIT"`, `"machine learning professor Stanford University"` across 4 department keywords per university. This gave much better signal.

I then made a **second SerpAPI call per author** using the `google_scholar_author` engine to fetch full profile details — affiliation text, verified email domain, citation count, and h-index. This two-step approach (find → enrich) is what gave us clean, structured data.

### Phase 2 — Filter
I used a **hybrid scoring system:**

**Rule-based scoring first** — fast, free, deterministic:
- `+30` if affiliation text contains "professor", "faculty", "lecturer" etc.
- `+15` if verified institutional email present
- `+20` if citations > 5000
- `−30` if bio contains "PhD student", "graduate student" etc.
- `−40` if affiliation says "university student"

**Groq LLM (`llama-3.1-8b-instant`) for ambiguous cases** — only profiles scoring between 20–60 on the rule-based system get sent to the LLM. This saved API calls while handling edge cases rules can't catch.

The LLM prompt includes the profile's affiliation text, citation count, paper title, and paper snippet — giving it enough context to make a smart judgment. It returns a structured JSON with `label`, `confidence`, and `reason`.

### Phase 3 — Verify
Instead of scraping faculty pages (which are often JavaScript-rendered or paginated and hard to parse reliably), I used **SerpAPI Google Search** to verify each professor by searching `"{name} {university} professor"` and checking if an official university domain URL appears in the top 5 results.

This approach is more robust than page scraping because:
- It works regardless of how the university website is built
- It handles name variations naturally (Google's search handles this)
- It scales to any university without custom scraping logic per site

---

## 2. Assumptions I Made

- **Assumption 1:** A professor who appears in a paper mentioning a university is likely affiliated with that university. This is imperfect — co-authors from other institutions also appear.

- **Assumption 2:** Citation count and h-index are strong proxies for seniority. A researcher with 10,000+ citations is almost certainly a senior faculty member, not a student.

- **Assumption 3:** A verified institutional email (e.g., `@mit.edu`, `@stanford.edu`) signals current affiliation. In practice, people retain old emails after leaving.

- **Assumption 4:** If a Google search for `"Robert L. Byer Stanford University professor"` returns a `stanford.edu` URL containing "Byer" — that's strong verification. This assumes Google's index is reasonably up to date.

- **Assumption 5:** SerpAPI's `google_scholar_author` engine returns accurate profile data. We treat this as ground truth without cross-checking against Scholar directly.

---

## 3. Tradeoffs I Considered

### Coverage vs. Precision
My targeted search queries (`"computer science professor MIT"`) improve precision but reduce coverage. A professor in humanities at MIT won't appear unless I add more department keywords. I chose **precision over coverage** deliberately — it's better to have 60 high-confidence professors than 200 noisy ones for a student-facing product.

### Speed vs. Cost
The two-step SerpAPI approach (search → enrich) uses roughly 2x the API credits compared to search-only. But the enrichment step gives us affiliation text, email, and citation data that makes Phase 2 scoring dramatically more accurate. The extra cost is worth it.

### Rule-based vs. LLM for filtering
Running every profile through Groq would be slower and use more API calls. Running none through Groq misses ambiguous cases. The **20–60 score band** as the LLM trigger zone was calibrated by looking at actual profiles — scores above 60 are reliably professors (affiliation text says "Professor of X at Y"), scores below 20 are reliably not (no email, <20 citations, student keywords). Only the middle band needs judgment.

### Completeness vs. Accuracy
Some real professors were dropped — researchers with unconventional titles like "Principal Investigator" or "Research Scientist" may score below threshold. I accepted this tradeoff to avoid false positives, which are more damaging in a student-facing product where a wrong recommendation about who teaches at a school could mislead an applicant.

---

## 4. Edge Cases Spotted

### The "co-author contamination" problem
When searching `"machine learning professor MIT"`, the results include papers by MIT professors — but also their co-authors from other institutions. A paper by an MIT professor might have 4 co-authors from Delft, Princeton, and CMU. All 5 get added to our "MIT profiles" list.

**How I handled it:** Phase 2 uses affiliation text (fetched from Scholar profile) to score — if the affiliation says "Delft University", the rule-based score won't get the professor title bonus for MIT, and Phase 3 verification will fail when checking for `mit.edu` URLs. These profiles end up with low final confidence and are either filtered out or clearly marked as unverified.

### JavaScript-rendered faculty pages
IIT Bombay's faculty page is JavaScript-rendered — our scraper got an empty page. I replaced IIT Bombay with University of Toronto which has a static, scrapeable page. At scale, this would require Playwright or Selenium for JS-heavy sites.

### SerpAPI discontinuing Google Scholar Profiles API
Midway through development, I discovered that SerpAPI's `google_scholar_profiles` engine was discontinued. I adapted by switching to the `google_scholar` engine with targeted queries, then using `google_scholar_author` for enrichment. This kind of API deprecation is a real operational risk in data pipelines.

### Duplicate profiles
The same researcher (e.g., "Martin Kenney") appeared across multiple university searches since his paper mentioned both MIT and Stanford. I handled this with `drop_duplicates(subset=["scholar_id"])` in Phase 3, keeping the highest-confidence entry.

### Names in non-Latin scripts
One profile appeared with the name `孟心飛` — a Chinese character name. Fuzzy name matching fails for these, and SerpAPI verification is unreliable. I let the pipeline handle it gracefully (it gets a low confidence score) rather than crashing.

### "Unknown affiliation" profiles
Some Scholar profiles show "Unknown affiliation" — the person hasn't filled in their profile. These get no title keyword bonus in Phase 2 but aren't penalized unless other signals are also weak.

---

## 5. What I'd Build Differently With Another Week and 500 Universities

### Better data collection
Instead of paper-level search → author extraction, I would use **university faculty directory pages as the primary source** and Scholar as enrichment. Scrape the official list of professors first (using Playwright for JS-rendered pages), then look each one up on Scholar by name + university. This reverses the flow and gives much higher precision.

### Smarter university name normalization
"Stanford", "Stanford University", "Stanford CS", "Leland Stanford Jr. University" all mean the same thing. I'd build a university name normalization layer using a reference database like the **ROR (Research Organization Registry)** which maps name variants to canonical IDs.

### Async pipeline for scale
At 500 universities × 40 profiles × 2 SerpAPI calls = 40,000 API calls. The current sequential pipeline would take hours. I'd rewrite Phase 1 and Phase 3 using **Python `asyncio`** with rate limiting to run requests concurrently, reducing runtime by 10–20x.

### Caching and incremental updates
Data goes stale the moment it's collected. I'd add a **last_verified timestamp** to each record and build an incremental refresh job that re-verifies records older than 30 days. A Redis cache would store SerpAPI results to avoid re-fetching the same profiles.

### Confidence score calibration
The current confidence formula (base + rule_part + llm_part + verify_part) has manually chosen weights. With more data, I'd **calibrate these weights** using a labeled ground truth dataset — manually verified professor/non-professor labels for ~500 profiles — and use logistic regression to learn optimal weights.

### Handling professors without Scholar profiles
The current pipeline only finds people who appear in Scholar search results. A significant minority of professors — especially in humanities and social sciences — don't have Scholar profiles. A complete solution would cross-reference **ORCID**, **ResearchGate**, and institutional directories to fill these gaps.

---

## 6. Directly Addressing the Assignment Nudges

### "Scholar doesn't offer a clean API. Your choices here have real consequences."

This was the first wall I hit. The `scholarly` Python library — which scrapes Scholar directly — was blocked by Google immediately, returning zero results. I adapted by switching to **SerpAPI**, a paid managed scraping service with a free tier. This choice has real consequences:

- **Pro:** Reliable, fast, doesn't get blocked, returns structured JSON
- **Con:** Costs money at scale, has rate limits, and as I discovered mid-build, SerpAPI itself deprecated their `google_scholar_profiles` engine without warning — forcing me to pivot to a different search approach on the fly

The lesson: any pipeline built on top of an unofficial data source is fragile. Scholar's lack of a public API is a fundamental architectural constraint, not just a technical inconvenience.

---

### "Not everyone affiliated with a university is a professor. What signals help you tell the difference — and how reliable are they?"

I identified the following signals ranked by reliability:

| Signal | Reliability | Why |
|---|---|---|
| Affiliation text contains "Professor", "Faculty" | High | Self-reported but specific — people rarely fake this |
| Verified institutional email (@mit.edu) | Medium-High | Requires domain ownership, but alumni retain old emails |
| Citations > 5000 | High | PhD students almost never reach this threshold |
| H-index > 15 | High | Requires sustained multi-year publication output |
| Publishing for 7+ years | Medium | Inferable from paper dates, but not always available |
| "PhD student" / "candidate" in bio | High (negative) | People are honest about being students |

No single signal is definitive. A postdoctoral researcher might have 8,000 citations. An emeritus professor might have an outdated email. This is why I combine all signals into a single confidence score rather than using binary rules — the answer is probabilistic, not absolute.

---

### "This works for 3 universities. What happens at 500?"

At 500 universities the math breaks down quickly. Assuming 40 profiles per university:

- **Phase 1:** 500 × 4 dept queries = 2,000 SerpAPI calls for search + 20,000 calls for enrichment
- **Phase 2:** 20,000 Groq LLM calls (only ambiguous ones, so maybe 8,000)
- **Phase 3:** 20,000 SerpAPI verification calls

**Total: ~30,000 API calls.** Running sequentially at 0.5s each = 4+ hours and significant API cost.

To handle this I would:
1. **Async requests** — run 50 concurrent API calls instead of 1, reducing time by 50x
2. **University batching** — process universities in parallel batches
3. **Tiered verification** — only run expensive SerpAPI verification on profiles scoring above a threshold in Phase 2, skipping clearly low-confidence ones
4. **Cost estimation layer** — before running, estimate API cost and alert if over budget

---

### "Profiles change. People move. How stale is your data the moment you collect it?"

The answer is: **immediately stale, and getting staler every day.**

A professor who moved from MIT to Stanford last month still has their old MIT affiliation on Scholar. Our pipeline would confidently label them as an MIT professor — incorrectly.

Concrete staleness risks:
- Professor leaves academia → still appears as "Professor of X"
- Professor moves universities → old affiliation persists until they update it
- PhD student graduates and becomes a professor → our pipeline might have flagged them as a student
- Emeritus professors → technically no longer teaching but still listed

**What I'd build to handle this:**
- Add a `collected_at` timestamp to every record
- Build a **staleness score** — profiles with no recent publications (last 2 years) get flagged
- Schedule weekly re-verification jobs for high-confidence records
- Add a `last_verified` field so downstream users know exactly how fresh the data is
- Accept that this data is a **snapshot**, not ground truth, and communicate that clearly in the output

---

### "Some professors don't have a Scholar profile. Some profiles don't have verified emails. Some names are shared by five people at the same institution."

**No Scholar profile:** Our pipeline has a blind spot here — we can only find people who appear in Scholar search results. Professors in humanities, law, or medicine are underrepresented on Scholar. A complete solution would cross-reference ORCID, institutional directories, and ResearchGate to find these people.

**No verified email:** 40%+ of Scholar profiles have no verified email. I handle this by treating email as one of several signals rather than a hard requirement. A professor with 50,000 citations and an affiliation saying "Professor of Physics, Stanford University" gets a high confidence score even without a verified email.

**Shared names:** "David Miller" appears at multiple universities. I deduplicate using Scholar's `author_id` — a unique identifier that persists even if the person changes their name or affiliation. Two profiles with the same name but different `author_id` are treated as different people. Two entries with the same `author_id` are deduplicated, keeping the highest-confidence version.



The pipeline works end-to-end for 3 universities and produces a clean, confidence-scored dataset of Google Scholar profiles mapped to likely university professors. The biggest architectural decision was using **targeted search queries + profile enrichment** rather than broad scraping, and using a **hybrid rule-based + LLM filter** that's both accurate and cost-efficient.

The core tension in this problem is that no single signal is reliable enough alone — a verified email might be outdated, a high citation count might belong to a postdoc, and an official title in the affiliation text might be self-reported incorrectly. The confidence score combines all signals to give a probabilistic answer rather than a binary one, which is the right approach for data that is inherently messy and uncertain.

> "The best data engineers don't just move data — they understand it."  
> This pipeline was built with that principle in mind.