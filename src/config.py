"""Configuration models and loading utilities."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TimingConfig(BaseModel):
    """Timing configuration for benchmarks."""

    sleep_time: int = Field(default=90, description="Wait time before starting benchmark (seconds)")
    benchmark_time: int = Field(default=600, description="Duration of each benchmark iteration (seconds)")
    sample_interval: int = Field(default=15, description="Time between samples (seconds)")


class SafetyConfig(BaseModel):
    """Safety limits configuration."""

    max_temp: int = Field(default=66, description="Maximum chip temperature (°C)")
    max_vr_temp: int = Field(default=86, description="Maximum voltage regulator temperature (°C)")
    max_power: int = Field(default=30, description="Maximum power consumption (W)")
    max_allowed_voltage: int = Field(default=1400, description="Maximum core voltage (mV)")
    min_allowed_voltage: int = Field(default=1000, description="Minimum core voltage (mV)")
    max_allowed_frequency: int = Field(default=1200, description="Maximum core frequency (MHz)")
    min_allowed_frequency: int = Field(default=400, description="Minimum core frequency (MHz)")
    min_input_voltage: int = Field(default=4800, description="Minimum input voltage (mV)")
    max_input_voltage: int = Field(default=5500, description="Maximum input voltage (mV)")


class IncrementsConfig(BaseModel):
    """Increment values for stepping through voltage/frequency."""

    voltage_increment: int = Field(default=15, description="Voltage increment step (mV)")
    frequency_increment: int = Field(default=20, description="Frequency increment step (MHz)")


class AnalysisConfig(BaseModel):
    """Configuration for result analysis."""

    hashrate_tolerance: float = Field(default=0.94, description="Minimum hashrate as fraction of expected")
    trim_outliers: int = Field(default=3, description="Number of outliers to trim from each end")
    warmup_samples: int = Field(default=6, description="Number of warmup samples to exclude from temp averaging")
    min_samples: int = Field(default=7, description="Minimum samples required for valid benchmark")


class BenchmarkConfig(BaseModel):
    """Complete benchmark configuration."""

    timing: TimingConfig = Field(default_factory=TimingConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    increments: IncrementsConfig = Field(default_factory=IncrementsConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)

    def validate_benchmark_params(self) -> None:
        """Validate that benchmark parameters are sensible."""
        total_samples = self.timing.benchmark_time // self.timing.sample_interval
        if total_samples < self.analysis.min_samples:
            raise ValueError(
                f"Benchmark time too short: {total_samples} samples < {self.analysis.min_samples} minimum. "
                "Increase benchmark_time or decrease sample_interval."
            )

        min_required_samples = (self.analysis.trim_outliers * 2) + 1
        if total_samples < min_required_samples:
            raise ValueError(
                f"Not enough samples ({total_samples}) after trimming {self.analysis.trim_outliers} "
                f"outliers from each end. Need at least {min_required_samples}."
            )


def load_config(config_path: Optional[Path] = None) -> BenchmarkConfig:
    """Load configuration from JSON file or return defaults.

    Args:
        config_path: Path to config.json. If None, looks in current directory
                    and package directory.

    Returns:
        BenchmarkConfig with loaded or default values.
    """
    search_paths = []

    if config_path:
        search_paths.append(config_path)
    else:
        # Check current directory first
        search_paths.append(Path.cwd() / "config.json")
        # Then check package directory
        search_paths.append(Path(__file__).parent.parent / "config.json")

    for path in search_paths:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return BenchmarkConfig(**data)
            except (json.JSONDecodeError, ValueError) as e:
                raise ValueError(f"Invalid config file {path}: {e}")

    # Return defaults if no config file found
    return BenchmarkConfig()


def save_config(config: BenchmarkConfig, config_path: Path) -> None:
    """Save configuration to JSON file.

    Args:
        config: Configuration to save.
        config_path: Path to write config.json.
    """
    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
