"""
IMS · contract versions and threshold config loading.

Three version stamps travel with every generated program ·

  GENERATOR_VERSION · the code that built the plan. Bump on any change that
                      can alter a printed prescription.
  CONTRACT_VERSION  · the shape of the payload Coach OS sends in. Bump the
                      major on any breaking field change. The server rejects
                      a payload whose declared major does not match.
  PROTOCOL_VERSION  · the IMS training protocol the plan expresses (block
                      structure, week intents, progression philosophy).

Thresholds live in config/objective_thresholds.json. Nothing in the generator
may hard-code a cutoff.
"""

import json
import threading
from pathlib import Path

GENERATOR_VERSION = "v2.0.0"
CONTRACT_VERSION = "2.0.0"
PROTOCOL_VERSION = "ims-block-1.2"

# Payload contract majors this build will accept.
ACCEPTED_CONTRACT_MAJORS = {"1", "2"}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "objective_thresholds.json"

_config_cache = {}
_config_lock = threading.Lock()


class ConfigError(RuntimeError):
    """Raised when the threshold config is missing or unreadable."""


def load_thresholds(path=None, force_reload: bool = False) -> dict:
    """Load and cache config/objective_thresholds.json.

    Fails loudly. A missing or malformed threshold config is a deployment
    error, not something to silently paper over with inline defaults · the
    whole point of the file is that the numbers are visible and tunable.
    """
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    key = str(p)
    if not force_reload:
        cached = _config_cache.get(key)
        if cached is not None:
            return cached
    with _config_lock:
        if not p.exists():
            raise ConfigError(f"Threshold config not found at {p}")
        try:
            data = json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001 · surface the real reason
            raise ConfigError(f"Threshold config at {p} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or "config_version" not in data:
            raise ConfigError(f"Threshold config at {p} is missing config_version")
        _config_cache[key] = data
        return data


def version_stamp(config: dict = None) -> dict:
    """The block of versions stamped onto every program and PDF."""
    cfg = config or {}
    return {
        "generator_version": GENERATOR_VERSION,
        "contract_version": CONTRACT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "threshold_config_version": cfg.get("config_version"),
    }


def contract_major(version: str) -> str:
    return str(version or "").split(".")[0].strip()
