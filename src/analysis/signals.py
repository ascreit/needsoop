"""
Signal detection for identifying user needs, frustrations, and desires.

Loads patterns from config/signals.yaml and matches them against post text.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a detected signal in text."""

    signal_type: str
    matches: list[str]
    weight: float


@dataclass
class SignalConfig:
    """Configuration for a signal type."""

    name: str
    description: str
    weight: float
    patterns: list[str]
    compiled_patterns: list[re.Pattern]


class SignalDetector:
    """
    Detects signal patterns in text.

    Loads signal definitions from a YAML file and provides methods
    to match text against those patterns.
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize the signal detector.

        Args:
            config_path: Path to signals.yaml. If None, uses default location.
        """
        if config_path is None:
            # Default to config/signals.yaml relative to project root
            config_path = Path(__file__).parent.parent.parent / "config" / "signals.yaml"

        self.config_path = Path(config_path)
        self.signals: dict[str, SignalConfig] = {}
        self.exclusion_patterns: list[re.Pattern] = []
        self.min_length: int = 20
        self.max_length: int = 1000

        self._load_config()

    def _load_config(self) -> None:
        """Load signal configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Signal config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Load signal definitions
        signals_config = config.get("signals", {})
        for name, signal_data in signals_config.items():
            patterns = signal_data.get("patterns", [])
            compiled = [
                re.compile(re.escape(p), re.IGNORECASE) for p in patterns
            ]
            self.signals[name] = SignalConfig(
                name=name,
                description=signal_data.get("description", ""),
                weight=signal_data.get("weight", 1.0),
                patterns=patterns,
                compiled_patterns=compiled,
            )

        # Load exclusion patterns
        exclusions = config.get("exclusions", {})
        exclusion_patterns = exclusions.get("patterns", [])
        self.exclusion_patterns = [
            re.compile(re.escape(p), re.IGNORECASE) for p in exclusion_patterns
        ]

        # Load language settings
        language_config = config.get("language", {})
        self.min_length = language_config.get("min_length", 20)
        self.max_length = language_config.get("max_length", 1000)

        logger.info(
            f"Loaded {len(self.signals)} signal types with "
            f"{sum(len(s.patterns) for s in self.signals.values())} patterns"
        )

    def _is_excluded(self, text: str) -> bool:
        """Check if text matches any exclusion pattern."""
        for pattern in self.exclusion_patterns:
            if pattern.search(text):
                return True
        return False

    def detect(self, text: str) -> Signal | None:
        """
        Detect signals in the given text.

        Args:
            text: The text to analyze.

        Returns:
            Signal object if a match is found, None otherwise.
        """
        # Length check
        if len(text) < self.min_length or len(text) > self.max_length:
            return None

        # Exclusion check
        if self._is_excluded(text):
            return None

        # Find matching signals
        best_signal: Signal | None = None
        best_weight = 0.0

        for signal_config in self.signals.values():
            matches = []
            for i, pattern in enumerate(signal_config.compiled_patterns):
                if pattern.search(text):
                    matches.append(signal_config.patterns[i])

            if matches:
                # Calculate effective weight based on number of matches
                effective_weight = signal_config.weight * (1 + 0.1 * (len(matches) - 1))

                if effective_weight > best_weight:
                    best_weight = effective_weight
                    best_signal = Signal(
                        signal_type=signal_config.name,
                        matches=matches,
                        weight=effective_weight,
                    )

        return best_signal

    def detect_all(self, text: str) -> list[Signal]:
        """
        Detect all signals in the given text.

        Args:
            text: The text to analyze.

        Returns:
            List of all detected signals.
        """
        # Length check
        if len(text) < self.min_length or len(text) > self.max_length:
            return []

        # Exclusion check
        if self._is_excluded(text):
            return []

        signals = []
        for signal_config in self.signals.values():
            matches = []
            for i, pattern in enumerate(signal_config.compiled_patterns):
                if pattern.search(text):
                    matches.append(signal_config.patterns[i])

            if matches:
                signals.append(
                    Signal(
                        signal_type=signal_config.name,
                        matches=matches,
                        weight=signal_config.weight,
                    )
                )

        return signals

    def get_matcher(self) -> Callable[[str], tuple[str | None, list[str]]]:
        """
        Get a matcher function for use with collectors.

        Returns:
            A function that takes text and returns (signal_type, matches).
        """

        def matcher(text: str) -> tuple[str | None, list[str]]:
            signal = self.detect(text)
            if signal:
                return signal.signal_type, signal.matches
            return None, []

        return matcher

    def get_signal_types(self) -> list[str]:
        """Get list of all signal type names."""
        return list(self.signals.keys())

    def get_signal_weight(self, signal_type: str) -> float:
        """Get the weight for a signal type."""
        if signal_type in self.signals:
            return self.signals[signal_type].weight
        return 1.0
