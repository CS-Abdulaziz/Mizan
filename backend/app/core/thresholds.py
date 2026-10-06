"""Tunable thresholds (SPEC §7.3, §7.4, §7.5, §8.5). Tuned on the bench dev split only (TASKS B20)."""

# Extraction (§7.2)
MAX_CLAIMS = 10

# Verse matcher (§7.3)
QURAN_MIN_WORDS = 3
QURAN_TOP_K = 10
QURAN_VERIFIED_RAW = 96.0  # raw alignment score for `verified` with no word diffs
QURAN_CANDIDATE_RAW = 80.0  # below this: no verse match
QURAN_CONTAINMENT_RATIO = 1.3  # quote > 1.3x candidate words -> candidate cannot be `verified`
QURAN_MAX_LOCATIONS = 5
QURAN_SPELLING_VARIANT_RATIO = 80.0  # D-13: token pair this similar (len >= 4) is a spelling variant, not a diff

# Non-Arabic verse path (§7.3, B12)
VERSE_VECTOR_TOP_K = 8
VERSE_LEXICAL_TOP_K = 8
VERSE_VERIFIER_TOP = 6

# Hadith retrieval (§7.4)
DORAR_EARLY_STOP = 90.0  # token_set_ratio of a Dorar result to the query that stops further queries
MATN_GROUP_RATIO = 92.0  # token_set_ratio for grouping Dorar results of the same matn
HADITH_VECTOR_TOP_K = 8
HADITH_LOCAL_TOP_K = 8
HADITH_VERIFIER_TOP = 6

# Verifier confidence (§7.5)
VERSE_ACCEPT_CONF = 0.70
HADITH_EXACT_CONF = 0.70
HADITH_SAME_MEANING_CONF = 0.85  # AMENDMENT 3
ALTERED_CONF = 0.75

# Authentic alternative (§8.5)
ALTERNATIVE_MIN_SIMILARITY = 0.75
