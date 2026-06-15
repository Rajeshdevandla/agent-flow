"""Anthropic API Configuration

Centralized configuration for the Anthropic SDK.
All SDK settings should come through here, not scattered across files.
"""

import os
from dataclasses import dataclass
from typing import Optional

import anthropic


@dataclass
class AnthropicConfig:
    """Configuration for Anthropic SDK usage."""

    # Model settings
    model: str = "claude-opus-4-5"
    max_tokens: int = 4096
    temperature: float = 1.0  # Default Claude temperature

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    retry_backoff: float = 2.0  # exponential backoff multiplier

    # Timeout settings
    timeout: float = 60.0  # seconds per request

    # Safety settings
    safety_threshold: int = 70  # minimum safety score 0-100
    block_on_violation: bool = True

    @classmethod
    def from_env(cls) -> "AnthropicConfig":
        """Load configuration from environment variables."""
        return cls(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
            max_retries=int(os.getenv("AGENT_MAX_RETRIES", "3")),
            timeout=float(os.getenv("AGENT_TIMEOUT", "60")),
            safety_threshold=int(os.getenv("SAFETY_THRESHOLD", "70")),
            block_on_violation=os.getenv("SAFETY_BLOCK_ON_VIOLATION", "true").lower() == "true"
        )


class AnthropicClientFactory:
    """Factory for creating Anthropic clients with consistent settings."""

    _instance: Optional[anthropic.Anthropic] = None
    _config: Optional[AnthropicConfig] = None

    @classmethod
    def get_client(cls, config: Optional[AnthropicConfig] = None) -> anthropic.Anthropic:
        """Get or create Anthropic client (singleton pattern).

        Design decision: Singleton prevents creating multiple clients
        with different configurations, which could cause inconsistent behavior.
        """
        if cls._instance is None or config is not None:
            cfg = config or AnthropicConfig.from_env()
            cls._config = cfg

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Get your key from: https://console.anthropic.com/"
                )

            cls._instance = anthropic.Anthropic(
                api_key=api_key,
                max_retries=cfg.max_retries,
                timeout=cfg.timeout
            )

        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (mainly for testing)."""
        cls._instance = None
        cls._config = None

    @classmethod
    def get_config(cls) -> AnthropicConfig:
        """Get current configuration."""
        if cls._config is None:
            cls._config = AnthropicConfig.from_env()
        return cls._config


def get_default_system_prompt() -> str:
    """Get the default system prompt used across all agents.

    Design decision: Shared base prompt ensures consistent behavior
    and values across all agents.
    """
    return (
        "You are a helpful, harmless, and honest AI assistant. "
        "You are part of the AgentFlow v2.0 multi-agent system. "
        "\n\nCore behaviors:\n"
        "- Always return structured JSON when asked\n"
        "- Never fabricate facts - say INSUFFICIENT_DATA when uncertain\n"
        "- Be honest about limitations and uncertainties\n"
        "- Prioritize safety and helpfulness in all responses\n"
        "- Follow Constitutional AI principles from Bai et al. (2022)"
    )


def validate_api_key() -> bool:
    """Validate that the API key is set and looks valid."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return False
    # Anthropic API keys start with sk-ant-
    return api_key.startswith("sk-ant-") or len(api_key) > 20
