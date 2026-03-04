# config.py
# ─────────────────────────────────────────
# Central config — edit universities here
# ─────────────────────────────────────────

UNIVERSITIES = [
    "University of Toronto",
    "MIT",
    "Stanford University"
]

# Minimum confidence score to include in final output (0.0 to 1.0)
MIN_CONFIDENCE = 0.4

# How many Scholar profiles to fetch per university
MAX_PROFILES_PER_UNI = 40

# Groq model to use
GROQ_MODEL = "llama-3.1-8b-instant"

# Rule-based score threshold below which we call Groq LLM
# Profiles scoring between these values go to LLM
AMBIGUOUS_SCORE_MIN = 20
AMBIGUOUS_SCORE_MAX = 60

# Official faculty page URLs for cross-verification (Phase 3)
FACULTY_PAGES = {
    "University of Toronto": "https://web.cs.toronto.edu/people/faculty-directory",
    "MIT": "https://www.eecs.mit.edu/role/faculty/",
    "Stanford University": "https://www.cs.stanford.edu/people/faculty"
}

# Output file paths
RAW_OUTPUT    = "data/raw_profiles.json"
FILTERED_OUTPUT = "data/filtered_profiles.json"
FINAL_OUTPUT  = "data/final_output.csv"