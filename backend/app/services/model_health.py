"""Model Health and Inspection Utility.

Verifies that registered Side-Scan Sonar models exist on disk, can be loaded
into memory, and have intact metadata and class definitions.
"""

from typing import List
from app.core.model_registry import (
    MODEL_REGISTRY,
    ModelDefinition,
    get_model_definition,
    resolve_model_path,
)
from app.schemas.inference import ModelHealthInfo
from app.services.model_loader import load_model


def inspect_model(name_or_key: str) -> ModelHealthInfo:
    """Perform a diagnostic health check on a specific model."""
    definition: ModelDefinition = get_model_definition(name_or_key)
    path = resolve_model_path(definition)
    exists = path.exists() and (path.is_file() or (path / "data.pkl").exists())

    is_loadable = False
    error_msg = None

    if not exists:
        error_msg = f"Model checkpoint files missing at path: {path}"
    else:
        try:
            model = load_model(definition.key)
            is_loadable = True
        except Exception as e:
            error_msg = str(e)

    return ModelHealthInfo(
        model_key=definition.key,
        name=definition.name,
        architecture=definition.architecture,
        input_size=definition.input_size,
        task=definition.task,
        exists_on_disk=exists,
        is_loadable=is_loadable,
        classes_count=len(definition.raw_classes),
        raw_classes=definition.raw_classes,
        semantic_labels=definition.semantic_labels,
        error_message=error_msg,
    )


def inspect_all_models() -> List[ModelHealthInfo]:
    """Perform health checks across all registered models."""
    return [inspect_model(key) for key in MODEL_REGISTRY]
