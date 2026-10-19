"""Search the delivered manual indexes without changing the answer pipeline."""
from collections import OrderedDict
import html
import json
import os
from pathlib import Path
import re
from threading import Lock


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "backend/vendor/graph_index_toolkit/templates/graph.html"
CORPORA = ("dhf8000", "fanuc")
_LOCK = Lock()
_RESULTS = OrderedDict()
_CACHE_SIZE = 8
_SOURCE_CHAR_LIMIT = 700


class KnowledgeGraphConfigurationError(RuntimeError):
    """The manual indexes or their local dependencies are unavailable."""


class KnowledgeGraphSearchError(RuntimeError):
    """The embedding service or manual search failed."""


def _index_settings():
    indexes, fingerprints = [], []
    for name in CORPORA:
        variable = f"GRAPH_INDEX_{name.upper()}_DIR"
        directory = Path(os.environ.get(variable) or ROOT / "backend/data/graph_indexes" / name).resolve()
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
        fingerprints.append((str(directory), stat.st_mtime_ns, stat.st_size))
    cache = Path(os.environ.get("GRAPH_INDEX_CACHE_DIR") or ROOT / "backend/data/graph_index_cache").resolve()
    return indexes, cache, (tuple(fingerprints), str(cache))


def _load_toolkit():
    # Keep large numeric/parquet dependencies out of API startup.
    try:
        from vendor.graph_index_toolkit.graphindex import get_search
        from vendor.graph_index_toolkit.query import embed_question
        from vendor.graph_index_toolkit.trace import EDGE_SEMANTICS, export_trace
    except ImportError as exc:
        raise KnowledgeGraphConfigurationError(
            "매뉴얼 그래프 검색 의존성이 없습니다. backend/requirements.txt를 설치해 주세요."
        ) from exc
    return get_search, embed_question, export_trace, EDGE_SEMANTICS


def _render_html(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    options = "\n".join(
        '<option value="' + html.escape(item["id"], quote=True) + '">'
        + html.escape(item["title"]) + "</option>" for item in data["datasets"]
    )
    replacements = {"__GRAPH_DATA_JSON__": payload, "__GRAPH_DATA_OPTIONS__": options}
    fragment = re.sub("__GRAPH_DATA_JSON__|__GRAPH_DATA_OPTIONS__",
                      lambda match: replacements[match[0]], TEMPLATE.read_text(encoding="utf-8"))
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>질문에서 근거까지</title><style>
:root{--background:#fff;--foreground:#172d55;--muted-foreground:#60728f;--border:#cfd9e8;--ring:#1b55cf;--viz-series-1:#a34796;--viz-series-2:#247bbd;--viz-series-3:#2e9271;--viz-series-4:#c27724}
*{box-sizing:border-box}body{margin:0;padding:14px;background:var(--background);color:var(--foreground);font:14px/1.55 system-ui,sans-serif}
h2{margin:0;font-size:19px}h3{font-size:16px;overflow-wrap:anywhere}.text-small{font-size:12px;color:var(--muted-foreground)}
.viz-controls,.viz-row{display:flex;gap:8px;flex-wrap:wrap}.form-label{display:block;font-weight:600}
.form-select{display:block;margin-top:5px;min-height:38px;padding:7px;border:1px solid var(--border);border-radius:6px;background:#fff;color:var(--foreground);font:inherit}
.btn{min-height:36px;padding:7px 10px;border:1px solid var(--border);border-radius:6px;background:#fff;color:var(--foreground);font:inherit;cursor:pointer}
.btn[aria-pressed=true]{background:#e8f0ff;border-color:#1b55cf;color:#174fbb}.btn:focus-visible,.form-select:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
.card{padding:12px;border:1px solid var(--border);border-radius:8px}.cursor-interaction{cursor:pointer}.tabular-nums{font-variant-numeric:tabular-nums}
body #kg-trace-20261016 .kg-top{padding-right:0;margin-bottom:12px;gap:4px}#kg-trace-20261016 .kg-detail{overflow-wrap:anywhere}
@media(max-width:480px){body{padding:10px}.kg-stage .btn{font-size:12px;flex:1 1 42%}.kg-legend{font-size:11px}}
</style></head><body>""" + fragment + "</body></html>"


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
        })
    return sources


def build_question_graph(question: str) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("질문을 입력해 주세요.")
    # Both indexes are large; serialise loading/search and reuse recent results.
    with _LOCK:
        indexes, cache, configuration = _index_settings()
        key = (configuration, question)
        if key in _RESULTS:
            _RESULTS.move_to_end(key)
            return _RESULTS[key]
        get_search, embed_question, export_trace, semantics = _load_toolkit()
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
        result = {"question": question, "corpora": list(CORPORA), "sources": sources,
                  "html": _render_html({"datasets": datasets, "edge_semantics": semantics})}
        _RESULTS[key] = result
        while len(_RESULTS) > _CACHE_SIZE:
            _RESULTS.popitem(last=False)
        return result
