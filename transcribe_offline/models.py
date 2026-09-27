"""Model pins. The only place model URLs, commits and hashes live."""

# All mandatory: without tokenizer.json faster-whisper downloads a fallback tokenizer,
# without preprocessor_config.json it silently uses the wrong mel-bin count.
REQUIRED_FILES = (
    "model.bin",
    "config.json",
    "tokenizer.json",
    "vocabulary.json",
    "preprocessor_config.json",
)
