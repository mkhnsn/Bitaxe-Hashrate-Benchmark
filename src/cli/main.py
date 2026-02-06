"""CLI interface using Typer."""

import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

# Default output directory - use RESULTS_DIR env var if set (for Docker)
DEFAULT_OUTPUT_DIR = Path(os.environ.get("RESULTS_DIR", "."))

from ..benchmark.core import BenchmarkCallbacks, BenchmarkRunner
from ..config import BenchmarkConfig, load_config
from ..models import (
    BenchmarkComplete,
    BenchmarkMode,
    BenchmarkStatus,
    ErrorMessage,
    IterationComplete,
    LogMessage,
    SampleProgress,
)

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# Enable ANSI on Windows
try:
    import colorama
    colorama.init()
except ImportError:
    pass

app = typer.Typer(
    name="bitaxe-benchmark",
    help="Bitaxe Hashrate Benchmark Tool",
    add_completion=False,
)


def create_cli_callbacks() -> BenchmarkCallbacks:
    """Create callbacks that print to the console."""

    def on_sample(progress: SampleProgress) -> None:
        s = progress.sample
        status = (
            f"[{progress.sample_number:2d}/{progress.total_samples:2d}] "
            f"{progress.progress_percent:5.1f}% | "
            f"CV: {progress.core_voltage:4d}mV | "
            f"F: {progress.frequency:4d}MHz | "
            f"H: {int(s.hashrate):4d} GH/s | "
            f"SD: {progress.running_stddev:3.0f} GH/s | "
            f"IV: {s.input_voltage:4d}mV | "
            f"T: {int(s.temperature):2d}°C"
        )
        if s.vr_temperature is not None and s.vr_temperature > 0:
            status += f" | VR: {int(s.vr_temperature):2d}°C"
        if s.power is not None:
            status += f" | P: {int(s.power):2d} W"
        if s.fan_speed is not None:
            status += f" | FAN: {int(s.fan_speed):2d}%"
        print(status + RESET)

    def on_iteration_complete(iteration: IterationComplete) -> None:
        r = iteration.result
        print(GREEN + f"\nIteration {iteration.iteration_number} complete:" + RESET)
        print(GREEN + f"  Average Hashrate: {r.average_hashrate:.2f} GH/s" + RESET)
        print(GREEN + f"  Hashrate Std Dev: {r.hashrate_stddev:.2f} GH/s" + RESET)
        print(GREEN + f"  Average Temperature: {r.average_temperature:.2f}°C" + RESET)
        if r.average_vr_temperature is not None:
            print(GREEN + f"  Average VR Temp: {r.average_vr_temperature:.2f}°C" + RESET)
        print(GREEN + f"  Efficiency: {r.efficiency_jth:.2f} J/TH" + RESET)
        print()

    def on_status_change(status: BenchmarkStatus) -> None:
        if status.message:
            print(YELLOW + status.message + RESET)

    def on_complete(complete: BenchmarkComplete) -> None:
        if complete.best_hashrate:
            b = complete.best_hashrate
            print(GREEN + "\n--- Best Hashrate ---" + RESET)
            print(GREEN + f"  {b.core_voltage}mV / {b.frequency}MHz" + RESET)
            print(GREEN + f"  {b.average_hashrate:.2f} GH/s @ {b.efficiency_jth:.2f} J/TH" + RESET)

        if complete.most_efficient:
            e = complete.most_efficient
            print(GREEN + "\n--- Most Efficient ---" + RESET)
            print(GREEN + f"  {e.core_voltage}mV / {e.frequency}MHz" + RESET)
            print(GREEN + f"  {e.average_hashrate:.2f} GH/s @ {e.efficiency_jth:.2f} J/TH" + RESET)

        print(GREEN + f"\nTotal duration: {complete.total_duration_seconds:.1f}s" + RESET)

    def on_error(error: ErrorMessage) -> None:
        print(RED + f"Error: {error.error}" + RESET)
        if error.details:
            print(RED + f"  {error.details}" + RESET)

    def on_log(log: LogMessage) -> None:
        if log.level == "error":
            print(RED + log.message + RESET)
        elif log.level == "warning":
            print(YELLOW + log.message + RESET)
        else:
            print(GREEN + log.message + RESET)

    return BenchmarkCallbacks(
        on_sample=on_sample,
        on_iteration_complete=on_iteration_complete,
        on_status_change=on_status_change,
        on_complete=on_complete,
        on_error=on_error,
        on_log=on_log,
    )


def save_results(results: BenchmarkComplete, output_dir: Path, bitaxe_ip: str) -> None:
    """Save benchmark results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"bitaxe_benchmark_results_{bitaxe_ip}_{timestamp}.json"
    filepath = output_dir / filename

    # Format results similar to original
    data = {
        "all_results": [r.model_dump() for r in results.all_results],
        "top_performers": [],
        "most_efficient": [],
    }

    if results.all_results:
        # Top 5 by hashrate
        by_hashrate = sorted(results.all_results, key=lambda x: x.average_hashrate, reverse=True)[:5]
        for i, r in enumerate(by_hashrate, 1):
            data["top_performers"].append({"rank": i, **r.model_dump()})

        # Top 5 by efficiency
        by_efficiency = sorted(results.all_results, key=lambda x: x.efficiency_jth)[:5]
        for i, r in enumerate(by_efficiency, 1):
            data["most_efficient"].append({"rank": i, **r.model_dump()})

    with open(filepath, "w") as f:
        json.dump(data, f, indent=4, default=str)

    print(GREEN + f"Results saved to {filepath}" + RESET)


@app.command()
def benchmark(
    bitaxe_ip: str = typer.Argument(..., help="IP address of your Bitaxe miner"),
    voltage: Optional[int] = typer.Option(
        None, "-v", "--voltage", help="Starting core voltage in mV"
    ),
    frequency: Optional[int] = typer.Option(
        None, "-f", "--frequency", help="Starting frequency in MHz"
    ),
    set_values: bool = typer.Option(
        False, "-s", "--set-values", help="Set values only, do not benchmark"
    ),
    max_temp: Optional[int] = typer.Option(
        None, "--max-temp", help="Maximum chip temperature in °C"
    ),
    mode: str = typer.Option(
        "full_sweep", "--mode", help="Sweep mode: full_sweep or quick (4x step sizes)"
    ),
    max_voltage: Optional[int] = typer.Option(
        None, "--max-voltage", help="Maximum voltage for sweep (mV)"
    ),
    max_frequency: Optional[int] = typer.Option(
        None, "--max-frequency", help="Maximum frequency for sweep (MHz)"
    ),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR, "-o", "--output-dir", help="Directory to save results"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to config.json"
    ),
):
    """
    Run a benchmark on your Bitaxe miner.

    Examples:

        # Full benchmark starting at 1150mV, 500MHz
        python -m src.cli.main benchmark 192.168.1.136 -v 1150 -f 500

        # Apply specific settings only
        python -m src.cli.main benchmark 192.168.1.136 --set-values -v 1150 -f 780
    """
    # Load config
    config = load_config(config_path)

    if max_temp:
        config.safety.max_temp = max_temp

    # Validate set-values mode
    if set_values:
        if voltage is None or frequency is None:
            print(RED + "Error: --set-values requires both -v/--voltage and -f/--frequency" + RESET)
            raise typer.Exit(1)

    # Create runner
    callbacks = create_cli_callbacks()
    runner = BenchmarkRunner(config=config, callbacks=callbacks)

    # Handle Ctrl+C
    def signal_handler(sig, frame):
        print(RED + "\nInterrupted by user" + RESET)
        runner.request_stop()

    signal.signal(signal.SIGINT, signal_handler)

    # Run
    if set_values:
        print(GREEN + f"\n--- Applying Settings ---" + RESET)
        print(GREEN + f"Voltage: {voltage}mV, Frequency: {frequency}MHz" + RESET)

        success = asyncio.run(runner.set_values(bitaxe_ip, voltage, frequency))

        if success:
            print(GREEN + "Settings applied successfully" + RESET)
        else:
            print(RED + "Failed to apply settings" + RESET)
            raise typer.Exit(1)
    else:
        # Print disclaimer
        print(RED + "\nDISCLAIMER:" + RESET)
        print("This tool will stress test your Bitaxe by running it at various voltages and frequencies.")
        print("While safeguards are in place, running hardware outside of standard parameters carries inherent risks.")
        print("Use this tool at your own risk. The author(s) are not responsible for any damage to your hardware.")
        print("\nNOTE: Ambient temperature significantly affects these results.\n")

        # Parse mode
        try:
            benchmark_mode = BenchmarkMode(mode)
        except ValueError:
            print(RED + f"Error: Invalid mode '{mode}'. Use 'full_sweep' or 'quick'" + RESET)
            raise typer.Exit(1)

        results = asyncio.run(
            runner.run(
                bitaxe_ip=bitaxe_ip,
                initial_voltage=voltage,
                initial_frequency=frequency,
                mode=benchmark_mode,
                max_voltage=max_voltage,
                max_frequency=max_frequency,
            )
        )

        if results.all_results:
            save_results(results, output_dir, bitaxe_ip)

            # Print summary
            print(GREEN + "\n--- Summary ---" + RESET)
            print(GREEN + f"Completed {len(results.all_results)} iterations" + RESET)

            if results.best_hashrate:
                b = results.best_hashrate
                print(GREEN + f"\nBest Hashrate: {b.core_voltage}mV / {b.frequency}MHz" + RESET)
                print(GREEN + f"  {b.average_hashrate:.2f} GH/s" + RESET)

            if results.most_efficient:
                e = results.most_efficient
                print(GREEN + f"\nMost Efficient: {e.core_voltage}mV / {e.frequency}MHz" + RESET)
                print(GREEN + f"  {e.efficiency_jth:.2f} J/TH" + RESET)

            # Print refine suggestion for quick mode
            if results.refine_range:
                rr = results.refine_range
                print(YELLOW + "\n--- Quick Mode: Refine Suggestion ---" + RESET)
                print(YELLOW + f"  Voltage range: {rr.voltage_min} - {rr.voltage_max} mV" + RESET)
                print(YELLOW + f"  Frequency range: {rr.frequency_min} - {rr.frequency_max} MHz" + RESET)
                print(YELLOW + "\nTo refine, run:" + RESET)
                print(
                    YELLOW
                    + f"  python -m src.cli.main benchmark {bitaxe_ip} "
                    f"-v {rr.voltage_min} -f {rr.frequency_min} "
                    f"--max-voltage {rr.voltage_max} --max-frequency {rr.frequency_max}"
                    + RESET
                )
        else:
            print(YELLOW + "No benchmark results collected" + RESET)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
):
    """
    Start the web UI server.

    Example:
        python -m src.cli.main serve --port 8080
    """
    import uvicorn

    print(GREEN + f"Starting Bitaxe Benchmark Web UI on http://{host}:{port}" + RESET)
    uvicorn.run(
        "src.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
