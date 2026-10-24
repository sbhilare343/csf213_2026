from __future__ import annotations
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .sandbox import build_command

@dataclass
class ProcessOutcome:
    status: str
    return_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    message: str = ""


def run_bounded(command: list[str], workspace: Path, config: Any, *, phase: str,
                readonly: bool = False, stdin_text: str | None = None) -> ProcessOutcome:
    ex = config.section("execution")
    timeout = float(config.section("compiler").get("compile_timeout_seconds", 60)) if phase == "compile" else float(ex.get("wall_timeout_seconds", 4))
    output_cap = max(1024, int(ex.get("max_output_bytes", 1_048_576)))
    try:
        wrapped = build_command(command, workspace, config, phase=phase, readonly=readonly)
    except Exception as exc:
        return ProcessOutcome("INFRASTRUCTURE_ERROR", None, 0.0, "", "", str(exc))
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "TMPDIR": "/tmp", "LC_ALL": "C", "LANG": "C"}
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            wrapped, cwd=None if config.section("execution").get("sandbox", "required") == "required" else str(workspace),
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, env=env,
        )
    except OSError as exc:
        return ProcessOutcome("INFRASTRUCTURE_ERROR", None, time.monotonic() - started, "", "", f"Could not start process: {exc}")

    out = bytearray(); err = bytearray(); combined = 0
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    for stream, bucket in ((process.stdout, out), (process.stderr, err)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, bucket)
    if stdin_text is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin_text.encode("utf-8")); process.stdin.close()
        except BrokenPipeError:
            pass
    status = "OK"; message = ""
    deadline = started + timeout
    while selector.get_map() or process.poll() is None:
        now = time.monotonic()
        # The parent process may exit while a forked descendant keeps stdout/stderr
        # open. Enforce the wall-clock limit until every pipe reaches EOF, not merely
        # until the direct child exits.
        if now >= deadline and (process.poll() is None or selector.get_map()):
            status = "TIMEOUT"; message = f"Exceeded wall-clock timeout of {timeout:g}s."
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            break
        events = selector.select(timeout=min(0.05, max(0.0, deadline - now)))
        for key, _ in events:
            stream = key.fileobj; bucket = key.data
            try: chunk = os.read(stream.fileno(), 65536)
            except BlockingIOError: continue
            if not chunk:
                selector.unregister(stream); continue
            remaining = output_cap - combined
            if len(chunk) > remaining:
                if remaining > 0:
                    bucket.extend(chunk[:remaining])
                combined = output_cap
                status = "OUTPUT_LIMIT"; message = f"Combined stdout/stderr exceeded {output_cap} bytes."
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                break
            bucket.extend(chunk); combined += len(chunk)
        if status == "OUTPUT_LIMIT": break
        if process.poll() is not None and not selector.get_map(): break
    if process.poll() is None:
        try: process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
    # Collect any output already buffered after process termination, without waiting indefinitely.
    for stream, bucket in ((process.stdout, out), (process.stderr, err)):
        try:
            while combined < output_cap:
                chunk = os.read(stream.fileno(), min(65536, output_cap - combined))
                if not chunk: break
                bucket.extend(chunk); combined += len(chunk)
        except (OSError, BlockingIOError):
            pass
    selector.close()
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    elapsed = time.monotonic() - started
    stdout = bytes(out).decode("utf-8", "replace")
    stderr = bytes(err).decode("utf-8", "replace")
    if status == "OK":
        status = "OK" if process.returncode == 0 else "NONZERO_EXIT"
    return ProcessOutcome(status, process.returncode, elapsed, stdout, stderr, message)
