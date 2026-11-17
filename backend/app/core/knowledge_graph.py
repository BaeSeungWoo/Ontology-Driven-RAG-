"""Search the delivered manual indexes without changing the answer pipeline."""
from collections import OrderedDict
import json
import os
from pathlib import Path
import re
from threading import Lock


ROOT = Path(__file__).resolve().parents[3]
CORPORA = ("dhf8000", "fanuc")
_LOCK = Lock()
_RESULTS = OrderedDict()
_CACHE_SIZE = 8
_SOURCE_CHAR_LIMIT = 700


class KnowledgeGraphConfigurationError(RuntimeError):
    """The manual indexes or their local dependencies are unavailable."""


class KnowledgeGraphSearchError(RuntimeError):
    """The embedding service or manual search failed."""


def _index_settings(factory_id="yunam"):
    indexes, fingerprints = [], []
    index_root = ROOT / "backend/data/graph_indexes"
    if factory_id != "yunam_origin":
        index_root = index_root / factory_id
    registry = index_root / "indexes.json"
    corpora = CORPORA
    if registry.exists():
        try:
            corpora = json.loads(registry.read_text(encoding="utf-8"))
            if (not isinstance(corpora, list) or not corpora
                    or any(not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name) for name in corpora)
                    or len(set(corpora)) != len(corpora)):
                raise ValueError("Invalid corpus registry")
        except (OSError, ValueError) as exc:
            raise KnowledgeGraphConfigurationError("공장별 지식그래프 인덱스 목록을 읽을 수 없습니다.") from exc
    for name in corpora:
        variable = f"GRAPH_INDEX_{name.upper()}_DIR" if factory_id == "yunam_origin" else f"GRAPH_INDEX_{factory_id.upper()}_{name.upper()}_DIR"
        directory = Path(os.environ.get(variable) or index_root / name).resolve()
        manifest_path = directory / "manifest.json"
        try:
            stat = manifest_path.stat()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 2 or not all(manifest.get(key) for key in (
                "embedding_model", "embedding_base_url", "embedding_dimensions",
            )):
                raise ValueError("Invalid embedding manifest")
            if int(manifest["embedding_dimensions"]) < 1:
                raise ValueError("Invalid embedding dimensions")
        except (OSError, ValueError, AttributeError) as exc:
            raise KnowledgeGraphConfigurationError(
                f"{name.upper()} 매뉴얼 인덱스를 읽을 수 없습니다. {variable}을 manifest.json이 있는 폴더로 설정해 주세요."
            ) from exc
        indexes.append((name, directory, manifest))
        fingerprints.append((name, str(directory), stat.st_mtime_ns, stat.st_size))
    cache = Path(os.environ.get("GRAPH_INDEX_CACHE_DIR") or ROOT / "backend/data/graph_index_cache").resolve()
    return indexes, cache, (tuple(fingerprints), str(cache))


def _load_toolkit():
    # Keep large numeric/parquet dependencies out of API startup.
    try:
        from vendor.graph_index_toolkit.graphindex import get_search
        from vendor.graph_index_toolkit.query import embed_question
        from vendor.graph_index_toolkit.trace import export_trace
    except ImportError as exc:
        raise KnowledgeGraphConfigurationError(
            "매뉴얼 그래프 검색 의존성이 없습니다. backend/requirements.txt를 설치해 주세요."
        ) from exc
    return get_search, embed_question, export_trace


def _answer_sources(corpus, results, start_index):
    sources = []
    for item in results:
        if item["type"] == "passage":
            content = item["content"].strip()
        else:
            table = item["table"]
            content = "\n".join([
                item.get("caption", ""),
                " | ".join(map(str, table["header"])),
                *(" | ".join(map(str, row)) for row in table["rows"]),
            ]).strip()
        if not content:
            continue
        if len(content) > _SOURCE_CHAR_LIMIT:
            # Prefer complete table rows / paragraphs within each source's equal budget.
            excerpt = content[:_SOURCE_CHAR_LIMIT]
            line_end = excerpt.rfind("\n")
            if line_end >= _SOURCE_CHAR_LIMIT // 2:
                excerpt = excerpt[:line_end]
            content = excerpt.rstrip() + "\n[이하 생략]"
        metadata = item["source"]
        sources.append({
            "index": start_index + len(sources),
            "corpus": corpus,
            "document_name": f"{corpus.upper()} · {metadata.get('source_doc_name') or '문서명 미상'}",
            "page": str(metadata.get("page_range") or ""),
            "excerpt": content,
            **({"rows": [[{"text": str(cell)} for cell in row] for row in [table["header"], *table["rows"]]]}
               if item["type"] == "table" else {}),
        })
    return sources


def build_question_graph(question: str, factory_id: str = "yunam") -> dict:
    question = question.strip()
    if not question:
        raise ValueError("질문을 입력해 주세요.")
    # Both indexes are large; serialise loading/search and reuse recent results.
    with _LOCK:
        indexes, cache, configuration = _index_settings(factory_id)
        key = (configuration, question)
        if key in _RESULTS:
            _RESULTS.move_to_end(key)
            return _RESULTS[key]
        get_search, embed_question, export_trace = _load_toolkit()
        vectors, datasets, sources = {}, [], []
        for name, directory, manifest in indexes:
            embedding_key = (manifest["embedding_base_url"], manifest["embedding_model"],
                             int(manifest["embedding_dimensions"]))
            if embedding_key not in vectors:
                try:
                    vectors[embedding_key] = embed_question(manifest, question)
                except Exception as exc:
                    raise KnowledgeGraphSearchError(
                        "질문 임베딩을 만들지 못했습니다. 매뉴얼 인덱스의 임베딩 서버 연결과 모델 상태를 확인해 주세요."
                    ) from exc
            try:
                search = get_search(directory, cache)
            except (OSError, ValueError, KeyError) as exc:
                raise KnowledgeGraphConfigurationError(
                    f"{name.upper()} 매뉴얼 인덱스를 불러오지 못했습니다. 인덱스 파일과 GRAPH_INDEX_CACHE_DIR의 쓰기 권한을 확인해 주세요."
                ) from exc
            try:
                trace = {}
                vector = vectors[embedding_key]
                results = search.retrieve(vector, top_k=3, trace=trace)
                datasets.append(export_trace(search, vector, question, results, trace, top_k=3))
                sources.extend(_answer_sources(name, results, len(sources) + 1))
            except Exception as exc:
                raise KnowledgeGraphSearchError(
                    f"{name.upper()} 매뉴얼 그래프 검색에 실패했습니다. 잠시 후 다시 시도해 주세요."
                ) from exc
        result = {"question": question, "corpora": [name for name, _, _ in indexes], "sources": sources,
                  "datasets": datasets}
        _RESULTS[key] = result
        while len(_RESULTS) > _CACHE_SIZE:
            _RESULTS.popitem(last=False)
        return result
