"""Curated ONNX / fastembed embedding model catalog."""

from __future__ import annotations

from typing import Any

# e5-family models are trained with an asymmetric role prefix on every input:
# "query: " for the search side and "passage: " for the indexed side. Feeding
# both through unprefixed still returns vectors and still returns results --
# retrieval quality just silently drops, which is worse than an error.
_PREFIXED_MODEL_PREFIXES: tuple[str, ...] = ("intfloat/e5-", "intfloat/multilingual-e5-")

QUERY_ROLE = "query"
PASSAGE_ROLE = "passage"
_ROLE_PREFIXES = {QUERY_ROLE: "query: ", PASSAGE_ROLE: "passage: "}


def needs_role_prefix(model_id: str) -> bool:
    """Whether ``model_id`` expects its inputs tagged as query or passage."""
    return any(model_id.startswith(prefix) for prefix in _PREFIXED_MODEL_PREFIXES)


def apply_role_prefix(model_id: str, text: str, role: str) -> str:
    """Tag one input the way the model was trained, when it expects that."""
    if not needs_role_prefix(model_id):
        return text
    try:
        prefix = _ROLE_PREFIXES[role]
    except KeyError:
        raise ValueError(f"unknown embedding role: {role!r}") from None
    return f"{prefix}{text}"


# Shown in the knowledge-base dialog without expanding "高级选项". Every entry
# here must be usable for Chinese corpora and must not need call-site help --
# intfloat/multilingual-e5-large was demoted for both reasons (2.24 GB, and it
# silently degrades unless the caller tags queries and passages).
ONNX_PRESET_MODEL_IDS: tuple[str, ...] = (
    "BAAI/bge-small-zh-v1.5",
    "jinaai/jina-embeddings-v2-base-zh",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)

# Shown only while fastembed is unimportable, so every id here must also be
# loadable by fastembed once the extra installs — otherwise the entry vanishes
# from the catalog mid-flow and the download fails on an unsupported model.
_EXTRA_CATALOG_IDS: tuple[str, ...] = (
    "intfloat/multilingual-e5-large",
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "BAAI/bge-large-en-v1.5",
    "jinaai/jina-embeddings-v2-base-en",
    "jinaai/jina-embeddings-v2-small-en",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "thenlper/gte-base",
    "thenlper/gte-large",
)

# Approximate sizes (GB) when fastembed metadata is unavailable. Measured against
# fastembed's own ``size_in_GB`` on 2026-10-11; six of the previous twelve entries
# were off by ~2x in both directions, so the same model advertised a different
# download size depending on whether fastembed happened to import.
_FALLBACK_SIZE_GB: dict[str, float] = {
    "BAAI/bge-small-zh-v1.5": 0.09,
    "jinaai/jina-embeddings-v2-base-zh": 0.64,
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": 1.0,
    "intfloat/multilingual-e5-large": 2.24,
    "BAAI/bge-small-en-v1.5": 0.067,
    "BAAI/bge-base-en-v1.5": 0.21,
    "BAAI/bge-large-en-v1.5": 1.2,
    "jinaai/jina-embeddings-v2-base-en": 0.52,
    "jinaai/jina-embeddings-v2-small-en": 0.12,
    "sentence-transformers/all-MiniLM-L6-v2": 0.09,
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 0.22,
    "thenlper/gte-base": 0.44,
    "thenlper/gte-large": 1.2,
}

# When fastembed is not installed, still recognize HF cache dirs it would create.
_HF_SOURCE_FALLBACK: dict[str, str] = {
    "BAAI/bge-small-zh-v1.5": "Qdrant/bge-small-zh-v1.5",
    "BAAI/bge-small-en-v1.5": "qdrant/bge-small-en-v1.5-onnx-q",
    "BAAI/bge-base-en-v1.5": "qdrant/bge-base-en-v1.5-onnx-q",
    "BAAI/bge-large-en-v1.5": "qdrant/bge-large-en-v1.5-onnx",
    "sentence-transformers/all-MiniLM-L6-v2": "qdrant/all-MiniLM-L6-v2-onnx",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": (
        "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    ),
    "jinaai/jina-embeddings-v2-base-en": "xenova/jina-embeddings-v2-base-en",
    "jinaai/jina-embeddings-v2-small-en": "xenova/jina-embeddings-v2-small-en",
    "thenlper/gte-large": "qdrant/gte-large-onnx",
    "intfloat/multilingual-e5-large": "qdrant/multilingual-e5-large-onnx",
}


# One-line pro-and-con per curated model, as (Chinese, English).
#
# Curated catalog copy lives here rather than in the dashboard locales because
# model ids contain "/" and ".", both of which are i18next key separators, and
# this is already how the expert catalog carries label_zh / label_en.
_MODEL_NOTES: dict[str, tuple[str, str]] = {
    "BAAI/bge-small-zh-v1.5": (
        "92 MB、CPU 上秒级响应，中文短文档检索性价比最高；缺点是长篇条款与专业术语召回弱于大模型，超 512 token 会被截断。",
        "92 MB and instant on CPU, the best value for short Chinese documents; weaker on long clauses and jargon, and truncates past 512 tokens.",
    ),
    "jinaai/jina-embeddings-v2-base-zh": (
        "支持 8192 token 超长上下文，整段规章制度不用切碎，中英混排也稳；缺点是 640 MB，CPU 上索引大库明显更慢。",
        "8192-token context keeps whole policy documents intact and handles mixed Chinese/English, but 640 MB indexes large corpora slowly on CPU.",
    ),
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": (
        "768 维、约 50 种语言，多语种质量标杆之一，且不需要任何调用侧配合；缺点是 1.0 GB，纯中文场景不如 bge 系列划算。",
        "768-dim over ~50 languages, a multilingual benchmark that needs no call-site help; at 1.0 GB it is poor value for Chinese-only corpora.",
    ),
    "intfloat/multilingual-e5-large": (
        "1024 维、约 100 种语言，跨语言检索最强；但 2.24 GB 最重，且要求区分查询/文档前缀（本版本已自动处理）。",
        "1024-dim across ~100 languages, the strongest cross-lingual option, but 2.24 GB and it needs query/passage tagging (handled automatically now).",
    ),
    "BAAI/bge-small-en-v1.5": (
        "67 MB 的英文小模型标杆；缺点是中文语料召回差，不要拿它建中文知识库。",
        "67 MB English small-model benchmark, but poor on Chinese — do not build a Chinese knowledge base on it.",
    ),
    "BAAI/bge-base-en-v1.5": (
        "210 MB，英文精度更好；同样不适合中文。",
        "210 MB with better English accuracy; still wrong for Chinese.",
    ),
    "BAAI/bge-large-en-v1.5": (
        "1.2 GB 英文高精度；中文场景没有理由选它。",
        "1.2 GB high-accuracy English model; no reason to pick it for Chinese.",
    ),
    "jinaai/jina-embeddings-v2-base-en": (
        "520 MB 英文长上下文（8192 token）；语言不对。",
        "520 MB with 8192-token English context; wrong language.",
    ),
    "jinaai/jina-embeddings-v2-small-en": (
        "120 MB 英文小快；中文不适用。",
        "120 MB fast English model; not for Chinese.",
    ),
    "sentence-transformers/all-MiniLM-L6-v2": (
        "90 MB、社区最知名的轻量模型，但仅英文且上下文只有 256 token——体积与默认的中文模型几乎相同，最容易被误选。",
        "90 MB and the best-known light model, but English-only at 256 tokens — the same size as the Chinese default, so the easiest one to pick by mistake.",
    ),
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": (
        "220 MB 支持约 50 种语言；但上下文只有 128 token，长段落会被切得极碎。",
        "220 MB over ~50 languages, but a 128-token window shreds long paragraphs.",
    ),
    "thenlper/gte-base": (
        "440 MB，英文 MTEB 排名高；中文非其所长。",
        "440 MB with strong English MTEB scores; not a Chinese model.",
    ),
    "thenlper/gte-large": (
        "1.2 GB 英文高精度；中文场景不划算。",
        "1.2 GB high-accuracy English model; poor value for Chinese.",
    ),
}


def model_notes(model_id: str) -> tuple[str, str]:
    """Return ``(zh, en)`` for ``model_id``, or empty strings when uncurated."""
    return _MODEL_NOTES.get(model_id, ("", ""))


def _model_entry(
    model_id: str,
    *,
    recommended: bool = False,
    size_gb: float | None = None,
    hf_source: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": model_id,
        "name": model_id,
        "recommended": recommended,
    }
    note_zh, note_en = model_notes(model_id)
    if note_zh:
        entry["note_zh"] = note_zh
    if note_en:
        entry["note_en"] = note_en
    if size_gb is not None:
        entry["size_gb"] = size_gb
    if hf_source:
        entry["hf_source"] = hf_source
    return entry


def _fastembed_meta_map() -> dict[str, dict[str, Any]]:
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return {}
    try:
        raw = TextEmbedding.list_supported_models()
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        model = item.get("model") or item.get("model_name") or item.get("id")
        if not isinstance(model, str) or not model:
            continue
        out[model] = item
    return out


def _hf_repo_from_sources(sources: object) -> str | None:
    """Read the Hugging Face repo id from fastembed ``sources`` (dict or ModelSource)."""
    raw = sources.get("hf") if isinstance(sources, dict) else getattr(sources, "hf", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def get_onnx_model_meta(model_id: str) -> dict[str, Any]:
    """Return size / HF source metadata for a model id."""
    meta = _fastembed_meta_map().get(model_id) or {}
    size = meta.get("size_in_GB")
    size_gb: float | None
    try:
        size_gb = float(size) if size is not None else None
    except (TypeError, ValueError):
        size_gb = None
    if size_gb is None:
        size_gb = _FALLBACK_SIZE_GB.get(model_id)
    hf_source = _hf_repo_from_sources(meta.get("sources")) or _HF_SOURCE_FALLBACK.get(model_id)
    return {
        "id": model_id,
        "size_gb": size_gb,
        "hf_source": hf_source,
        "supported": bool(meta),
    }


def list_onnx_catalog_models() -> list[dict[str, Any]]:
    """Return catalog entries for the Models local ONNX panel."""
    meta_map = _fastembed_meta_map()
    recommended = set(ONNX_PRESET_MODEL_IDS)

    def enrich(model_id: str, *, rec: bool) -> dict[str, Any]:
        info = get_onnx_model_meta(model_id) if not meta_map else None
        if meta_map and model_id in meta_map:
            item = meta_map[model_id]
            size = item.get("size_in_GB")
            try:
                size_gb = float(size) if size is not None else _FALLBACK_SIZE_GB.get(model_id)
            except (TypeError, ValueError):
                size_gb = _FALLBACK_SIZE_GB.get(model_id)
            hf = _hf_repo_from_sources(item.get("sources")) or _HF_SOURCE_FALLBACK.get(model_id)
            return _model_entry(
                model_id,
                recommended=rec,
                size_gb=size_gb,
                hf_source=hf,
            )
        if info:
            return _model_entry(
                model_id,
                recommended=rec,
                size_gb=info.get("size_gb"),
                hf_source=info.get("hf_source"),
            )
        return _model_entry(
            model_id,
            recommended=rec,
            size_gb=_FALLBACK_SIZE_GB.get(model_id),
        )

    if meta_map:
        ordered = list(ONNX_PRESET_MODEL_IDS) + sorted(
            mid for mid in meta_map if mid not in recommended
        )
        return [enrich(mid, rec=mid in recommended) for mid in ordered]

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for mid in ONNX_PRESET_MODEL_IDS:
        seen.add(mid)
        out.append(enrich(mid, rec=True))
    for mid in _EXTRA_CATALOG_IDS:
        if mid in seen:
            continue
        seen.add(mid)
        out.append(enrich(mid, rec=False))
    return out
