# pipeline.py
# ─────────────────────────────────────────────────────────────────
# MASTER PIPELINE — runs Phase 1 → 2 → 3 end to end
# Just run:  python pipeline.py
# ─────────────────────────────────────────────────────────────────

from phase1_collect import run_phase1
from phase2_filter import run_phase2
from phase3_verify import run_phase3


def main():
    print("=" * 60)
    print("  AMBITIO — Google Scholar → Professor Mapping Pipeline")
    print("=" * 60)

    print("\n🔵 PHASE 1 — Collecting Scholar profiles...")
    raw_profiles = run_phase1()

    print("\n🟡 PHASE 2 — Filtering & LLM classification...")
    filtered_profiles = run_phase2(raw_profiles)

    print("\n🟢 PHASE 3 — Verifying against faculty pages...")
    final_df = run_phase3(filtered_profiles)

    print("\n" + "=" * 60)
    print(f"  ✅ Pipeline complete!")
    print(f"  📄 Final output saved to: data/final_output.csv")
    print(f"  📊 Total verified professors: {len(final_df)}")
    print("=" * 60)


if __name__ == "__main__":
    main()