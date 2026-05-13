from typing import Any

from .base import BaseMessageClassifier

_registry: dict[str, BaseMessageClassifier] = {}


def get_enabled_classifiers() -> list[tuple[BaseMessageClassifier, float, list[str]]]:
    """Return (classifier, threshold, flag_labels) for each enabled classifier in settings."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    result: list[tuple[BaseMessageClassifier, float, list[str]]] = []
    for cfg in getattr(settings, "MODERATION_CLASSIFIERS", []):
        if not cfg.get("enabled", True):
            continue
        name: str = cfg["name"]
        if name not in _registry:
            cls: type[BaseMessageClassifier] = import_string(cfg["class"])
            _registry[name] = cls()
        threshold: float = cfg["threshold"]
        flag_labels: list[str] = cfg.get("flag_labels", ["hate"])
        result.append((_registry[name], threshold, flag_labels))
    return result
