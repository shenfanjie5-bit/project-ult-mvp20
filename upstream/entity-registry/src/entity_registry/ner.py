"""Chinese NER adapter contracts used by resolution candidate generation."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, field_validator, model_validator

if TYPE_CHECKING:
    from entity_registry.resolution_types import ResolutionContext


class ExtractedMention(BaseModel):
    """One entity mention extracted from free text."""

    mention_text: str
    entity_type: str | None = None
    start: int | None = None
    end: int | None = None
    confidence: float | None = None
    source: str = "hanlp"

    @field_validator("mention_text")
    @classmethod
    def validate_mention_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("mention_text must not be empty")
        return cleaned

    @field_validator("start", "end")
    @classmethod
    def validate_offset(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("mention offsets must be non-negative")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        if value is not None and (value < 0.0 or value > 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value

    @model_validator(mode="after")
    def validate_span_order(self) -> ExtractedMention:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must be less than or equal to end")
        return self


class NERExtractor(Protocol):
    """Runtime contract for extracting mentions before fuzzy matching."""

    def extract_mentions(
        self,
        text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
    ) -> list[ExtractedMention]: ...


class NullNERExtractor:
    """NER extractor used when HanLP is not configured for this runtime."""

    def extract_mentions(
        self,
        text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
    ) -> list[ExtractedMention]:
        return []


class HanLPNERExtractor:
    """Lazy HanLP wrapper with a narrow, testable result normalizer."""

    def __init__(
        self,
        model_name: str | None = None,
        task_name: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._task_name = task_name
        self._model: Any | None = None

    def extract_mentions(
        self,
        text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
    ) -> list[ExtractedMention]:
        if not text.strip():
            return []

        payload = self._load_model()(text)
        mentions: list[ExtractedMention] = []
        for item in _iter_ner_items(payload, self._task_name):
            mention = _coerce_extracted_mention(item)
            if mention is not None:
                mentions.append(mention)
        return mentions

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            hanlp = importlib.import_module("hanlp")
        except ImportError as exc:
            raise RuntimeError(
                "HanLP is not installed; install entity-registry with the 'ner' "
                "extra or use NullNERExtractor"
            ) from exc

        model_name = self._model_name or _default_hanlp_ner_model_name(hanlp)
        try:
            self._model = hanlp.load(model_name)
        except AttributeError as exc:
            raise RuntimeError("HanLP module does not expose load(model_name)") from exc
        return self._model


def _default_hanlp_ner_model_name(hanlp: Any) -> str:
    pretrained = getattr(hanlp, "pretrained", None)
    ner_models = getattr(pretrained, "ner", None)
    model_name = getattr(ner_models, "MSRA_NER_BERT_BASE_ZH", None)
    if isinstance(model_name, str):
        return model_name
    return "MSRA_NER_BERT_BASE_ZH"


def _iter_ner_items(payload: Any, task_name: str | None) -> list[Any]:
    raw_items: Any = payload
    if isinstance(payload, dict):
        raw_items = _select_ner_payload(payload, task_name)
    if raw_items is None:
        return []
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("entities", raw_items.get("mentions", []))
    if isinstance(raw_items, str):
        return [raw_items]
    if isinstance(raw_items, list | tuple):
        if raw_items and all(isinstance(item, list | tuple) for item in raw_items):
            return list(raw_items)
        return list(raw_items)
    return []


def _select_ner_payload(payload: dict[Any, Any], task_name: str | None) -> Any:
    if task_name is not None and task_name in payload:
        return payload[task_name]
    for key, value in payload.items():
        if "ner" in str(key).lower():
            return value
    return None


def _coerce_extracted_mention(item: Any) -> ExtractedMention | None:
    if isinstance(item, ExtractedMention):
        return item
    if isinstance(item, str):
        return ExtractedMention(mention_text=item)
    if isinstance(item, dict):
        return _coerce_dict_mention(item)
    if isinstance(item, list | tuple):
        return _coerce_sequence_mention(list(item))
    return None


def _coerce_dict_mention(item: dict[Any, Any]) -> ExtractedMention | None:
    mention_text = (
        item.get("mention_text")
        or item.get("text")
        or item.get("word")
        or item.get("entity")
    )
    if not isinstance(mention_text, str):
        return None

    return ExtractedMention(
        mention_text=mention_text,
        entity_type=_optional_text(
            item.get("entity_type") or item.get("type") or item.get("label")
        ),
        start=_optional_int(item.get("start")),
        end=_optional_int(item.get("end")),
        confidence=_optional_float(item.get("confidence") or item.get("score")),
        source=_optional_text(item.get("source")) or "hanlp",
    )


def _coerce_sequence_mention(values: list[Any]) -> ExtractedMention | None:
    if not values or not isinstance(values[0], str):
        return None

    mention_text = values[0]
    entity_type: str | None = None
    start: int | None = None
    end: int | None = None
    confidence: float | None = None

    if len(values) >= 4 and isinstance(values[1], str):
        entity_type = values[1]
        start = _optional_int(values[2])
        end = _optional_int(values[3])
    elif len(values) >= 4:
        start = _optional_int(values[1])
        end = _optional_int(values[2])
        entity_type = _optional_text(values[3])
    elif len(values) >= 2:
        entity_type = _optional_text(values[1])

    if len(values) >= 5:
        confidence = _optional_float(values[4])

    return ExtractedMention(
        mention_text=mention_text,
        entity_type=entity_type,
        start=start,
        end=end,
        confidence=confidence,
        source="hanlp",
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ExtractedMention",
    "HanLPNERExtractor",
    "NERExtractor",
    "NullNERExtractor",
]
