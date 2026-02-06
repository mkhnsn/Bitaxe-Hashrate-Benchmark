"""FastAPI web application for Bitaxe Benchmark."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..benchmark.core import BenchmarkRunner
from ..config import BenchmarkConfig, load_config, save_config
from ..models import (
    BenchmarkComplete,
    BenchmarkRequest,
    BenchmarkState,
    BenchmarkStatus,
    IterationResult,
    SetValuesRequest,
)
from .websocket import ConnectionManager, create_websocket_callbacks

# Paths - use env vars if set (for Docker), otherwise use local directories
PACKAGE_DIR = Path(__file__).parent.parent.parent
STATIC_DIR = Path(__file__).parent / "static"
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", PACKAGE_DIR / "results"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", PACKAGE_DIR))
CONFIG_PATH = CONFIG_DIR / "config.json"


def _load_or_create_config() -> BenchmarkConfig:
    """Load config from file, or create default config file if it doesn't exist."""
    if CONFIG_PATH.exists():
        return load_config(CONFIG_PATH)

    # Config file doesn't exist - create it with defaults
    default_config = BenchmarkConfig()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    save_config(default_config, CONFIG_PATH)
    return default_config


# Global state
app = FastAPI(
    title="Bitaxe Hashrate Benchmark",
    description="Web UI for benchmarking Bitaxe miners",
    version="2.0.0",
)

manager = ConnectionManager()
config: BenchmarkConfig = _load_or_create_config()
runner: Optional[BenchmarkRunner] = None
current_task: Optional[asyncio.Task] = None
last_result: Optional[BenchmarkComplete] = None
current_bitaxe_ip: Optional[str] = None
summary_start_time: Optional[datetime] = None

SUMMARY_FILENAME = "benchmark_summary.json"


def _build_summary_data(results: list[IterationResult], bitaxe_ip: str, state: str) -> dict:
    """Build summary data dict from results list."""
    data: dict = {
        "bitaxe_ip": bitaxe_ip,
        "started_at": summary_start_time.isoformat() if summary_start_time else datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "state": state,
        "iterations_completed": len(results),
        "all_results": [r.model_dump() if isinstance(r, IterationResult) else r for r in results],
        "top_performers": [],
        "most_efficient": [],
    }

    if results:
        parsed = [r if isinstance(r, IterationResult) else IterationResult(**r) for r in results]
        valid = [r for r in parsed if r.error_reason is None]

        if valid:
            by_hashrate = sorted(valid, key=lambda x: x.average_hashrate, reverse=True)[:5]
            for i, r in enumerate(by_hashrate, 1):
                data["top_performers"].append({"rank": i, **r.model_dump()})

            by_efficiency = sorted(valid, key=lambda x: x.efficiency_jth)[:5]
            for i, r in enumerate(by_efficiency, 1):
                data["most_efficient"].append({"rank": i, **r.model_dump()})

    return data


def save_summary(state: str = "running") -> Optional[Path]:
    """Save/update the running summary file. Called after each iteration."""
    r = runner
    if r is None or not current_bitaxe_ip:
        return None

    results = r.results
    if not results:
        return None

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / SUMMARY_FILENAME

    data = _build_summary_data(results, current_bitaxe_ip, state)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return filepath


def save_final_results(results: BenchmarkComplete, bitaxe_ip: str) -> Optional[Path]:
    """Save final timestamped results file on benchmark completion."""
    if not results.all_results:
        return None

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"bitaxe_benchmark_results_{bitaxe_ip}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    data = _build_summary_data(results.all_results, bitaxe_ip, "completed")
    if results.applied_settings:
        data["applied_settings"] = results.applied_settings
    data["total_duration_seconds"] = results.total_duration_seconds

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return filepath


def get_runner() -> BenchmarkRunner:
    """Get or create the benchmark runner with WebSocket callbacks."""
    global runner
    if runner is None:
        loop = asyncio.get_event_loop()
        callbacks = create_websocket_callbacks(manager, loop, on_iteration_side_effect=_on_iteration_save)
        runner = BenchmarkRunner(config=config, callbacks=callbacks)
    return runner


def _on_iteration_save() -> None:
    """Side-effect called after each iteration to save summary."""
    save_summary("running")


# --- Config endpoints ---


@app.get("/api/config")
async def get_config() -> dict:
    """Get the current configuration."""
    return config.model_dump()


@app.put("/api/config")
async def update_config(new_config: BenchmarkConfig) -> dict:
    """Update the configuration."""
    global config, runner
    try:
        new_config.validate_benchmark_params()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = new_config
    runner = None  # Force recreation with new config
    save_config(config, CONFIG_PATH)
    return {"status": "ok", "config": config.model_dump()}


@app.patch("/api/config")
async def patch_config(updates: dict) -> dict:
    """Partially update the configuration."""
    global config, runner

    current = config.model_dump()

    # Merge updates recursively
    def merge(base: dict, update: dict) -> dict:
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                merge(base[key], value)
            else:
                base[key] = value
        return base

    merged = merge(current, updates)

    try:
        new_config = BenchmarkConfig(**merged)
        new_config.validate_benchmark_params()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = new_config
    runner = None
    save_config(config, CONFIG_PATH)
    return {"status": "ok", "config": config.model_dump()}


# --- Benchmark endpoints ---


@app.post("/api/benchmark/start")
async def start_benchmark(request: BenchmarkRequest) -> dict:
    """Start a new benchmark."""
    global current_task, last_result, current_bitaxe_ip, summary_start_time

    r = get_runner()

    if current_task and not current_task.done():
        raise HTTPException(status_code=409, detail="Benchmark already running")

    current_bitaxe_ip = request.bitaxe_ip
    summary_start_time = datetime.now()

    async def run_benchmark():
        global last_result
        last_result = await r.run(
            bitaxe_ip=request.bitaxe_ip,
            initial_voltage=request.initial_voltage,
            initial_frequency=request.initial_frequency,
            max_temp_override=request.max_temp,
            mode=request.mode,
            max_voltage=request.max_voltage,
            max_frequency=request.max_frequency,
        )
        # Save final timestamped results file
        if last_result and last_result.all_results:
            save_final_results(last_result, request.bitaxe_ip)
        # Update summary with final state
        save_summary("completed" if last_result and last_result.all_results else "error")

    current_task = asyncio.create_task(run_benchmark())

    return {
        "status": "started",
        "bitaxe_ip": request.bitaxe_ip,
        "initial_voltage": request.initial_voltage,
        "initial_frequency": request.initial_frequency,
        "mode": request.mode.value,
        "max_voltage": request.max_voltage,
        "max_frequency": request.max_frequency,
    }


@app.post("/api/benchmark/stop")
async def stop_benchmark() -> dict:
    """Request the running benchmark to stop."""
    r = get_runner()

    if not current_task or current_task.done():
        # Allow stop on paused benchmarks
        if r.state != BenchmarkState.PAUSED:
            raise HTTPException(status_code=400, detail="No benchmark running")

    r.request_stop()
    save_summary("stopped")
    return {"status": "stop_requested"}


@app.post("/api/benchmark/pause")
async def pause_benchmark() -> dict:
    """Request the running benchmark to pause after current iteration."""
    r = get_runner()

    if r.state not in (BenchmarkState.RUNNING, BenchmarkState.STABILIZING):
        raise HTTPException(status_code=400, detail="Benchmark not running")

    r.request_pause()
    save_summary("paused")
    return {"status": "pause_requested"}


@app.post("/api/benchmark/resume")
async def resume_benchmark() -> dict:
    """Resume a paused benchmark."""
    r = get_runner()

    if r.state != BenchmarkState.PAUSED:
        raise HTTPException(status_code=400, detail="Benchmark not paused")

    r.resume()
    return {"status": "resumed"}


@app.post("/api/benchmark/reset")
async def reset_benchmark() -> dict:
    """Reset the benchmark runner to idle state."""
    global current_task, last_result

    r = get_runner()

    # Stop if running
    if current_task and not current_task.done():
        r.request_stop()
        # Wait briefly for task to stop
        try:
            await asyncio.wait_for(current_task, timeout=5.0)
        except asyncio.TimeoutError:
            pass

    r.reset()
    current_task = None
    last_result = None

    return {"status": "reset"}


@app.get("/api/benchmark/status")
async def get_benchmark_status() -> dict:
    """Get current benchmark status."""
    r = get_runner()

    task_active = current_task is not None and not current_task.done()
    # Use runner state - it knows if it's paused, running, etc.
    state = r.state

    # A task can be "done" but we're paused waiting for resume
    is_running = task_active or state == BenchmarkState.PAUSED

    return {
        "state": state.value,
        "is_running": is_running,
        "is_paused": r.is_paused,
        "can_resume": r.can_resume,
        "iterations_completed": len(r.results),
        "connections": manager.connection_count,
    }


@app.post("/api/set-values")
async def set_values(request: SetValuesRequest) -> dict:
    """Apply specific voltage/frequency values without benchmarking."""
    r = get_runner()

    if current_task and not current_task.done():
        raise HTTPException(status_code=409, detail="Benchmark running, cannot set values")

    # Validate values
    if request.voltage < config.safety.min_allowed_voltage:
        raise HTTPException(
            status_code=400,
            detail=f"Voltage {request.voltage}mV below minimum {config.safety.min_allowed_voltage}mV",
        )
    if request.voltage > config.safety.max_allowed_voltage:
        raise HTTPException(
            status_code=400,
            detail=f"Voltage {request.voltage}mV exceeds maximum {config.safety.max_allowed_voltage}mV",
        )
    if request.frequency < config.safety.min_allowed_frequency:
        raise HTTPException(
            status_code=400,
            detail=f"Frequency {request.frequency}MHz below minimum {config.safety.min_allowed_frequency}MHz",
        )
    if request.frequency > config.safety.max_allowed_frequency:
        raise HTTPException(
            status_code=400,
            detail=f"Frequency {request.frequency}MHz exceeds maximum {config.safety.max_allowed_frequency}MHz",
        )

    success = await r.set_values(request.bitaxe_ip, request.voltage, request.frequency)

    if success:
        return {"status": "ok", "voltage": request.voltage, "frequency": request.frequency}
    else:
        raise HTTPException(status_code=500, detail="Failed to apply settings")


# --- Results endpoints ---


@app.get("/api/results")
async def list_results() -> list[dict]:
    """List available result files."""
    if not RESULTS_DIR.exists():
        return []

    results = []
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            stat = f.stat()
            results.append({
                "filename": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        except OSError:
            continue

    return results


@app.get("/api/results/latest")
async def get_latest_result() -> dict:
    """Get the most recent benchmark result."""
    if last_result:
        return last_result.model_dump()

    if not RESULTS_DIR.exists():
        raise HTTPException(status_code=404, detail="No results available")

    files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No results available")

    try:
        with open(files[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")


@app.get("/api/results/export/summary")
async def export_summary():
    """Download the current summary file."""
    filepath = RESULTS_DIR / SUMMARY_FILENAME
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="No summary available")

    return FileResponse(
        filepath,
        media_type="application/json",
        filename=SUMMARY_FILENAME,
    )


@app.get("/api/results/export/current")
async def export_current() -> dict:
    """Export the current in-memory results (even if not yet saved)."""
    r = get_runner()
    results = r.results
    ip = current_bitaxe_ip or "unknown"

    state_str = r.state.value
    data = _build_summary_data(results, ip, state_str)
    if summary_start_time:
        data["started_at"] = summary_start_time.isoformat()

    return data


@app.post("/api/results/import")
async def import_results(file: UploadFile) -> dict:
    """Import a previous results file and load into the UI."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a JSON file")

    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")

    # Validate it has the expected structure
    if "all_results" not in data or not isinstance(data["all_results"], list):
        raise HTTPException(status_code=400, detail="File must contain 'all_results' array")

    # Validate each result can be parsed
    try:
        results = [IterationResult(**r) for r in data["all_results"]]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid result data: {e}")

    return {
        "status": "ok",
        "results": [r.model_dump() for r in results],
        "bitaxe_ip": data.get("bitaxe_ip"),
        "state": data.get("state"),
        "iterations_completed": len(results),
    }


@app.get("/api/results/{filename}")
async def get_result(filename: str) -> dict:
    """Get a specific result file."""
    filepath = RESULTS_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Result not found")

    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")


# --- WebSocket endpoint ---


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)

    # Send current status on connect — use actual runner state so refreshed
    # clients see running/paused/completed rather than always idle
    r = get_runner()
    task_active = current_task is not None and not current_task.done()
    effective_state = r._state if (task_active or r._state != BenchmarkState.IDLE) else BenchmarkState.IDLE
    await manager.send_personal(
        websocket,
        BenchmarkStatus(
            state=effective_state,
            iterations_completed=len(r._results),
            message="Connected",
        ),
    )

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


# --- Static files ---


# Mount static files if directory exists (built React app)
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        """Serve the React app."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve static files or fall back to index.html for SPA routing."""
        file_path = STATIC_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
