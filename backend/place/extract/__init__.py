"""Extraction pipeline (docs/03 §2): fetch -> batch extract -> resolve -> review.

Everything here is importable and unit-testable without any credential;
key-gated paths (Reddit API, Anthropic batch API, embedding rerank) raise
place.config.MissingCredential / degrade cleanly when keys are absent.
"""
