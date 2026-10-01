"""Central Model Registry and Configuration Module.

Defines all verified Side-Scan Sonar detection models, architectures,
native input resolutions, verified raw class mappings, and user-facing
semantic display labels.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelDefinition:
    """Immutable definition of a verified machine learning model."""

    name: str
    key: str
    relative_path: str
    architecture: str
    input_size: Tuple[int, int]  # (width, height)
    task: str
    raw_classes: Dict[int, str]
    semantic_labels: Dict[int, str]
    default_conf: float = 0.25
    default_iou: float = 0.70
    is_end2end: bool = False
    notes: str = ""

    def get_semantic_label(self, class_id: int) -> str:
        """Return the frontend-friendly semantic label for a given class ID."""
        return self.semantic_labels.get(
            class_id, self.raw_classes.get(class_id, f"Unknown (ID: {class_id})")
        )

    def get_raw_class_name(self, class_id: int) -> str:
        """Return the authentic raw class name as trained in the model."""
        return self.raw_classes.get(class_id, f"Class_{class_id}")


# Base directory for models
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BACKEND_DIR / "models"

# Verified registry mapping canonical model keys to definitions
MODEL_REGISTRY: Dict[str, ModelDefinition] = {
    "cylinder": ModelDefinition(
        name="Cylinder Detector",
        key="cylinder",
        relative_path="Cylinder model/best",
        architecture="YOLO12s",
        input_size=(1536, 1536),
        task="detect",
        raw_classes={0: "Cylinder"},
        semantic_labels={0: "Industrial Cylinder / Drum"},
        default_conf=0.25,
        default_iou=0.70,
        notes="High-resolution industrial cylinder & container hazard detector.",
    ),
    "ghostvision": ModelDefinition(
        name="GhostVision",
        key="ghostvision",
        relative_path="GhostVision_YOLO12s_best.pt/best",
        architecture="YOLO12s",
        input_size=(640, 640),
        task="detect",
        raw_classes={0: "Crab-Pot"},
        semantic_labels={0: "Abandoned Fishing Gear (Crab Pot / Trap)"},
        default_conf=0.25,
        default_iou=0.70,
        notes="Ghost gear & abandoned subsea entrapment hazard detector.",
    ),
    "mines": ModelDefinition(
        name="Mine Detector",
        key="mines",
        relative_path="Mine_YOLO12s_best.pt/best",
        architecture="YOLO12s",
        input_size=(640, 640),
        task="detect",
        raw_classes={
            0: "MILCO",
            1: "NOMBO",
        },
        semantic_labels={
            0: "Mine-Like Contact (MILCO)",
            1: "Non-Mine Mine-Like Bottom Object (NOMBO)",
        },
        default_conf=0.25,
        default_iou=0.70,
        notes="Naval mine warfare detector for ordnance and non-ordnance bottom contacts.",
    ),
    "shipwreck": ModelDefinition(
        name="Shipwreck Detector",
        key="shipwreck",
        relative_path="shipwreak model/best",
        architecture="YOLO26n",
        input_size=(640, 640),
        task="detect",
        raw_classes={
            0: "Class_0",
            1: "MILCO",
            2: "NOMBO",
            3: "Shipwreck",
        },
        semantic_labels={
            0: "Class_0 (Unknown / Unlabeled Artifact)",
            1: "Mine-Like Contact (MILCO)",
            2: "Non-Mine Mine-Like Bottom Object (NOMBO)",
            3: "Maritime Shipwreck / Hull",
        },
        default_conf=0.25,
        default_iou=0.70,
        is_end2end=True,
        notes="Multi-class compact detector for maritime wrecks, hulls, and bottom contacts.",
    ),
    "subpipes": ModelDefinition(
        name="Subsea Pipeline Detector",
        key="subpipes",
        relative_path="SubPipeMini2_YOLO12s_best.pt.pt/best",
        architecture="YOLO12s",
        input_size=(640, 640),
        task="detect",
        raw_classes={0: "Pipeline"},
        semantic_labels={0: "Subsea Pipeline / Conduit"},
        default_conf=0.15,
        default_iou=0.70,
        notes="Industrial subsea infrastructure and pipeline detector.",
    ),
}


class ModelNotFoundError(KeyError):
    """Raised when a requested model is not found in the registry."""
    pass


def get_model_definition(name_or_key: str) -> ModelDefinition:
    """Retrieve a model definition by canonical key or case-insensitive name."""
    normalized_key = name_or_key.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

    # Exact key match
    if name_or_key.lower() in MODEL_REGISTRY:
        return MODEL_REGISTRY[name_or_key.lower()]

    # Check aliases for singular/plural or alternative identifiers
    aliases = {
        "mine": "mines",
        "subpipe": "subpipes",
        "subpipemini2": "subpipes",
        "subpipemini": "subpipes",
        "pipeline": "subpipes",
        "minedetector": "mines",
        "cylinderdetector": "cylinder",
        "shipwreckdetector": "shipwreck",
    }
    if normalized_key in aliases:
        return MODEL_REGISTRY[aliases[normalized_key]]

    # Normalized lookup
    for key, definition in MODEL_REGISTRY.items():
        clean_key = key.replace("_", "")
        clean_name = definition.name.lower().replace(" ", "").replace("-", "").replace("_", "")
        if normalized_key in (clean_key, clean_name):
            return definition

    available = ", ".join(f"'{k}' ({v.name})" for k, v in MODEL_REGISTRY.items())
    raise ModelNotFoundError(
        f"Model '{name_or_key}' is not registered. Available models: {available}"
    )


def list_registered_models() -> List[ModelDefinition]:
    """Return all verified model definitions."""
    return list(MODEL_REGISTRY.values())


def resolve_model_path(definition: ModelDefinition) -> Path:
    """Resolve the absolute filesystem path for a model's source directory or packaged .pt archive."""
    # 0. Check for pre-packaged .pt archive first
    direct_pt = MODELS_DIR / f"{definition.key}.pt"
    if direct_pt.exists():
        return direct_pt

    # 1. Check custom environment override if set
    env_dir = os.getenv("MODELS_DIR")
    if env_dir:
        env_pt = Path(env_dir).resolve() / f"{definition.key}.pt"
        if env_pt.exists():
            return env_pt
        env_cand = Path(env_dir).resolve() / definition.relative_path
        if env_cand.exists():
            return env_cand

    # 2. Check primary path relative to backend codebase location
    primary = MODELS_DIR / definition.relative_path
    if primary.exists():
        return primary

    # 3. Check candidate paths relative to current working directory
    cwd = Path.cwd().resolve()
    candidates = [
        cwd / "backend" / "models" / definition.relative_path,
        cwd / "models" / definition.relative_path,
        cwd.parent / "backend" / "models" / definition.relative_path,
        cwd.parent / "models" / definition.relative_path,
    ]
    for cand in candidates:
        if cand.exists():
            return cand

    return primary
