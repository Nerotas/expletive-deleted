#!/usr/bin/env python3
"""List all words in the better_profanity censoring list"""

from better_profanity import profanity

# Load the default censoring words
profanity.load_censor_words()

# Get the list of words and convert to strings
censor_words = sorted([str(word) for word in profanity.CENSOR_WORDSET])

print(f"Total profanity words in library: {len(censor_words)}\n")
print("Full list of censored words:")
print("=" * 60)

for i, word in enumerate(censor_words, 1):
    print(f"{i:3d}. {word}")

print("\n" + "=" * 60)
print(f"Total: {len(censor_words)} words")
