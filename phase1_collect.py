# phase1_collect.py
# ─────────────────────────────────────────────────────────────────
# Phase 1 — COLLECT
# Uses SerpAPI to search Google Scholar with targeted queries
# like "professor MIT computer science" to get real faculty.
# Multiple department searches per university = better coverage.
# ─────────────────────────────────────────────────────────────────

import json
import time
import random
import os
from dotenv import load_dotenv
from serpapi import GoogleSearch
from config import UNIVERSITIES, MAX_PROFILES_PER_UNI, RAW_OUTPUT

load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Targeted department keywords — these make searches much more precise
DEPARTMENT_KEYWORDS = [
    "computer science professor",
    "engineering professor",
    "machine learning professor",
    "physics professor",
]


def search_scholar(query: str) -> list:
    """
    Runs a single SerpAPI Google Scholar search and returns
    a list of (name, scholar_id, scholar_url, citations, snippet, title).
    """
    try:
        params = {
            "engine":  "google_scholar",
            "q":       query,
            "api_key": SERPAPI_KEY,
            "num":     10,
        }
        results = GoogleSearch(params).get_dict()
        return results.get("organic_results", [])

    except Exception as e:
        print(f"  [SerpAPI] Error on query '{query}': {e}")
        return []


def extract_authors_from_results(results: list, university: str) -> list:
    """
    Pulls author info out of raw SerpAPI Scholar results.
    Filters to only authors who have an actual Scholar profile.
    """
    profiles = []

    for item in results:
        pub_info = item.get("publication_info", {})
        authors  = pub_info.get("authors", [])

        for author in authors:
            author_id = author.get("author_id", "")
            if not author_id:
                continue   # skip — no Scholar profile at all

            profile = {
                "name":                author.get("name", ""),
                "affiliation":         "",
                "email_domain":        "",
                "interests":           [],
                "citedby":             item.get("inline_links", {})
                                           .get("cited_by", {})
                                           .get("total", 0),
                "hindex":              0,
                "scholar_id":          author_id,
                "scholar_url":         author.get("link", ""),
                "university_searched": university,
                "paper_title":         item.get("title", ""),
                "paper_snippet":       item.get("snippet", ""),
            }
            profiles.append(profile)

    return profiles


def enrich_profile_with_serpapi(profile: dict) -> dict:
    """
    Takes a profile with a scholar_id and fetches their full
    Scholar author page via SerpAPI to get:
    - full name, affiliation, email, interests, citations, h-index
    """
    author_id = profile.get("scholar_id", "")
    if not author_id:
        return profile

    try:
        params = {
            "engine":    "google_scholar_author",
            "author_id": author_id,
            "api_key":   SERPAPI_KEY,
        }
        result = GoogleSearch(params).get_dict()
        author = result.get("author", {})

        # Overwrite with richer data
        profile["name"]         = author.get("name", profile["name"])
        profile["affiliation"]  = author.get("affiliations", "")
        profile["email_domain"] = author.get("email", "")
        profile["interests"]    = [
            i.get("title", "")
            for i in result.get("interests", [])
        ]

        # Citations and h-index from cited_by table
        cited = result.get("cited_by", {}).get("table", [])
        for row in cited:
            if "citations" in row:
                profile["citedby"] = row["citations"].get("all", profile["citedby"])
            if "h_index" in row:
                profile["hindex"]  = row["h_index"].get("all", 0)
            if "i10_index" in row:
                profile["i10index"] = row["i10_index"].get("all", 0)

        print(f"    ✅ Enriched: {profile['name']} | {profile['affiliation']} | "
              f"citations: {profile['citedby']} | h-index: {profile['hindex']}")

    except Exception as e:
        print(f"    ⚠️  Could not enrich {profile.get('name')}: {e}")

    return profile


def fetch_profiles_for_university(university_name: str, max_profiles: int) -> list:
    """
    Step 1: Runs targeted searches to collect author IDs.
    Step 2: Enriches each profile with full Scholar data via SerpAPI.
    """
    print(f"\n[Phase 1] Fetching profiles for: {university_name}")
    all_profiles = []
    seen_ids     = set()

    # ── Step 1: Collect author IDs ────────────────────────────────
    for dept in DEPARTMENT_KEYWORDS:
        query = f"{dept} {university_name}"
        print(f"  → Searching: '{query}'")

        results  = search_scholar(query)
        profiles = extract_authors_from_results(results, university_name)

        for p in profiles:
            sid = p["scholar_id"]
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                all_profiles.append(p)
                print(f"    + {p['name']} | id: {sid}")

        if len(all_profiles) >= max_profiles:
            break

        time.sleep(random.uniform(1, 2))

    all_profiles = all_profiles[:max_profiles]

    # ── Step 2: Enrich each profile with full Scholar data ────────
    print(f"\n  [Phase 1] Enriching {len(all_profiles)} profiles with full Scholar data...")
    for i, profile in enumerate(all_profiles):
        print(f"  [{i+1}/{len(all_profiles)}] Enriching: {profile['name']}")
        all_profiles[i] = enrich_profile_with_serpapi(profile)
        time.sleep(random.uniform(1, 2))   # be polite to SerpAPI

    print(f"[Phase 1] Done — {len(all_profiles)} enriched profiles for {university_name}")
    return all_profiles


def run_phase1() -> list:
    """
    Main Phase 1 runner.
    """
    if not SERPAPI_KEY:
        raise ValueError("SERPAPI_KEY not found in .env file!")

    all_profiles = []

    for uni in UNIVERSITIES:
        profiles = fetch_profiles_for_university(uni, MAX_PROFILES_PER_UNI)
        all_profiles.extend(profiles)

    os.makedirs("data", exist_ok=True)
    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_profiles, f, indent=2, ensure_ascii=False)

    print(f"\n[Phase 1] Total profiles collected: {len(all_profiles)}")
    print(f"[Phase 1] Saved to data/raw_profiles.json")

    return all_profiles


if __name__ == "__main__":
    run_phase1()