"""Search the delivered GraphIndexing integrated FANUC graph for legacy Yunam M005."""
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from pydantic import BaseModel

from .knowledge_graph import ROOT, KnowledgeGraphConfigurationError, KnowledgeGraphSearchError, _render_html


@lru_cache(maxsize=1)
def _load(directory):
    import numpy as np
    import pyarrow.parquet as pq
    from scipy import sparse
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf8"))
    graph = directory / manifest["graph"]
    adjacency = sparse.load_npz(graph / "integrated_adjacency.npz").tocsr()
    model = directory / manifest["hipporag_model_dir"]

    def content(kind):
        projection = directory / f"{kind}_content.parquet"
        path = projection if projection.exists() else model / f"{kind}_embeddings/vdb_{kind}.parquet"
        return pq.read_table(path, columns=["content"])["content"].to_pylist()

    corpus = json.loads((directory / manifest["text_corpus"]).read_text(encoding="utf8"))
    nodes = {}
    passages = np.load(graph / "passage_node_indices.npy")
    for node, record in zip(passages, content("chunk"), strict=True):
        number, _, body = record.partition(":")
        row = corpus[int(number)]
        if body != row["text"]:
            raise ValueError("Passage provenance mismatch")
        nodes[int(node)] = dict(kind="passage", label=row["title"], content=body,
                                document=row["source_doc"], pages=row["pages"]["range"])
    entities = np.load(graph / "entity_node_indices.npy")
    for node, label in zip(entities, content("entity"), strict=True):
        nodes[int(node)] = dict(kind="entity", label=label, content=label)
    offset = len(nodes)
    tables = np.load(graph / "table_idxs.npy")
    with (directory / manifest["tables"]).open(encoding="utf8") as file:
        for pos, (line, table_id) in enumerate(zip(file, tables, strict=True)):
            row = json.loads(line)
            if row["table_idx"] != table_id:
                raise ValueError("Table node mismatch")
            meta, table = row["metadata"], row["table"]
            page = meta.get("merge", {}).get("page_range") or meta.get("page_range") or meta.get("page_no", "")
            rows = [table["header"], *table["rows"]]
            nodes[offset + pos] = dict(kind="table", label=row["caption"], document=meta["document"],
                pages=str(page.get("range", "") if isinstance(page, dict) else page),
                content=row["caption"] + "\n" + "\n".join(" | ".join(map(str, cells)) for cells in rows))
    if adjacency.shape != (len(nodes), len(nodes)) or set(nodes) != set(range(len(nodes))):
        raise ValueError("Graph node mappings do not align")
    contexts = np.concatenate([passages, offset + np.arange(len(tables))])
    vectorizer = TfidfVectorizer(sublinear_tf=True, stop_words="english", dtype=np.float32)
    terms = vectorizer.fit_transform(nodes[int(i)]["content"] for i in contexts)
    transition = normalize(adjacency.astype(np.float32), norm="l1", axis=1, copy=False)
    return nodes, contexts, vectorizer, terms, transition, dict(
        entities=len(entities), passages=len(passages), tables=len(tables))


@lru_cache(maxsize=8)
def _equipment_index(path, modified):
    import numpy as np
    from scipy import sparse
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    data = json.loads(path.read_text(encoding="utf8"))
    nodes, page_ids, links = {}, {}, []
    for page in sorted(data["pages"], key=lambda item: item["page"]):
        number = page["page"]
        node = len(nodes)
        page_ids[number] = node
        nodes[node] = dict(kind="passage", label=" · ".join(page["titles"]) or f"본문 {number}",
                           content="\n".join(page["blocks"]), pages=str(number), document=data["document"])
        if number - 1 in page_ids:
            links.append((page_ids[number - 1], node))
    for table in data["tables"]:
        node = len(nodes)
        nodes[node] = dict(kind="table", label=table["label"], content=table["content"], rows=table.get("rows"),
                           pages=str(table["page"]), document=data["document"])
        links.append((page_ids[table["page"]], node))
    left, right = zip(*links) if links else ((), ())
    adjacency = sparse.csr_matrix((np.ones(2 * len(links), dtype=np.float32),
                                   (left + right, right + left)), shape=(len(nodes), len(nodes)))
    max_length = max((len(node["content"].strip()) for node in nodes.values()), default=0)
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(min(2, max(1, max_length)), 4),
                                 sublinear_tf=True, dtype=np.float32)
    contexts = np.array([i for i, node in nodes.items() if node["content"].strip()])
    # Dot-leader entries repeat procedure titles in the contents pages.
    terms = vectorizer.fit_transform(
        re.sub(r"(?m)^.*\.{3,}\s*[\d-]+\s*$", "", nodes[i]["content"]) for i in contexts
    )
    return (nodes, contexts, vectorizer, terms, normalize(adjacency, norm="l1"),
            dict(entities=0, passages=len(page_ids), tables=len(data["tables"])))


class ManualQuery(BaseModel):
    scope: str
    ko: str
    en: str
    alarm: str
    symptom: str
    targets_ko: list[str]
    targets_en: list[str]
    states_ko: list[str]
    states_en: list[str]


def _search_terms(question, model_key):
    import asyncio
    from app.core.graph_model import graph_completion
    from app.factories.config import CONFIGS
    messages = [{"role": "system", "content":
                "Classify the user's CNC manual search. Output JSON with scope, ko, en, alarm, symptom, "
                "targets_ko, targets_en, states_ko, states_en. "
                "scope is general_incident only for unspecified abnormal operation or a broad question about "
                "what to do when a problem occurs. A named symptom, part or alarm is specific. Otherwise use other. "
                "ko and en are short Korean and English retrieval terms, not answers. For general_incident "
                "search general operating precautions, stopping operation, reporting abnormalities and conditions "
                "for resuming. For specific symptoms preserve the symptom and component; do not invent a cause. "
                "For fault questions, targets are short equivalent manual names of the affected function or component. "
                "States are short equivalent manual terms for the observed behavior alone. Use up to four strings per "
                "array in the specified language. For example for a pump that will not start, separate 펌프 from "
                "기동 불가, 작동 불가, 불가능. For a vibrating spindle separate 주축 from 진동. Include no conjectured causes. "
                "If the target is unspecified leave target arrays empty. For non-fault questions leave all arrays empty. "
                "symptom is a short exact quote of the observed symptom for answer generation, empty for non-fault questions. "
                "alarm is the exact alarm code from the question, or an empty string. Never use a machine model, "
                "parameter or page number as an alarm code."}, {"role": "user", "content": question}]
    content, _ = asyncio.run(graph_completion(CONFIGS[model_key], messages, ManualQuery))
    plan = ManualQuery.model_validate_json(content).model_dump()
    scope = plan["scope"]
    if scope not in ("general_incident", "specific", "other"):
        raise ValueError("Unknown retrieval scope")
    code = str(plan.get("alarm") or "").strip()
    if not re.fullmatch(r"[A-Za-z]*[0-9]+(?:\.[0-9]+)?", code) or code.casefold() not in question.casefold():
        code = ""
    if not code and re.search(r"알람|경보|alarm|\balm\b", question, re.I):
        numbers = re.findall(r"(?<![\w.])([0-9]{3,5})(?![0-9.])", question)
        if len(numbers) == 1:
            code = numbers[0]
    if code:
        scope = "specific"
    ko = question if scope == "other" else question + " " + plan["ko"]
    symptom = str(plan.get("symptom") or "").strip()
    if scope != "specific" or symptom.casefold() not in question.casefold():
        symptom = ""
    def fault_terms(lang):
        if scope != "specific" or code:
            return (), ()
        return plan[f"targets_{lang}"], plan[f"states_{lang}"]

    return scope, ko, question + " " + plan["en"], code, symptom, fault_terms("ko"), fault_terms("en")




_search_lock = Lock()


def controller_graph(question, model_key):
    with _search_lock:
        equipment = ROOT / "backend/data/graph_indexes/yunam_origin/M005/dhf8000.json"
        return _controller_graph(question, model_key, equipment, equipment.stat().st_mtime_ns if equipment.exists() else None)


@lru_cache(maxsize=8)
def _controller_graph(question, model_key, equipment, modified):
    directory = Path(os.getenv("GRAPH_INDEX_M005_CONTROLLER_DIR") or
                     ROOT / "backend/data/graph_indexes/yunam_origin/M005/controller_manuals")
    try:
        controller = _load(directory)
        machine = _equipment_index(equipment, modified) if modified is not None else None
    except (ImportError, OSError, KeyError, ValueError) as exc:
        raise KnowledgeGraphConfigurationError("FANUC GraphIndexing 인덱스를 읽지 못했습니다.") from exc
    try:
        scope, korean_query, english_query, code, symptom, korean_fault, english_fault = _search_terms(question, model_key)
    except Exception as exc:
        raise KnowledgeGraphSearchError("영문 매뉴얼 검색어를 생성하지 못했습니다.") from exc
    datasets, sources = [], []
    if machine:
        dataset, evidence = _rank(machine, question, korean_query, "dhf8000", "DHF8000 장비 조작설명서", 0, scope, code, korean_fault)
        datasets.append(dataset)
        sources.extend(evidence)
    dataset, evidence = _rank(controller, question, english_query, "fanuc", "FANUC 제어기 매뉴얼", len(sources), scope, code, english_fault)
    datasets.append(dataset)
    sources.extend(evidence)
    return dict(scope=scope, symptom=symptom, alarm=code, targets={"dhf8000": korean_fault[0], "fanuc": english_fault[0]},
                question=question, corpora=[d["id"] for d in datasets], sources=sources,
                snapshot=sha256(json.dumps([question, sources]).encode()).hexdigest(),
                html=_render_html({"datasets": datasets}))


def factory_graph(question, model_key, factory_id, machine):
    folder = ROOT / "pipeline/data" / factory_id / "graph"
    path = folder / "catalog.json"
    if not path.exists():
        return None
    catalog = json.loads(path.read_text(encoding="utf8"))
    ids = catalog["machines"].get(machine, [])
    return _factory_graph(question, model_key, folder, tuple((key, catalog["documents"][key]) for key in ids))


@lru_cache(maxsize=8)
def _factory_graph(question, model_key, folder, documents):
    datasets, sources, targets = [], [], {}
    try:
        scope, ko, en, code, symptom, ko_fault, en_fault = _search_terms(question, model_key)
    except Exception as exc:
        raise KnowledgeGraphSearchError("매뉴얼 검색어를 생성하지 못했습니다.") from exc
    fault = tuple(list(a) + list(b) for a, b in zip(ko_fault, en_fault))
    for key, name in documents:
        path = folder / "documents" / (key + ".json")
        index = _equipment_index(path, key)
        dataset, evidence = _rank(index, question, ko + " " + en, name, name, len(sources), scope, code, fault)
        datasets.append(dataset)
        sources.extend(evidence)
        targets[name] = fault[0]
    return dict(scope=scope, symptom=symptom, alarm=code, targets=targets,
                question=question, corpora=[d["id"] for d in datasets], sources=sources,
                snapshot=sha256(json.dumps([question, sources]).encode()).hexdigest(),
                html=_render_html({"datasets": datasets}) if datasets else "<p>연결된 매뉴얼이 없습니다.</p>")


def _term_pattern(terms):
    patterns = []
    for term in terms:
        words = term.strip().split()
        if not words:
            continue
        pattern = r"\s+".join(map(re.escape, words))
        if re.fullmatch(r"[가-힣\s]+", term):
            pattern = r"[^\S\n]*".join(map(re.escape, "".join(words)))
        elif term.isascii():
            pattern = r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])"
        patterns.append(pattern)
    return re.compile("|".join(patterns), re.I) if patterns else None


def _rank(index, question, query, corpus, title, start, scope, code, fault):
    import numpy as np
    nodes, contexts, vectorizer, terms, transition, counts = index
    weights = (terms @ vectorizer.transform([query]).T).toarray().ravel()
    excerpts = {}
    target, state = map(_term_pattern, fault)
    if code:
        pattern = re.compile(r"(?<![#a-z0-9])" + re.escape(code) + r"(?![a-z0-9])", re.I)
        for pos, i in enumerate(contexts):
            body = nodes[i]["content"]
            match = pattern.search(body)
            if match and corpus == "fanuc":
                nearby = body[max(0, match.start()-120):match.end()+120]
                if not re.search(r"alarm|\bALM\b", nearby, re.I):
                    match = None
            if match:
                weights[pos] += 1
                if nodes[i]["kind"] == "table":
                    rows = body.splitlines()
                    excerpts[i] = "\n".join(line for line in rows if pattern.search(line))[:1100]
                else:
                    begin = max(0, match.start() - 160)
                    excerpts[i] = body[begin:begin + 1100]
            else:
                weights[pos] = 0
    elif target or state:
        keyword = target or state
        for pos, i in enumerate(contexts):
            body = nodes[i]["content"]
            match = keyword.search(body)
            if match:
                weights[pos] += 1
                if target and state:
                    for occurrence in keyword.finditer(body):
                        begin = max(body.rfind("\n", 0, occurrence.start()) + 1, occurrence.start() - 100)
                        nearby = body[begin:occurrence.end() + 100].split("\n", 1)[0]
                        if state.search(nearby):
                            match = occurrence
                            weights[pos] += 1
                            break
                # Numbered manual subsections can describe different operating conditions on the same page.
                boundaries = [m.start() for m in re.finditer(r"(?m)^\s*[①-⑳]", body)]
                begin = max([0, match.start() - 200, *(n for n in boundaries if n <= match.start())])
                end = next((n for n in boundaries if n > match.start()), len(body))
                excerpts[i] = body[begin:min(begin + 1100, end)]
            else:
                weights[pos] = 0
    elif scope == "general_incident":
        # Search conditional operating instructions rather than alarm/table entries.
        condition = re.compile(r"의심스러운 상황|긴급.{0,12}(?:정지|멈)|비상정지.{0,22}(?:누르|눌러)|"
                               r"(?:이상|비정상).{0,12}(?:상황|발생|발견)|"
                               r"abnormal(?:ity|ities| condition)|in an emergency", re.I)
        action = re.compile(r"가동.{0,4}중지|기계.{0,8}(?:정지|멈)|관리 책임자|주축.{0,12}정지|"
                            r"stop the machine|stop operation|press (?:the )?emergency stop", re.I)
        weights.fill(0)
        owners, blocks = [], []
        for pos, i in enumerate(contexts):
            if nodes[i]["kind"] != "passage":
                continue
            paragraphs = nodes[i]["content"].splitlines()
            lines = []
            for n, line in enumerate(paragraphs):
                if condition.search(line) and action.search(line):
                    if n + 1 < len(paragraphs) and not re.search(r"[.!?。]$", line.rstrip()):
                        line += " " + paragraphs[n + 1]
                    lines.append(line)
            if lines:
                owners.append(pos)
                blocks.append("\n".join(lines))
                excerpts[i] = blocks[-1][:1100]
        if blocks:
            general_query = (query + " 기계 가동 중지 관리 책임자 문제 해결 후 가동 긴급 정지"
                             if corpus == "dhf8000" else query + " stop the machine abnormal condition emergency stop")
            similarities = vectorizer.transform(blocks) @ vectorizer.transform([general_query]).T
            weights[owners] = similarities.toarray().ravel()
    positions = np.argsort(-weights, kind="stable")[:5]
    direct = [int(contexts[p]) for p in positions if weights[p] > 0]
    seed = np.zeros(len(nodes), dtype=np.float32)
    scores = seed.copy()
    final = []
    if direct:
        seed[direct] = weights[positions[:len(direct)]]
        seed /= seed.sum()
        scores = seed.copy()
        dangling = np.diff(transition.indptr) == 0
        for _ in range(50):
            updated = .7 * seed + .3 * (transition.T @ scores + seed * scores[dangling].sum())
            delta = np.abs(updated - scores).sum()
            scores = updated
            if delta < 1e-6:
                break
        final = [int(contexts[p]) for p in np.argsort(-scores[contexts], kind="stable")[:5]
                 if scores[contexts[p]] > 0 and (not (code or target or state or scope == "general_incident") or weights[p] > 0)]

    shown = set(direct + final)
    for node in final:
        row = transition.getrow(node)
        shown.update(int(row.indices[i]) for i in np.argsort(-row.data)[:2])
    graph_nodes = [dict(id="query", kind="query", label="질문", content=question)]
    edges = [dict(source="query", target=str(i), kind="direct") for i in direct]
    for i in sorted(shown):
        graph_nodes.append(dict(nodes[i], id=str(i), final=i in final, dense=i in direct,
            dense_rank=direct.index(i)+1 if i in direct else None, ppr=i in final,
            ppr_rank=final.index(i)+1 if i in final else None, ppr_score=float(scores[i])))
        edges.extend(dict(source=str(i), target=str(j), kind="context")
                     for j in transition.getrow(i).indices if j in shown and j > i)
    for n, edge in enumerate(edges):
        edge["id"] = f"edge{n}"

    def view(ids):
        return dict(nodes=ids, edges=[e["id"] for e in edges if e["source"] in ids and e["target"] in ids])
    overall = view([n["id"] for n in graph_nodes])
    dataset = dict(id=corpus, title=title, question=question, nodes=graph_nodes,
        edges=edges, index_counts=counts, views=dict(overall=overall,
        dense=view(["query", *map(str, direct)]), ppr=view(list(map(str, final)))))
    sources = [dict(index=start+n, corpus=corpus, kind=nodes[i]["kind"], node_id=str(i), document_name=nodes[i]["document"],
                    page=str(nodes[i]["pages"]), excerpt=excerpts.get(i, nodes[i]["content"][:1100]))
               for n, i in enumerate(final, 1)]
    for source, node_id in zip(sources, final):
        if source["kind"] == "table":
            node = nodes[node_id]
            rows = node.get("rows")
            if not rows:
                lines = node["content"].splitlines()
                if lines and lines[0] == node["label"]:
                    lines = lines[1:]
                rows = [[{"text": cell.strip()} for cell in line.split(" | ")] for line in lines]
            source["rows"] = rows
    return dataset, sources
