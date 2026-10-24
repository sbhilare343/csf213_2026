from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from .errors import ConfigurationError

@dataclass(frozen=True)
class AppConfig:
    path: Path
    root: Path
    raw: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        if not isinstance(value, dict):
            raise ConfigurationError(f"Configuration section {name!r} must be a mapping.")
        return value

    def path_value(self, section: str, key: str) -> Path | None:
        value = self.section(section).get(key)
        if value is None or str(value).strip() == "":
            return None
        p = Path(str(value)).expanduser()
        return (p if p.is_absolute() else self.root / p).resolve()


def load_config(path: str | Path) -> AppConfig:
    cfg_path = Path(path).expanduser().resolve()
    if not cfg_path.is_file():
        raise ConfigurationError(f"Settings file not found: {cfg_path}")
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {cfg_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("Settings root must be a YAML mapping.")
    root = cfg_path.parent.parent if cfg_path.parent.name == "config" else cfg_path.parent
    return AppConfig(cfg_path, root.resolve(), raw)


def validate_settings(cfg: AppConfig) -> list[str]:
    errors: list[str] = []
    for key in ("rubric_xlsx", "rubric_pdf", "attendance_xlsx", "submissions_dir", "output_dir"):
        if cfg.path_value("paths", key) is None:
            errors.append(f"paths.{key} must be configured.")
    mode = cfg.section("execution").get("sandbox", "required")
    if mode not in {"required", "unsafe"}:
        errors.append("execution.sandbox must be 'required' or 'unsafe'.")
    if cfg.section("submissions").get("layout", "directory") != "directory":
        errors.append("submissions.layout currently supports only 'directory'.")
    source_mode = cfg.section("harness").get("source_mode", "auto")
    if source_mode not in {"auto", "headers", "monolithic"}:
        errors.append("harness.source_mode must be auto, headers, or monolithic.")
    for section, key, minimum in [
        ("compiler", "compile_timeout_seconds", 1), ("compiler", "compile_cpu_seconds", 1),
        ("compiler", "memory_mb", 128), ("execution", "worker_reserve_cores", 0),
        ("execution", "cpu_seconds", 1), ("execution", "wall_timeout_seconds", 1),
        ("execution", "memory_mb", 32), ("execution", "tmpfs_mb", 16),
        ("execution", "max_output_bytes", 1024),
    ]:
        value = cfg.section(section).get(key, minimum)
        try:
            if float(value) < minimum:
                errors.append(f"{section}.{key} must be >= {minimum}.")
        except (TypeError, ValueError):
            errors.append(f"{section}.{key} must be numeric.")
    policies = cfg.section("policies")
    if policies.get("compile_failure", "zero") not in {"zero", "hold"}:
        errors.append("policies.compile_failure must be zero or hold.")
    return errors
