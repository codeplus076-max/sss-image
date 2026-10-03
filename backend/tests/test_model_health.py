"""Unit tests for Model Health and Inspection Diagnostic Utility."""

from app.services.model_health import inspect_all_models, inspect_model


def test_inspect_single_model():
    """Verify inspection returns valid diagnostic info for GhostVision."""
    info = inspect_model("ghostvision")
    assert info.model_key == "ghostvision"
    assert info.exists_on_disk is True
    assert info.is_loadable is True
    assert info.classes_count == 1
    assert info.raw_classes == {0: "Crab-Pot"}
    assert info.error_message is None


def test_inspect_all_registered_models():
    """Verify all 6 registered models pass disk existence and loadability checks."""
    all_info = inspect_all_models()
    assert len(all_info) == 6

    for info in all_info:
        assert info.exists_on_disk is True, f"Model {info.model_key} failed disk check"
        assert info.is_loadable is True, f"Model {info.model_key} failed load check: {info.error_message}"
        assert info.classes_count > 0
