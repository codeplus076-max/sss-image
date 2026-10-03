"""Unit tests for Model Registry and Class Mappings."""

import pytest
from app.core.model_registry import (
    MODEL_REGISTRY,
    ModelNotFoundError,
    get_model_definition,
    list_registered_models,
)


def test_registry_contains_six_verified_models():
    """Verify exactly 6 verified models exist in the registry including natural_seabed."""
    registered = list_registered_models()
    keys = {m.key for m in registered}
    expected_keys = {"cylinder", "ghostvision", "mines", "shipwreck", "subpipes", "natural_seabed"}
    assert keys == expected_keys
    assert len(registered) == 6


def test_natural_seabed_in_registry():
    """Verify that Natural Seabed classifier is properly registered with expected task and classes."""
    assert "natural_seabed" in MODEL_REGISTRY
    m = get_model_definition("natural_seabed")
    assert m.architecture == "YOLO26m-cls"
    assert m.input_size == (224, 224)
    assert m.task == "classify"
    assert m.raw_classes == {0: "clean_seabed", 1: "debris_anomaly"}
    assert m.get_semantic_label(0) == "Natural Clean Seabed"
    assert m.get_semantic_label(1) == "Seafloor Anomaly / Debris"


def test_cylinder_model_properties():
    """Verify Cylinder model definition, input resolution 1536x1536, and single class."""
    m = get_model_definition("cylinder")
    assert m.architecture == "YOLO12s"
    assert m.input_size == (1536, 1536)
    assert m.task == "detect"
    assert m.raw_classes == {0: "Cylinder"}
    assert m.get_semantic_label(0) == "Industrial Cylinder / Drum"


def test_ghostvision_model_properties():
    """Verify GhostVision model definition and semantic label for Crab-Pot."""
    m = get_model_definition("ghostvision")
    assert m.architecture == "YOLO12s"
    assert m.input_size == (640, 640)
    assert m.raw_classes == {0: "Crab-Pot"}
    assert "Abandoned Fishing Gear" in m.get_semantic_label(0)


def test_mine_detector_properties():
    """Verify Mine detector classes (MILCO, NOMBO) and semantic labels."""
    m = get_model_definition("mines")
    assert m.architecture == "YOLO12s"
    assert m.input_size == (640, 640)
    assert m.raw_classes == {0: "MILCO", 1: "NOMBO"}
    assert "Mine-Like Contact" in m.get_semantic_label(0)
    assert "Non-Mine" in m.get_semantic_label(1)


def test_shipwreck_detector_properties():
    """Verify Shipwreck detector classes including Class_0 and Shipwreck."""
    m = get_model_definition("shipwreck")
    assert m.architecture == "YOLO26n"
    assert m.input_size == (640, 640)
    assert m.raw_classes == {
        0: "Class_0",
        1: "MILCO",
        2: "NOMBO",
        3: "Shipwreck",
    }
    # Class_0 must be preserved and marked as unknown/unlabeled
    assert "Class_0" in m.get_semantic_label(0)
    assert "Unknown / Unlabeled" in m.get_semantic_label(0)
    assert "Shipwreck" in m.get_semantic_label(3)


def test_subpipes_detector_properties():
    """Verify Subsea Pipeline detector properties."""
    m = get_model_definition("subpipes")
    assert m.architecture == "YOLO12s"
    assert m.input_size == (640, 640)
    assert m.raw_classes == {0: "Pipeline"}
    assert "Pipeline" in m.get_semantic_label(0)


def test_missing_model_raises_error():
    """Verify that querying an unknown model raises ModelNotFoundError without silent fallback."""
    with pytest.raises(ModelNotFoundError) as exc_info:
        get_model_definition("non_existent_sonar_model")
    assert "non_existent_sonar_model" in str(exc_info.value)
