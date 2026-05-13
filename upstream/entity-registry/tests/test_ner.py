from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import entity_registry
import entity_registry.ner as ner_module
from entity_registry.ner import ExtractedMention, HanLPNERExtractor, NullNERExtractor


def test_package_exports_ner_public_types() -> None:
    assert entity_registry.ExtractedMention is ExtractedMention
    assert entity_registry.HanLPNERExtractor is HanLPNERExtractor
    assert entity_registry.NullNERExtractor is NullNERExtractor


def test_extracted_mention_validates_text_and_confidence() -> None:
    mention = ExtractedMention(
        mention_text=" 贵州茅台 ",
        entity_type="ORG",
        start=0,
        end=4,
        confidence=0.95,
    )

    assert mention.mention_text == "贵州茅台"
    with pytest.raises(ValidationError):
        ExtractedMention(mention_text="")
    with pytest.raises(ValidationError):
        ExtractedMention(mention_text="贵州茅台", confidence=1.1)
    with pytest.raises(ValidationError):
        ExtractedMention(mention_text="贵州茅台", start=4, end=1)


def test_null_ner_extractor_returns_empty_list() -> None:
    assert NullNERExtractor().extract_mentions("贵州茅台公告") == []


def test_hanlp_extractor_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(ner_module.importlib, "import_module", fail_import)
    extractor = HanLPNERExtractor(model_name="fake-model")

    with pytest.raises(RuntimeError, match="HanLP is not installed"):
        extractor.extract_mentions("贵州茅台公告")


def test_hanlp_extractor_normalizes_fake_hanlp_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_models: list[str] = []

    def load(model_name: str):
        loaded_models.append(model_name)
        return lambda text: {
            "ner/msra": [
                ("贵州茅台", "ORG", 0, 4, 0.93),
                {"text": "平安银行", "type": "ORG", "start": 5, "end": 9},
            ]
        }

    fake_hanlp = SimpleNamespace(load=load)
    monkeypatch.setattr(
        ner_module.importlib,
        "import_module",
        lambda name: fake_hanlp,
    )

    mentions = HanLPNERExtractor(
        model_name="fake-model",
        task_name="ner/msra",
    ).extract_mentions("贵州茅台和平安银行")

    assert loaded_models == ["fake-model"]
    assert [mention.mention_text for mention in mentions] == ["贵州茅台", "平安银行"]
    assert mentions[0].entity_type == "ORG"
    assert mentions[0].confidence == 0.93
    assert mentions[1].start == 5
