"""Lightweight token estimation for DeepSeek models.

Zero external dependencies. Conservative estimates keep us safely
within context limits without needing a real tokenizer.
"""

# DeepSeek-V3/V4 advertise 128K context; use 120K for safety margin.
CONTEXT_LIMIT = 120_000

# DeepSeek Max models support 1M context; use 900K for safety margin.
MAX_CONTEXT_LIMIT = 900_000

# Max output tokens for standard vs Max models
DEFAULT_MAX_TOKENS = 65_536
MAX_TOKENS = 131_072

# Never use more than 80% of context for input — leave room for output.
SAFETY_RATIO = 0.80

# Minimum token reserve for the LLM response regardless of input size.
MIN_OUTPUT_RESERVE = 8_192


def estimate_tokens(text: str) -> int:
    """Conservative token count for mixed CJK/English text.

    Rough model (intentionally overestimates):
      - CJK characters: ~1-2 tokens each
      - ASCII words:     ~1 token per 3-4 chars
      - JSON syntax:     ~1 token each

    Using 0.5 tokens per character is a safe upper bound that keeps
    us comfortably within context limits for all text mixes.
    """
    if not text:
        return 0
    return max(1, int(len(text) * 0.5))
