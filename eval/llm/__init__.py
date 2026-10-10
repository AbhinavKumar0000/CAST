"""eval.llm package - LLM provider abstractions."""

from eval.llm.kilo_provider import KiloProvider, LLMResult, get_provider
from eval.llm.provider import OpencodeProvider, GeminiProvider

__all__ = [
    "KiloProvider",
    "OpencodeProvider", 
    "GeminiProvider",
    "LLMResult",
    "get_provider",
]