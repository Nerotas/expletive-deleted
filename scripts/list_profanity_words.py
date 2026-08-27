#!/usr/bin/env python3
"""List all words in the better_profanity censoring list"""

from better_profanity import profanity

def main() -> int:
    profanity.load_censor_words()
    censor_words = sorted(str(word) for word in profanity.CENSOR_WORDSET)

    print(f"Total profanity words in library: {len(censor_words)}\n")
    print("Full list of censored words:")
    print("=" * 60)

    for index, word in enumerate(censor_words, 1):
        print(f"{index:3d}. {word}")

    print("\n" + "=" * 60)
    print(f"Total: {len(censor_words)} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
