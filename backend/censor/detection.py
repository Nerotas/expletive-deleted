"""Isolated vendor-dictionary review without mutating a running job policy."""

from typing import Dict, List


def _profanity_dictionary():
    """Create an isolated vendor dictionary only when broad detection is requested."""
    from better_profanity import profanity

    # The package-level object is mutable. Sharing it lets dictionary review requests
    # replace the active processing policy while a job is running.
    return type(profanity)()


def find_review_candidates(
    words_data: Dict,
    censor_words: set[str],
    exclude_words: set[str],
) -> List[Dict]:
    """Find vendor-list matches that a user has not yet classified as censor or ignore."""
    profanity = _profanity_dictionary()
    candidates = []
    for word_obj in words_data.get("words", []):
        word = str(word_obj.get("word", "")).strip(".,!?;:\"' \t")
        word_lower = word.lower()
        if not word or word_lower in censor_words or word_lower in exclude_words:
            continue
        if profanity.contains_profanity(word_lower):
            candidates.append(
                {
                    "word": word_lower,
                    "start": word_obj.get("start"),
                    "end": word_obj.get("end"),
                }
            )
    return candidates
