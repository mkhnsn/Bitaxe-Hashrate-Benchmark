"""WebSocket message types and data models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BenchmarkMode(str, Enum):
    """Benchmark sweep modes."""

    FULL_SWEEP = "full_sweep"
    QUICK = "quick"


class BenchmarkState(str, Enum):
    """Possible benchmark states."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    STABILIZING = "stabilizing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


class MessageType(str, Enum):
    """WebSocket message types."""

    SAMPLE_PROGRESS = "sample_progress"
    ITERATION_COMPLETE = "iteration_complete"
    BENCHMARK_STATUS = "benchmark_status"
    BENCHMARK_COMPLETE = "benchmark_complete"
    ERROR = "error"
    LOG = "log"


class SampleData(BaseModel):
    """Data from a single sample measurement."""

    hashrate: float = Field(description="Current hashrate in GH/s")
    temperature: float = Field(description="Chip temperature in °C")
    vr_temperature: Optional[float] = Field(default=None, description="VR temperature in °C")
    power: float = Field(description="Power consumption in W")
    input_voltage: float = Field(description="Input voltage in mV")
    fan_speed: Optional[float] = Field(default=None, description="Fan speed percentage")


class SampleProgress(BaseModel):
    """Progress update for a single sample during benchmark iteration."""

    type: MessageType = MessageType.SAMPLE_PROGRESS
    sample_number: int = Field(description="Current sample number (1-indexed)")
    total_samples: int = Field(description="Total samples in this iteration")
    progress_percent: float = Field(description="Progress percentage (0-100)")
    core_voltage: int = Field(description="Current core voltage in mV")
    frequency: int = Field(description="Current frequency in MHz")
    sample: SampleData = Field(description="Sample measurement data")
    running_stddev: float = Field(description="Running standard deviation of hashrate")
    timestamp: datetime = Field(default_factory=datetime.now)


class IterationResult(BaseModel):
    """Results from a completed benchmark iteration."""

    core_voltage: int = Field(description="Core voltage tested (mV)")
    frequency: int = Field(description="Frequency tested (MHz)")
    average_hashrate: float = Field(description="Average hashrate (GH/s)")
    hashrate_stddev: float = Field(description="Hashrate standard deviation")
    average_temperature: float = Field(description="Average chip temperature (°C)")
    average_vr_temperature: Optional[float] = Field(default=None, description="Average VR temperature (°C)")
    average_power: float = Field(description="Average power consumption (W)")
    average_fan_speed: Optional[float] = Field(default=None, description="Average fan speed (%)")
    efficiency_jth: float = Field(description="Efficiency in J/TH")
    hashrate_within_tolerance: bool = Field(description="Whether hashrate met expected threshold")
    error_reason: Optional[str] = Field(default=None, description="Error if iteration failed")


class IterationComplete(BaseModel):
    """Message sent when a benchmark iteration completes."""

    type: MessageType = MessageType.ITERATION_COMPLETE
    result: IterationResult = Field(description="Results from the iteration")
    iteration_number: int = Field(description="Which iteration this was")
    next_voltage: Optional[int] = Field(default=None, description="Next voltage to test")
    next_frequency: Optional[int] = Field(default=None, description="Next frequency to test")
    timestamp: datetime = Field(default_factory=datetime.now)


class BenchmarkStatus(BaseModel):
    """Current benchmark status update."""

    type: MessageType = MessageType.BENCHMARK_STATUS
    state: BenchmarkState = Field(description="Current benchmark state")
    current_voltage: Optional[int] = Field(default=None, description="Current voltage being tested")
    current_frequency: Optional[int] = Field(default=None, description="Current frequency being tested")
    iterations_completed: int = Field(default=0, description="Number of completed iterations")
    current_voltage_step: Optional[int] = Field(default=None, description="Current voltage step (1-indexed)")
    total_voltage_steps: Optional[int] = Field(default=None, description="Total number of voltage steps")
    message: Optional[str] = Field(default=None, description="Status message")
    timestamp: datetime = Field(default_factory=datetime.now)


class RefineRange(BaseModel):
    """Suggested range for a refinement sweep after quick mode."""

    voltage_min: int = Field(description="Minimum voltage for refine sweep (mV)")
    voltage_max: int = Field(description="Maximum voltage for refine sweep (mV)")
    frequency_min: int = Field(description="Minimum frequency for refine sweep (MHz)")
    frequency_max: int = Field(description="Maximum frequency for refine sweep (MHz)")


class BenchmarkComplete(BaseModel):
    """Message sent when entire benchmark completes."""

    type: MessageType = MessageType.BENCHMARK_COMPLETE
    all_results: list[IterationResult] = Field(description="All iteration results")
    best_hashrate: Optional[IterationResult] = Field(default=None, description="Best hashrate result")
    most_efficient: Optional[IterationResult] = Field(default=None, description="Most efficient result")
    applied_settings: Optional[dict] = Field(default=None, description="Settings applied to device")
    refine_range: Optional[RefineRange] = Field(default=None, description="Suggested refine range (quick mode)")
    total_duration_seconds: float = Field(description="Total benchmark duration")
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorMessage(BaseModel):
    """Error message."""

    type: MessageType = MessageType.ERROR
    error: str = Field(description="Error description")
    details: Optional[str] = Field(default=None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now)


class LogMessage(BaseModel):
    """Log message for real-time output."""

    type: MessageType = MessageType.LOG
    level: str = Field(description="Log level: info, warning, error")
    message: str = Field(description="Log message text")
    timestamp: datetime = Field(default_factory=datetime.now)


class DeviceInfo(BaseModel):
    """Information about the Bitaxe device."""

    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    small_core_count: int
    asic_count: int = 1
    default_voltage: int
    default_frequency: int
    firmware_version: Optional[str] = None


class BenchmarkRequest(BaseModel):
    """Request to start a benchmark."""

    bitaxe_ip: str = Field(description="IP address of Bitaxe device")
    initial_voltage: Optional[int] = Field(default=None, description="Starting voltage (mV)")
    initial_frequency: Optional[int] = Field(default=None, description="Starting frequency (MHz)")
    max_temp: Optional[int] = Field(default=None, description="Override max temperature")
    mode: BenchmarkMode = Field(default=BenchmarkMode.FULL_SWEEP, description="Sweep mode")
    max_voltage: Optional[int] = Field(default=None, description="Maximum voltage for sweep (mV)")
    max_frequency: Optional[int] = Field(default=None, description="Maximum frequency for sweep (MHz)")


class SetValuesRequest(BaseModel):
    """Request to set specific values without benchmarking."""

    bitaxe_ip: str = Field(description="IP address of Bitaxe device")
    voltage: int = Field(description="Core voltage (mV)")
    frequency: int = Field(description="Frequency (MHz)")
