"""Model Loader Service.

Provides robust, cached loading for Side-Scan Sonar detection models.
Safely handles unpacked Ultralytics checkpoint directories without modifying
original model files, caching instantiated models in memory to prevent
redundant initialization overhead.
"""

import gc
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Optional
import torch
from ultralytics import YOLO

from app.core.model_registry import (
    MODEL_REGISTRY,
    ModelDefinition,
    ModelNotFoundError,
    get_model_definition,
    resolve_model_path,
)

# Limit PyTorch CPU threads to avoid excessive memory and thread pool overhead
try:
    torch.set_num_threads(2)
except Exception:
    pass

class ModelLoadError(RuntimeError):
    """Raised when an existing model fails to load into memory."""
    pass


# Global in-memory cache holding initialized model instances
_LOADED_MODELS: Dict[str, YOLO] = {}
MAX_CACHED_MODELS = int(os.getenv("MAX_CACHED_MODELS", "1"))


def _get_cache_dir() -> Path:
    """Resolve and create a writable cache directory for packaged models."""
    env_cache = os.getenv("MODEL_CACHE_DIR")
    if env_cache:
        target = Path(env_cache).resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    default_cache = Path(__file__).resolve().parent.parent.parent / ".cache" / "packaged_models"
    try:
        default_cache.mkdir(parents=True, exist_ok=True)
        return default_cache
    except (OSError, PermissionError):
        tmp_cache = Path(tempfile.gettempdir()) / "sonarops_packaged_models"
        tmp_cache.mkdir(parents=True, exist_ok=True)
        return tmp_cache


def _ensure_packaged_pt(definition: ModelDefinition, source_path: Path) -> Path:
    """Ensure a standard PyTorch ZIP container exists for an unpacked checkpoint directory.

    Ultralytics and PyTorch require a single ZIP container (.pt) with an internal
    archive directory prefix. This function packages the unpacked directory into a
    local runtime cache without altering the source directory.
    """
    cache_dir = _get_cache_dir()
    target_pt = cache_dir / f"{definition.key}.pt"

    # Check if target already exists and is newer than source data.pkl
    source_pkl = source_path / "data.pkl"
    if not source_pkl.exists():
        raise ModelLoadError(
            f"Model directory '{source_path}' is missing essential 'data.pkl' checkpoint file."
        )

    src_mtime = source_pkl.stat().st_mtime
    if target_pt.exists() and target_pt.stat().st_mtime >= src_mtime:
        return target_pt

    # Create PyTorch zip container
    temp_pt = cache_dir / f"{definition.key}.tmp.pt"
    try:
        with zipfile.ZipFile(temp_pt, "w", compression=zipfile.ZIP_STORED) as zf:
            for root, _, files in os.walk(source_path):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(source_path).as_posix()
                    # PyTorch inline container requires top-level archive prefix
                    archive_path = f"{definition.key}/{rel_p}"
                    zf.write(full_p, archive_path)

        # Atomic rename to final target
        if target_pt.exists():
            target_pt.unlink()
        temp_pt.rename(target_pt)
    except Exception as e:
        if temp_pt.exists():
            temp_pt.unlink()
        raise ModelLoadError(
            f"Failed to package unpacked model '{definition.name}' from '{source_path}': {e}"
        ) from e

    return target_pt


def prepackage_all_models() -> None:
    """Pre-package all registered models into .pt containers ahead of time.

    Called during application startup to avoid on-the-fly zip packaging latency
    during live HTTP requests.
    """
    for definition in MODEL_REGISTRY.values():
        try:
            source_path = resolve_model_path(definition)
            if source_path.exists():
                _ensure_packaged_pt(definition, source_path)
        except Exception:
            pass


def load_model(name_or_key: str, force_reload: bool = False) -> YOLO:
    """Load a model by name or key, returning a cached instance if available.

    Args:
        name_or_key: Registered model key or human-readable name.
        force_reload: If True, bypasses memory cache and reloads from disk.

    Returns:
        Ultralytics YOLO model instance ready for inference.

    Raises:
        ModelNotFoundError: If the model is not registered.
        ModelLoadError: If loading from disk or initialization fails.
    """
    definition = get_model_definition(name_or_key)

    if not force_reload and definition.key in _LOADED_MODELS:
        return _LOADED_MODELS[definition.key]

    source_path = resolve_model_path(definition)
    if not source_path.exists():
        raise ModelLoadError(
            f"Model '{definition.name}' directory not found at resolved path: {source_path}"
        )

    # Evict older cached models if at capacity to keep memory well under 512MB
    if len(_LOADED_MODELS) >= MAX_CACHED_MODELS:
        keys_to_evict = [k for k in list(_LOADED_MODELS.keys()) if k != definition.key]
        for k in keys_to_evict:
            del _LOADED_MODELS[k]
        gc.collect()

    try:
        if source_path.is_file() and source_path.suffix == ".pt":
            packaged_pt_path = source_path
        else:
            packaged_pt_path = _ensure_packaged_pt(definition, source_path)
        # Load through Ultralytics YOLO with explicit task
        model_instance = YOLO(str(packaged_pt_path), task=definition.task)

        # Store in memory cache
        _LOADED_MODELS[definition.key] = model_instance
        return model_instance
    except ModelLoadError:
        raise
    except Exception as e:
        raise ModelLoadError(
            f"Failed to initialize Ultralytics model '{definition.name}' from '{source_path}': {e}"
        ) from e


def get_loaded_models() -> Dict[str, YOLO]:
    """Return all currently loaded model instances in memory."""
    return dict(_LOADED_MODELS)


def is_model_loaded(name_or_key: str) -> bool:
    """Check if a specific model is already resident in memory."""
    try:
        definition = get_model_definition(name_or_key)
        return definition.key in _LOADED_MODELS
    except ModelNotFoundError:
        return False


def clear_model_cache() -> None:
    """Clear in-memory cache and unload models."""
    _LOADED_MODELS.clear()
    gc.collect()

