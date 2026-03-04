# phase2_filter.py
# ─────────────────────────────────────────────────────────────────
# Phase 2 — FILTER
# Scores each profile using rule-based signals first.
# Since SerpAPI returns limited profile data, we send all
# ambiguous AND low-scoring profiles to Groq LLM for a
# smarter classification decision.
# ─────────────────────────────────────────────────────────────────

import json
import os
import time
from groq import Groq
from dotenv import load_dotenv
from config import (
    GROQ_MODEL, AMBIGUOUS_SCORE_MIN, AMBIGUOUS_SCORE_MAX,
    RAW_OUTPUT, FILTERED_OUTPUT
)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ── Rule-based scoring ────────────────────────────────────────────

PROFESSOR_TITLE_KEYWORDS = [
    "professor", "prof.", "prof ", "faculty", "lecturer",
    "associate professor", "assistant professor", "dr.", "doctor",
    "principal investigator", "pi ", "research scientist", "director"
]

STUDENT_KEYWORDS = [
    "phd student", "phd candidate", "ph.d. student", "graduate student",
    "doctoral student", "ms student", "master student", "undergraduate",
    "postdoc", "post-doc", "postdoctoral"
]


def rule_based_score(profile: dict) -> int:
    """
    Scores a profile 0–100 using hard signals.
    Higher = more likely a professor.

    Score ranges:
      > 60  → auto KEEP (clearly professor)
      20–60 → send to Groq LLM
      < 20  → auto DROP (clearly not)
    """
    score = 0
    affiliation = profile.get("affiliation", "").lower()
    email       = profile.get("email_domain", "").lower()
    text        = (
        affiliation + " " +
        profile.get("paper_title", "") + " " +
        profile.get("paper_snippet", "") + " " +
        " ".join(profile.get("interests", []))
    ).lower()

    # ── Positive signals ──────────────────────────────────────────

    # Title keywords in affiliation (strongest signal)
    if any(kw in affiliation for kw in PROFESSOR_TITLE_KEYWORDS):
        score += 30

    # "Verified email at X.edu" — note: SerpAPI uses this format, NOT @
    if "verified email at" in email:
        score += 15
    elif "@" in email:
        score += 15   # fallback for direct @ format

    # Unknown affiliation = weak signal, skip
    if affiliation and affiliation != "unknown affiliation":
        score += 5    # at least has some affiliation

    # Citations
    if profile.get("citedby", 0) > 5000:
        score += 20
    elif profile.get("citedby", 0) > 1000:
        score += 15
    elif profile.get("citedby", 0) > 300:
        score += 8

    # H-index
    if profile.get("hindex", 0) > 30:
        score += 15
    elif profile.get("hindex", 0) > 15:
        score += 10
    elif profile.get("hindex", 0) > 8:
        score += 5

    # ── Negative signals ──────────────────────────────────────────

    # Student keywords anywhere in text
    if any(kw in text for kw in STUDENT_KEYWORDS):
        score -= 30

    # "university student" in affiliation = definitely not professor
    if "university student" in affiliation:
        score -= 40

    # Very low citations AND no hindex = likely not a professor
    if profile.get("citedby", 0) < 20 and profile.get("hindex", 0) == 0:
        score -= 20

    return score


# ── Groq LLM classification ───────────────────────────────────────

def classify_with_groq(profile: dict) -> dict:
    """
    Sends a profile to Groq LLM and asks it to classify as
    professor / student / unclear.
    Uses paper title + snippet as extra context since we have
    limited direct profile data from SerpAPI.
    """
    prompt = f"""You are an academic data classifier. Based on the information below,
determine if this person is likely a current university professor (faculty member).

Use the paper title and snippet as context clues about their seniority and role.

Profile:
- Name: {profile.get('name', 'Unknown')}
- University: {profile.get('university_searched', 'Unknown')}
- Affiliation text: {profile.get('affiliation', 'None')}
- Citations: {profile.get('citedby', 0)}
- Research Interests: {', '.join(profile.get('interests', [])) or 'None listed'}
- Paper they authored: {profile.get('paper_title', 'Unknown')}
- Paper context: {profile.get('paper_snippet', 'None')[:300]}

Signals that suggest professor: senior authorship, high citations, established research area,
long publication history, named as PI or supervisor.

Signals that suggest student/other: first author on single paper, very low citations,
thesis-style titles, "student" or "candidate" in snippet.

Respond ONLY with valid JSON. No explanation outside JSON:
{{
  "label": "professor" or "student" or "unclear",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<one sentence>"
}}"""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError:
        return {"label": "unclear", "confidence": 0.3, "reason": "LLM returned unparseable response"}
    except Exception as e:
        print(f"    [Groq] Error: {e}")
        return {"label": "unclear", "confidence": 0.3, "reason": f"API error: {str(e)}"}


# ── Main Phase 2 runner ───────────────────────────────────────────

def run_phase2(profiles: list = None) -> list:
    """
    Main Phase 2 runner.
    - High scoring profiles (>AMBIGUOUS_SCORE_MAX) → auto keep
    - Everything else → send to Groq LLM for classification
    - Saves filtered results to JSON
    """
    if profiles is None:
        with open(RAW_OUTPUT, "r", encoding="utf-8") as f:
            profiles = json.load(f)

    print(f"\n[Phase 2] Scoring {len(profiles)} profiles...")

    filtered = []
    groq_call_count = 0

    for i, profile in enumerate(profiles):
        score = rule_based_score(profile)
        profile["rule_score"] = score

        if score > AMBIGUOUS_SCORE_MAX:
            # Clearly a professor — auto keep, no LLM needed
            profile["llm_label"]       = "professor"
            profile["llm_confidence"]  = 0.9
            profile["llm_reason"]      = "High rule-based score — skipped LLM"
            profile["filter_decision"] = "keep"

        elif score < AMBIGUOUS_SCORE_MIN:
            # Clearly not a professor — auto drop, no LLM needed
            profile["llm_label"]       = "student"
            profile["llm_confidence"]  = 0.1
            profile["llm_reason"]      = "Low rule-based score — skipped LLM"
            profile["filter_decision"] = "drop"

        else:
            # Ambiguous zone (20–60) — let Groq decide
            print(f"  [LLM] Groq classifying: {profile.get('name')} (rule_score={score})")
            llm_result = classify_with_groq(profile)

            profile["llm_label"]       = llm_result.get("label", "unclear")
            profile["llm_confidence"]  = llm_result.get("confidence", 0.5)
            profile["llm_reason"]      = llm_result.get("reason", "")
            profile["filter_decision"] = (
                "keep" if llm_result.get("label") == "professor" else "drop"
            )
            groq_call_count += 1
            time.sleep(0.3)

        status = "✅ KEEP" if profile["filter_decision"] == "keep" else "❌ DROP"
        print(f"  [{i+1}] {profile.get('name')} | score={score} "
              f"| llm={profile['llm_label']} ({profile['llm_confidence']}) | {status}")

        filtered.append(profile)

    kept = [p for p in filtered if p["filter_decision"] == "keep"]

    os.makedirs("data", exist_ok=True)
    with open(FILTERED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, ensure_ascii=False)

    print(f"\n[Phase 2] Groq API calls made: {groq_call_count}")
    print(f"[Phase 2] Kept {len(kept)} / {len(profiles)} profiles")
    print(f"[Phase 2] Saved to {FILTERED_OUTPUT}")

    return kept


if __name__ == "__main__":
    run_phase2()