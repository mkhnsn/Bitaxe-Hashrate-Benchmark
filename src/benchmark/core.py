"""Core benchmark logic with async support."""

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from ..config import BenchmarkConfig
from ..models import (
    BenchmarkComplete,
    BenchmarkMode,
    BenchmarkState,
    BenchmarkStatus,
    DeviceInfo,
    ErrorMessage,
    IterationComplete,
    IterationResult,
    LogMessage,
    RefineRange,
    SampleData,
    SampleProgress,
)
from .bitaxe_client import BitaxeClient


@dataclass
class BenchmarkCallbacks:
    """Callbacks for benchmark events."""

    on_sample: Optional[Callable[[SampleProgress], None]] = None
    on_iteration_complete: Optional[Callable[[IterationComplete], None]] = None
    on_status_change: Optional[Callable[[BenchmarkStatus], None]] = None
    on_complete: Optional[Callable[[BenchmarkComplete], None]] = None
    on_error: Optional[Callable[[ErrorMessage], None]] = None
    on_log: Optional[Callable[[LogMessage], None]] = None


@dataclass
class BenchmarkState_:
    """Saved state for pause/resume."""

    bitaxe_ip: str
    current_voltage: int
    current_frequency: int
    initial_voltage: int
    initial_frequency: int
    iteration_num: int
    retry_upon_overheat: int
    start_time: datetime


@dataclass
class BenchmarkRunner:
    """Async benchmark runner for Bitaxe devices."""

    config: BenchmarkConfig
    callbacks: BenchmarkCallbacks = field(default_factory=BenchmarkCallbacks)

    # Control flags
    _stop_requested: bool = field(default=False, init=False)
    _pause_requested: bool = field(default=False, init=False)

    # State
    _state: BenchmarkState = field(default=BenchmarkState.IDLE, init=False)
    _results: list[IterationResult] = field(default_factory=list, init=False)
    _device_info: Optional[DeviceInfo] = field(default=None, init=False)
    _client: Optional[BitaxeClient] = field(default=None, init=False)

    # Saved state for resume
    _saved_state: Optional[BenchmarkState_] = field(default=None, init=False)

    # Async event for pause/resume
    _resume_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def __post_init__(self):
        """Initialize the resume event as set (not paused)."""
        self._resume_event.set()

    @property
    def state(self) -> BenchmarkState:
        """Get current benchmark state."""
        return self._state

    @property
    def results(self) -> list[IterationResult]:
        """Get current results."""
        return self._results.copy()

    @property
    def is_paused(self) -> bool:
        """Check if benchmark is paused."""
        return self._state == BenchmarkState.PAUSED

    @property
    def can_resume(self) -> bool:
        """Check if benchmark can be resumed."""
        return self._saved_state is not None and self._state == BenchmarkState.PAUSED

    def request_stop(self) -> None:
        """Request the benchmark to stop gracefully."""
        self._stop_requested = True
        self._pause_requested = False
        self._resume_event.set()  # Unblock if paused
        self._log("info", "Stop requested, will stop after current sample")

    def request_pause(self) -> None:
        """Request the benchmark to pause after current iteration."""
        if self._state in (BenchmarkState.RUNNING, BenchmarkState.STABILIZING):
            self._pause_requested = True
            self._log("info", "Pause requested, will pause after current iteration")

    def resume(self) -> None:
        """Resume a paused benchmark."""
        if self._state == BenchmarkState.PAUSED:
            self._pause_requested = False
            self._resume_event.set()
            self._log("info", "Resuming benchmark")

    def reset(self) -> None:
        """Reset the runner to idle state, clearing all results."""
        self._stop_requested = False
        self._pause_requested = False
        self._results = []
        self._saved_state = None
        self._device_info = None
        self._resume_event.set()
        self._set_state(BenchmarkState.IDLE, "Reset complete")

    def _set_state(
        self,
        state: BenchmarkState,
        message: Optional[str] = None,
        current_voltage_step: Optional[int] = None,
        total_voltage_steps: Optional[int] = None,
    ) -> None:
        """Update state and notify via callback."""
        self._state = state
        if self.callbacks.on_status_change:
            voltage = None
            frequency = None
            if self._saved_state:
                voltage = self._saved_state.current_voltage
                frequency = self._saved_state.current_frequency
            self.callbacks.on_status_change(
                BenchmarkStatus(
                    state=state,
                    current_voltage=voltage,
                    current_frequency=frequency,
                    iterations_completed=len(self._results),
                    current_voltage_step=current_voltage_step,
                    total_voltage_steps=total_voltage_steps,
                    message=message,
                )
            )

    def _log(self, level: str, message: str) -> None:
        """Send log message via callback."""
        if self.callbacks.on_log:
            self.callbacks.on_log(LogMessage(level=level, message=message))

    def _error(self, error: str, details: Optional[str] = None) -> None:
        """Send error via callback."""
        if self.callbacks.on_error:
            self.callbacks.on_error(ErrorMessage(error=error, details=details))

    def _running_stddev(self, n: int, s1: float, s2: float) -> float:
        """Calculate running standard deviation."""
        if n > 1:
            var = (n * s2 - s1**2) / (n * (n - 1))
            return max(var, 0.0) ** 0.5
        return 0.0

    async def _get_system_info_with_retry(self, retries: int = 3) -> Optional[dict]:
        """Fetch system info with retries."""
        for attempt in range(retries):
            info = await self._client.get_system_info()
            if info:
                return info
            self._log("warning", f"System info fetch failed, attempt {attempt + 1}/{retries}")
            await asyncio.sleep(5)
        return None

    async def _apply_settings(self, voltage: int, frequency: int, wait_for_stabilization: bool = True) -> bool:
        """Apply settings and optionally wait for stabilization.

        Returns:
            True if settings applied and system stabilized.
        """
        self._log("info", f"Applying settings: {voltage}mV, {frequency}MHz")

        if not await self._client.set_settings(voltage, frequency):
            self._log("error", "Failed to apply settings")
            return False

        await asyncio.sleep(2)

        if not await self._client.restart():
            self._log("error", "Failed to restart system")
            return False

        if not wait_for_stabilization:
            return True

        self._log("info", f"Waiting {self.config.timing.sleep_time}s for stabilization...")

        start_time = asyncio.get_event_loop().time()
        consecutive_failures = 0

        while asyncio.get_event_loop().time() - start_time < self.config.timing.sleep_time:
            if self._stop_requested:
                return False

            try:
                info = await self._client.get_system_info()
                if not info:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        self._log("error", "Failed to read system info during stabilization")
                        return False
                    await asyncio.sleep(5)
                    continue

                consecutive_failures = 0
                temp = info.get("temp")
                power = info.get("power")
                vr_temp = info.get("vrTemp")

                if temp and temp >= self.config.safety.max_temp:
                    self._log("error", f"Chip temp {temp}°C exceeded {self.config.safety.max_temp}°C during stabilization")
                    return False
                if vr_temp and vr_temp >= self.config.safety.max_vr_temp:
                    self._log("error", f"VR temp {vr_temp}°C exceeded {self.config.safety.max_vr_temp}°C during stabilization")
                    return False
                if power and power > self.config.safety.max_power:
                    self._log("error", f"Power {power}W exceeded {self.config.safety.max_power}W during stabilization")
                    return False

            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    self._log("error", f"Error during stabilization: {e}")
                    return False

            await asyncio.sleep(5)

        return True

    async def _run_iteration(self, voltage: int, frequency: int, iteration_num: int) -> Optional[IterationResult]:
        """Run a single benchmark iteration.

        Returns:
            IterationResult or None if iteration failed.
        """
        total_samples = self.config.timing.benchmark_time // self.config.timing.sample_interval
        expected_hashrate = frequency * ((self._device_info.small_core_count * self._device_info.asic_count) / 1000)

        hash_rates = []
        temperatures = []
        power_consumptions = []
        vr_temps = []
        fan_speeds = []
        s1 = 0.0
        s2 = 0.0

        self._log("info", f"Starting iteration {iteration_num}: {voltage}mV, {frequency}MHz")

        for sample_num in range(total_samples):
            if self._stop_requested:
                self._log("info", "Stop requested, ending iteration early")
                break

            info = await self._get_system_info_with_retry()
            if not info:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=0,
                    average_power=0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="SYSTEM_INFO_FAILURE",
                )

            temp = info.get("temp")
            vr_temp = info.get("vrTemp")
            input_voltage = info.get("voltage", 0)
            hash_rate = info.get("hashRate")
            power = info.get("power")
            fan_speed = info.get("fanspeed")

            # Safety checks
            if temp is None or temp < 5:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=0,
                    average_power=0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="TEMPERATURE_DATA_FAILURE" if temp is None else "TEMPERATURE_BELOW_5",
                )

            if temp >= self.config.safety.max_temp:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_power=power or 0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="CHIP_TEMP_EXCEEDED",
                )

            if vr_temp is not None and vr_temp >= self.config.safety.max_vr_temp:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_vr_temperature=vr_temp,
                    average_power=power or 0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="VR_TEMP_EXCEEDED",
                )

            if input_voltage < self.config.safety.min_input_voltage:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_power=power or 0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="INPUT_VOLTAGE_BELOW_MIN",
                )

            if input_voltage > self.config.safety.max_input_voltage:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_power=power or 0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="INPUT_VOLTAGE_ABOVE_MAX",
                )

            if hash_rate is None or power is None:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_power=0,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="HASHRATE_POWER_DATA_FAILURE",
                )

            if power > self.config.safety.max_power:
                return IterationResult(
                    core_voltage=voltage,
                    frequency=frequency,
                    average_hashrate=0,
                    hashrate_stddev=0,
                    average_temperature=temp,
                    average_power=power,
                    efficiency_jth=float("inf"),
                    hashrate_within_tolerance=False,
                    error_reason="POWER_CONSUMPTION_EXCEEDED",
                )

            # Record sample
            hash_rates.append(hash_rate)
            s1 += hash_rate
            s2 += hash_rate * hash_rate
            temperatures.append(temp)
            power_consumptions.append(power)
            if vr_temp is not None and vr_temp > 0:
                vr_temps.append(vr_temp)
            if fan_speed is not None:
                fan_speeds.append(fan_speed)

            # Send progress update
            if self.callbacks.on_sample:
                self.callbacks.on_sample(
                    SampleProgress(
                        sample_number=sample_num + 1,
                        total_samples=total_samples,
                        progress_percent=((sample_num + 1) / total_samples) * 100,
                        core_voltage=voltage,
                        frequency=frequency,
                        sample=SampleData(
                            hashrate=hash_rate,
                            temperature=temp,
                            vr_temperature=vr_temp,
                            power=power,
                            input_voltage=input_voltage,
                            fan_speed=fan_speed,
                        ),
                        running_stddev=self._running_stddev(sample_num + 1, s1, s2),
                    )
                )

            # Sleep before next sample (except last)
            if sample_num < total_samples - 1:
                await asyncio.sleep(self.config.timing.sample_interval)

        # Calculate results
        if not hash_rates or not temperatures or not power_consumptions:
            return IterationResult(
                core_voltage=voltage,
                frequency=frequency,
                average_hashrate=0,
                hashrate_stddev=0,
                average_temperature=0,
                average_power=0,
                efficiency_jth=float("inf"),
                hashrate_within_tolerance=False,
                error_reason="NO_DATA_COLLECTED",
            )

        # Trim outliers
        trim = self.config.analysis.trim_outliers
        sorted_hashrates = sorted(hash_rates)
        trimmed_hashrates = sorted_hashrates[trim:-trim] if len(sorted_hashrates) > trim * 2 else sorted_hashrates
        average_hashrate = sum(trimmed_hashrates) / len(trimmed_hashrates)
        hashrate_stddev = statistics.stdev(trimmed_hashrates) if len(trimmed_hashrates) > 1 else 0.0

        # Trim warmup from temperatures
        warmup = self.config.analysis.warmup_samples
        sorted_temps = sorted(temperatures)
        trimmed_temps = sorted_temps[warmup:] if len(sorted_temps) > warmup else sorted_temps
        average_temperature = sum(trimmed_temps) / len(trimmed_temps)

        average_vr_temp = None
        if vr_temps:
            sorted_vr_temps = sorted(vr_temps)
            trimmed_vr_temps = sorted_vr_temps[warmup:] if len(sorted_vr_temps) > warmup else sorted_vr_temps
            average_vr_temp = sum(trimmed_vr_temps) / len(trimmed_vr_temps)

        average_power = sum(power_consumptions) / len(power_consumptions)
        average_fan_speed = sum(fan_speeds) / len(fan_speeds) if fan_speeds else None

        if average_hashrate > 0:
            efficiency_jth = average_power / (average_hashrate / 1000)
        else:
            return IterationResult(
                core_voltage=voltage,
                frequency=frequency,
                average_hashrate=0,
                hashrate_stddev=0,
                average_temperature=average_temperature,
                average_power=average_power,
                efficiency_jth=float("inf"),
                hashrate_within_tolerance=False,
                error_reason="ZERO_HASHRATE",
            )

        hashrate_within_tolerance = average_hashrate >= expected_hashrate * self.config.analysis.hashrate_tolerance

        return IterationResult(
            core_voltage=voltage,
            frequency=frequency,
            average_hashrate=average_hashrate,
            hashrate_stddev=hashrate_stddev,
            average_temperature=average_temperature,
            average_vr_temperature=average_vr_temp,
            average_power=average_power,
            average_fan_speed=average_fan_speed,
            efficiency_jth=efficiency_jth,
            hashrate_within_tolerance=hashrate_within_tolerance,
            error_reason=None,
        )

    async def _check_pause(self) -> bool:
        """Check if pause was requested and wait if so.

        Returns:
            True if should continue, False if stop was requested while paused.
        """
        if self._pause_requested and not self._stop_requested:
            self._set_state(BenchmarkState.PAUSED, "Benchmark paused")
            self._resume_event.clear()
            await self._resume_event.wait()

            if self._stop_requested:
                return False

            # Restore running state
            if self._saved_state:
                self._set_state(
                    BenchmarkState.RUNNING,
                    f"Resumed at {self._saved_state.current_voltage}mV / {self._saved_state.current_frequency}MHz",
                )
        return True

    async def run(
        self,
        bitaxe_ip: str,
        initial_voltage: Optional[int] = None,
        initial_frequency: Optional[int] = None,
        max_temp_override: Optional[int] = None,
        mode: BenchmarkMode = BenchmarkMode.FULL_SWEEP,
        max_voltage: Optional[int] = None,
        max_frequency: Optional[int] = None,
    ) -> BenchmarkComplete:
        """Run the full benchmark using a two-level voltage/frequency sweep.

        Args:
            bitaxe_ip: IP address of the Bitaxe device.
            initial_voltage: Starting voltage (uses device default if None).
            initial_frequency: Starting frequency (uses device default if None).
            max_temp_override: Override max temperature from config.
            mode: Sweep mode - full_sweep or quick (4x step sizes).
            max_voltage: Maximum voltage for sweep (uses config max if None).
            max_frequency: Maximum frequency for sweep (uses config max if None).

        Returns:
            BenchmarkComplete with all results.
        """
        start_time = datetime.now()
        self._stop_requested = False
        self._pause_requested = False
        self._results = []
        self._resume_event.set()

        if max_temp_override:
            self.config.safety.max_temp = max_temp_override

        self._set_state(BenchmarkState.INITIALIZING, "Connecting to Bitaxe...")

        try:
            async with BitaxeClient(bitaxe_ip) as client:
                self._client = client

                # Fetch device info
                try:
                    self._device_info = await client.fetch_device_info()
                except ConnectionError as e:
                    self._error(str(e))
                    self._set_state(BenchmarkState.ERROR, str(e))
                    return BenchmarkComplete(
                        all_results=[],
                        total_duration_seconds=(datetime.now() - start_time).total_seconds(),
                    )

                self._log(
                    "info",
                    f"Connected to Bitaxe: {self._device_info.small_core_count * self._device_info.asic_count} cores, "
                    f"default {self._device_info.default_voltage}mV/{self._device_info.default_frequency}MHz",
                )

                # Set initial values
                initial_volt = initial_voltage or self._device_info.default_voltage
                initial_freq = initial_frequency or self._device_info.default_frequency

                # Validate starting values
                if initial_volt < self.config.safety.min_allowed_voltage:
                    raise ValueError(f"Initial voltage {initial_volt}mV below minimum {self.config.safety.min_allowed_voltage}mV")
                if initial_volt > self.config.safety.max_allowed_voltage:
                    raise ValueError(f"Initial voltage {initial_volt}mV exceeds maximum {self.config.safety.max_allowed_voltage}mV")
                if initial_freq < self.config.safety.min_allowed_frequency:
                    raise ValueError(f"Initial frequency {initial_freq}MHz below minimum {self.config.safety.min_allowed_frequency}MHz")
                if initial_freq > self.config.safety.max_allowed_frequency:
                    raise ValueError(f"Initial frequency {initial_freq}MHz exceeds maximum {self.config.safety.max_allowed_frequency}MHz")

                # Compute effective increments (quick mode uses 4x steps)
                quick = mode == BenchmarkMode.QUICK
                v_inc = self.config.increments.voltage_increment * (4 if quick else 1)
                f_inc = self.config.increments.frequency_increment * (4 if quick else 1)

                # Sweep limits (clamped to safety config)
                sweep_max_v = min(
                    max_voltage or self.config.safety.max_allowed_voltage,
                    self.config.safety.max_allowed_voltage,
                )
                sweep_max_f = min(
                    max_frequency or self.config.safety.max_allowed_frequency,
                    self.config.safety.max_allowed_frequency,
                )

                # Build voltage level list
                voltage_levels = list(range(initial_volt, sweep_max_v + 1, v_inc))
                if not voltage_levels:
                    voltage_levels = [initial_volt]
                total_voltage_steps = len(voltage_levels)

                mode_label = "Quick" if quick else "Full"
                self._log(
                    "info",
                    f"{mode_label} sweep: {total_voltage_steps} voltage levels "
                    f"({initial_volt}-{sweep_max_v}mV, step {v_inc}mV), "
                    f"freq {initial_freq}-{sweep_max_f}MHz step {f_inc}MHz",
                )

                iteration_num = 0
                abort_all = False

                # Save state for resume capability
                self._saved_state = BenchmarkState_(
                    bitaxe_ip=bitaxe_ip,
                    current_voltage=initial_volt,
                    current_frequency=initial_freq,
                    initial_voltage=initial_volt,
                    initial_frequency=initial_freq,
                    iteration_num=iteration_num,
                    retry_upon_overheat=0,
                    start_time=start_time,
                )

                # === Two-level sweep: outer = voltage, inner = frequency ===
                for v_step, voltage in enumerate(voltage_levels, 1):
                    if self._stop_requested or abort_all:
                        break

                    # Check for pause at the start of each voltage level
                    if not await self._check_pause():
                        break

                    freq = initial_freq

                    while freq <= sweep_max_f and not self._stop_requested:
                        # Check for pause at the start of each frequency step
                        if not await self._check_pause():
                            break

                        # Update saved state
                        self._saved_state.current_voltage = voltage
                        self._saved_state.current_frequency = freq
                        self._saved_state.iteration_num = iteration_num

                        self._set_state(
                            BenchmarkState.STABILIZING,
                            f"Applying {voltage}mV / {freq}MHz",
                            current_voltage_step=v_step,
                            total_voltage_steps=total_voltage_steps,
                        )

                        if not await self._apply_settings(voltage, freq):
                            # Stabilization failed — skip to next voltage
                            self._log("warning", f"Stabilization failed at {voltage}mV / {freq}MHz, moving to next voltage")
                            break
                        else:
                            self._set_state(
                                BenchmarkState.RUNNING,
                                f"Benchmarking {voltage}mV / {freq}MHz",
                                current_voltage_step=v_step,
                                total_voltage_steps=total_voltage_steps,
                            )
                            iteration_num += 1
                            result = await self._run_iteration(voltage, freq, iteration_num)

                        if result and result.error_reason is None:
                            self._results.append(result)

                            # Notify iteration complete
                            if self.callbacks.on_iteration_complete:
                                self.callbacks.on_iteration_complete(
                                    IterationComplete(
                                        result=result,
                                        iteration_number=iteration_num,
                                    )
                                )

                            if result.hashrate_within_tolerance:
                                # Good hashrate at this voltage, try higher frequency
                                freq += f_inc
                                self._log("info", f"Good hashrate, trying frequency {freq}MHz")
                            else:
                                # Hashrate out of tolerance, stop freq sweep for this voltage
                                self._log("info", f"Hashrate out of tolerance at {voltage}mV / {freq}MHz, next voltage")
                                break
                        else:
                            # Failed iteration
                            error_reason = result.error_reason if result else "UNKNOWN"

                            if error_reason == "CHIP_TEMP_EXCEEDED" and freq == initial_freq:
                                # Thermal wall at starting frequency — abort entire sweep
                                self._log("error", f"Overheated at initial frequency ({voltage}mV / {freq}MHz), aborting sweep")
                                abort_all = True
                                break

                            # Any other failure at this voltage — move to next voltage
                            self._log("warning", f"Iteration failed ({error_reason}) at {voltage}mV / {freq}MHz, next voltage")
                            break

                    if abort_all:
                        break

                # Compute refine range for quick mode
                refine_range = None
                if quick and self._results:
                    best = max(self._results, key=lambda r: r.average_hashrate)
                    refine_range = RefineRange(
                        voltage_min=max(best.core_voltage - v_inc, self.config.safety.min_allowed_voltage),
                        voltage_max=min(best.core_voltage + v_inc, self.config.safety.max_allowed_voltage),
                        frequency_min=max(best.frequency - f_inc, self.config.safety.min_allowed_frequency),
                        frequency_max=min(best.frequency + f_inc, self.config.safety.max_allowed_frequency),
                    )

                # Apply best settings
                applied_settings = None
                if self._results:
                    best = max(self._results, key=lambda r: r.average_hashrate)
                    self._log("info", f"Applying best settings: {best.core_voltage}mV / {best.frequency}MHz")
                    await self._apply_settings(best.core_voltage, best.frequency, wait_for_stabilization=False)
                    applied_settings = {"voltage": best.core_voltage, "frequency": best.frequency}
                else:
                    # Restore defaults
                    self._log("info", "No results, restoring defaults")
                    await self._apply_settings(
                        self._device_info.default_voltage,
                        self._device_info.default_frequency,
                        wait_for_stabilization=False,
                    )

                self._saved_state = None
                self._set_state(BenchmarkState.COMPLETED, "Benchmark complete")

                # Build completion message
                best_hashrate = max(self._results, key=lambda r: r.average_hashrate) if self._results else None
                most_efficient = min(self._results, key=lambda r: r.efficiency_jth) if self._results else None

                completion = BenchmarkComplete(
                    all_results=self._results,
                    best_hashrate=best_hashrate,
                    most_efficient=most_efficient,
                    applied_settings=applied_settings,
                    refine_range=refine_range,
                    total_duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

                if self.callbacks.on_complete:
                    self.callbacks.on_complete(completion)

                return completion

        except Exception as e:
            self._error(f"Benchmark failed: {e}")
            self._set_state(BenchmarkState.ERROR, str(e))
            return BenchmarkComplete(
                all_results=self._results,
                total_duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def set_values(self, bitaxe_ip: str, voltage: int, frequency: int) -> bool:
        """Apply specific values without running benchmark.

        Args:
            bitaxe_ip: IP address of Bitaxe device.
            voltage: Core voltage in mV.
            frequency: Frequency in MHz.

        Returns:
            True if settings applied successfully.
        """
        async with BitaxeClient(bitaxe_ip) as client:
            self._client = client
            self._log("info", f"Setting values: {voltage}mV, {frequency}MHz")
            return await self._apply_settings(voltage, frequency)
