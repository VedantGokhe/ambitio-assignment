# phase3_verify.py
# ─────────────────────────────────────────────────────────────────
# Phase 3 — VERIFY & SCORE
# Uses SerpAPI to verify each professor by searching their name
# + university and checking if an official university page appears.
# Assigns a final confidence score to each profile.
# ─────────────────────────────────────────────────────────────────

import json
import os
import time
import pandas as pd
from dotenv import load_dotenv
from serpapi import GoogleSearch
from rapidfuzz import fuzz
from config import FILTERED_OUTPUT, FINAL_OUTPUT, MIN_CONFIDENCE

load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Official domain keywords per university — if any result URL contains
# these, we consider it a verified match
UNIVERSITY_DOMAINS = {
    "University of Toronto": ["utoronto.ca", "toronto.edu"],
    "MIT":                   ["mit.edu"],
    "Stanford University":   ["stanford.edu"],
}


# ── SerpAPI verification ──────────────────────────────────────────

def verify_professor_via_serpapi(name: str, university: str) -> tuple:
    """
    Searches Google for "{name} {university} professor" and checks
    if any result URL belongs to the official university domain.

    Returns (verified: bool, matched_url: str)
    """
    domains = UNIVERSITY_DOMAINS.get(university, [])
    if not domains:
        return False, ""

    query = f"{name} {university} professor"

    try:
        params = {
            "engine":  "google",
            "q":       query,
            "api_key": SERPAPI_KEY,
            "num":     5,
        }
        results  = GoogleSearch(params).get_dict()
        organic  = results.get("organic_results", [])

        for result in organic:
            url   = result.get("link", "").lower()
            title = result.get("title", "").lower()

            # Check if result URL is from official university domain
            if any(domain in url for domain in domains):
                # Also check name appears in title or snippet (avoid false matches)
                snippet    = result.get("snippet", "").lower()
                name_lower = name.lower().split()
                # At least last name should appear
                last_name  = name_lower[-1] if name_lower else ""
                if last_name and (last_name in title or last_name in snippet):
                    return True, result.get("link", "")

        return False, ""

    except Exception as e:
        print(f"    [SerpAPI] Error verifying {name}: {e}")
        return False, ""


# ── Final confidence scorer ───────────────────────────────────────

def compute_final_confidence(profile: dict, faculty_matched: bool) -> float:
    """
    Combines all signals into one final confidence score (0.0 to 1.0).

    Breakdown:
      Base (Scholar profile exists)    → 0.20
      Rule-based score (clamped 0–100) → up to 0.30
      LLM confidence                   → up to 0.25
      Faculty page match               → 0.25
    """
    base         = 0.20
    rule_clamped = max(profile.get("rule_score", 0), 0)  # clamp negatives to 0
    rule_part    = min(rule_clamped / 100, 1.0) * 0.30
    llm_part     = profile.get("llm_confidence", 0.5) * 0.25
    verify_part  = 0.25 if faculty_matched else 0.0

    total = base + rule_part + llm_part + verify_part
    return round(min(total, 1.0), 3)


# ── Main Phase 3 runner ───────────────────────────────────────────

def run_phase3(profiles: list = None) -> pd.DataFrame:
    """
    Main Phase 3 runner.
    Verifies each professor using SerpAPI Google search,
    assigns final confidence scores, saves to CSV.
    """
    if profiles is None:
        with open(FILTERED_OUTPUT, "r", encoding="utf-8") as f:
            profiles = json.load(f)

    print(f"\n[Phase 3] Verifying {len(profiles)} filtered profiles...")

    results = []
    serpapi_calls = 0

    for i, profile in enumerate(profiles):
        uni  = profile.get("university_searched", "")
        name = profile.get("name", "")

        print(f"  [{i+1}/{len(profiles)}] Verifying: {name} @ {uni}")

        verified, matched_url = verify_professor_via_serpapi(name, uni)
        confidence = compute_final_confidence(profile, verified)
        serpapi_calls += 1

        row = {
            "name":               name,
            "scholar_id":         profile.get("scholar_id", ""),
            "university":         uni,
            "affiliation_text":   profile.get("affiliation", ""),
            "scholar_url":        profile.get("scholar_url", ""),
            "email_domain":       profile.get("email_domain", ""),
            "research_interests": ", ".join(profile.get("interests", [])),
            "citations":          profile.get("citedby", 0),
            "hindex":             profile.get("hindex", 0),
            "rule_score":         profile.get("rule_score", 0),
            "llm_label":          profile.get("llm_label", ""),
            "llm_confidence":     profile.get("llm_confidence", 0),
            "llm_reason":         profile.get("llm_reason", ""),
            "faculty_page_match": verified,
            "verified_url":       matched_url,
            "final_confidence":   confidence,
            "verified":           "✅ Yes" if verified else "❌ No",
        }
        results.append(row)

        flag = "✅" if verified else "—"
        print(f"    {flag} confidence={confidence} | verified={verified}")

        # Small delay between SerpAPI calls
        time.sleep(0.5)

    df = pd.DataFrame(results)

    # Guard against empty dataframe
    if df.empty:
        print("\n[Phase 3] No profiles to verify.")
        os.makedirs("data", exist_ok=True)
        df.to_csv(FINAL_OUTPUT, index=False, encoding="utf-8")
        return df

    # Filter by minimum confidence
    df = df[df["final_confidence"] >= MIN_CONFIDENCE]

    # Sort by confidence descending
    df = df.sort_values("final_confidence", ascending=False)

    # Remove duplicates — same scholar appearing for multiple universities
    df = df.drop_duplicates(subset=["scholar_id"], keep="first")

    os.makedirs("data", exist_ok=True)
    df.to_csv(FINAL_OUTPUT, index=False, encoding="utf-8")

    print(f"\n[Phase 3] SerpAPI calls made: {serpapi_calls}")
    print(f"[Phase 3] Final dataset: {len(df)} verified professors")
    print(f"[Phase 3] Saved to {FINAL_OUTPUT}")

    return df


if __name__ == "__main__":
    run_phase3()