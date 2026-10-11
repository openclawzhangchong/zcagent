"""Tests for the curated ONNX catalog: role prefixes, recommended set, sizes.

These three facts used to be wrong in ways that produce no error at runtime:
e5-family models silently degrade without their input prefixes, the recommended
set advertised a 2.24 GB model to desktop users, and the fallback size table
disputed with fastembed by ~2x in both directions.
"""

from __future__ import annotations

import pytest

from octop.infra.agents.providers.onnx_catalog import (
    _EXTRA_CATALOG_IDS,
    _FALLBACK_SIZE_GB,
    CURATED_MODEL_IDS,
    ONNX_PRESET_MODEL_IDS,
    PASSAGE_ROLE,
    QUERY_ROLE,
    apply_role_prefix,
    list_onnx_catalog_models,
    model_notes,
    needs_role_prefix,
)

E5 = "intfloat/multilingual-e5-large"
BGE_ZH = "BAAI/bge-small-zh-v1.5"


class TestRolePrefixes:
    def test_e5_family_needs_prefixes(self) -> None:
        assert needs_role_prefix(E5)
        assert needs_role_prefix("intfloat/e5-small-v2")

    def test_other_models_are_left_alone(self) -> None:
        for model in (BGE_ZH, "jinaai/jina-embeddings-v2-base-zh", "thenlper/gte-large"):
            assert not needs_role_prefix(model)
            assert apply_role_prefix(model, "请假制度", QUERY_ROLE) == "请假制度"

    def test_query_and_passage_get_different_tags(self) -> None:
        """The whole point: the two sides must not be embedded identically."""
        query = apply_role_prefix(E5, "如何请假", QUERY_ROLE)
        passage = apply_role_prefix(E5, "员工请假管理办法", PASSAGE_ROLE)
        assert query == "query: 如何请假"
        assert passage == "passage: 员工请假管理办法"
        assert query.split(":")[0] != passage.split(":")[0]

    def test_unknown_role_is_rejected_for_prefixed_models(self) -> None:
        with pytest.raises(ValueError, match="unknown embedding role"):
            apply_role_prefix(E5, "text", "document")

    def test_unknown_role_is_harmless_for_plain_models(self) -> None:
        assert apply_role_prefix(BGE_ZH, "text", "nonsense") == "text"


class TestRecommendedSet:
    def test_every_recommended_model_works_for_chinese(self) -> None:
        assert set(ONNX_PRESET_MODEL_IDS) == {
            BGE_ZH,
            "jinaai/jina-embeddings-v2-base-zh",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        }

    def test_no_recommended_model_needs_call_site_help(self) -> None:
        """A default-facing model that silently degrades is worse than none."""
        for model in ONNX_PRESET_MODEL_IDS:
            assert not needs_role_prefix(model), model

    def test_e5_large_demoted_not_dropped(self) -> None:
        assert E5 not in ONNX_PRESET_MODEL_IDS
        assert E5 in _EXTRA_CATALOG_IDS

    def test_default_is_the_smallest_fastest(self) -> None:
        assert ONNX_PRESET_MODEL_IDS[0] == BGE_ZH
        assert _FALLBACK_SIZE_GB[BGE_ZH] <= 0.1

    def test_no_id_is_both_preset_and_extra(self) -> None:
        assert not set(ONNX_PRESET_MODEL_IDS) & set(_EXTRA_CATALOG_IDS)


@pytest.fixture(scope="module")
def fastembed_sizes() -> dict[str, float]:
    fastembed = pytest.importorskip("fastembed", reason="optional extra")
    return {
        str(m["model"]): float(m["size_in_GB"])
        for m in fastembed.TextEmbedding.list_supported_models()
    }


class TestModelNotes:
    """Every curated model must carry both languages.

    An uncurated model renders no note line at all, which is fine for the long
    tail but would be a silent gap for anything we put in front of a user.
    """

    def test_every_curated_model_has_both_notes(self) -> None:
        for model in [*ONNX_PRESET_MODEL_IDS, *_EXTRA_CATALOG_IDS]:
            zh, en = model_notes(model)
            assert zh, f"{model} has no Chinese note"
            assert en, f"{model} has no English note"

    def test_notes_are_one_liner_sized(self) -> None:
        for model in [*ONNX_PRESET_MODEL_IDS, *_EXTRA_CATALOG_IDS]:
            zh, en = model_notes(model)
            assert len(zh) <= 120, f"{model} Chinese note is too long to sit on one line"
            assert len(en) <= 220, f"{model} English note is too long to sit on one line"

    def test_notes_reach_the_api_entry(self) -> None:
        served = {str(m["id"]): m for m in list_onnx_catalog_models()}
        for model in ONNX_PRESET_MODEL_IDS:
            entry = served[model]
            assert entry.get("note_zh"), model
            assert entry.get("note_en"), model

    def test_unknown_model_has_no_note(self) -> None:
        assert model_notes("some/brand-new-model") == ("", "")


class TestKnowledgeDialogOptions:
    """The dialog used to receive every model fastembed can load -- 41 entries
    including a CLIP text tower, which is simply the wrong tool here."""

    def test_default_view_is_the_recommended_set(self) -> None:
        from octop.api.routers.knowledge_bases import _onnx_options_for_knowledge

        ids = [str(m["id"]) for m in _onnx_options_for_knowledge(include_all=False)]
        assert ids == list(ONNX_PRESET_MODEL_IDS)

    def test_expanded_view_stays_inside_the_curated_catalog(self) -> None:
        from octop.api.routers.knowledge_bases import _onnx_options_for_knowledge

        ids = [str(m["id"]) for m in _onnx_options_for_knowledge(include_all=True)]
        assert set(ids) == set(CURATED_MODEL_IDS)
        assert all("clip" not in mid.lower() for mid in ids)
        assert len(ids) < 20, f"expanded view leaked {len(ids)} models"

    def test_expanded_view_superset_of_default(self) -> None:
        from octop.api.routers.knowledge_bases import _onnx_options_for_knowledge

        default = {str(m["id"]) for m in _onnx_options_for_knowledge(include_all=False)}
        expanded = {str(m["id"]) for m in _onnx_options_for_knowledge(include_all=True)}
        assert default < expanded


class TestFallbackSizes:
    """The table is only used when fastembed cannot be imported, which is exactly
    the situation where nobody notices it disagrees with reality."""

    def test_every_curated_id_has_a_size(self, fastembed_sizes: None) -> None:
        curated = [*ONNX_PRESET_MODEL_IDS, *_EXTRA_CATALOG_IDS]
        assert set(curated) <= set(_FALLBACK_SIZE_GB)

    def test_sizes_agree_with_fastembed_within_twenty_percent(
        self, fastembed_sizes: dict[str, float]
    ) -> None:
        for model, claimed in _FALLBACK_SIZE_GB.items():
            real = fastembed_sizes.get(model)
            if real is None:
                continue
            drift = abs(claimed - real) / real
            assert drift <= 0.20, f"{model}: table says {claimed} GB, fastembed says {real} GB"

    def test_curated_ids_are_loadable_by_fastembed(self, fastembed_sizes: None) -> None:
        """An entry fastembed cannot load vanishes mid-flow and fails the download."""
        from octop.infra.agents.providers.onnx_catalog import list_onnx_catalog_models

        served = {str(m["id"]) for m in list_onnx_catalog_models()}
        for model in [*ONNX_PRESET_MODEL_IDS, *_EXTRA_CATALOG_IDS]:
            assert model in served, model
