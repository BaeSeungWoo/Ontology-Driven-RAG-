"""Search the delivered GraphIndexing integrated FANUC graph for legacy Yunam M005."""
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from pydantic import BaseModel

from .knowledge_graph import ROOT, KnowledgeGraphConfigurationError, KnowledgeGraphSearchError


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


def _node_title(titles, blocks, fallback):
    # Some PDF outline strings contain binary control characters even when the page text is intact.
    def readable(text):
        return not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ufffd]", text)

    valid = [title for title in titles if title.strip() and readable(title)]
    if valid:
        return " · ".join(valid)
    if any(titles):
        for block in blocks:
            for line in block.splitlines():
                if line.strip() and readable(line):
                    return line.strip()[:120]
    return fallback


def _coordinate_rows(content):
    """Decode the Rn | Cn: text representation used by controller manuals."""
    rows = []
    for line in content.strip().splitlines():
        match = re.fullmatch(r"R\d+\s*\|\s*C(\d+):\s*(.*)", line.strip())
        if not match:
            return None
        fields = [match[1], *re.split(r"\s*\|\s*C(\d+):\s*", match[2])]
        row = []
        for column, value in zip(fields[::2], fields[1::2]):
            index = int(column)
            if index < len(row):
                return None
            row.extend({"text": ""} for _ in range(index - len(row)))
            row.append({"text": value.strip()})
        rows.append(row)
    return rows


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
        nodes[node] = dict(kind="passage", label=_node_title(page["titles"], page["blocks"], f"본문 {number}"),
                           content="\n".join(page["blocks"]), pages=str(number), document=data["document"])
        if number - 1 in page_ids:
            links.append((page_ids[number - 1], node))
    for table in data["tables"]:
        node = len(nodes)
        content, rows = table["content"], table.get("rows")
        if re.search(r"<(?:table|tr)\b", content, re.I):
            if not rows:
                from bs4 import BeautifulSoup
                markup = BeautifulSoup(content, "html.parser")
                rows = [[dict(text=cell.get_text(" ", strip=True),
                              rowspan=int(cell.get("rowspan") or 1), colspan=int(cell.get("colspan") or 1))
                         for cell in tr.find_all(["th", "td"], recursive=False)] for tr in markup.select("tr")]
                rows = [row for row in rows if row]
        elif not rows:
            rows = _coordinate_rows(content)
        if rows:
            content = "\n".join(" | ".join(cell["text"] for cell in row) for row in rows)
        label = _node_title([table["label"]], [], f"표 {table['page']}")
        nodes[node] = dict(kind="table", label=label, content=content, rows=rows,
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


class ActionQuery(BaseModel):
    action_requested: bool
    situation_ko: list[str]
    situation_en: list[str]
    goal: str


class SearchItem(BaseModel):
    label: str
    english_noun: str
    synonyms: list[str]


class ItemQuery(BaseModel):
    condition_ko: str
    condition_en: str
    items: list[SearchItem]


def _search_terms(question, model_key):
    import asyncio
    from app.core.graph_model import graph_completion
    from app.factories.config import CONFIGS
    if re.search(r"각각|각 항목|[,·、]|[?？]\s*\S|및\s|(?:와|과|하고|이랑|랑)\s|그리고|\band\b|\beach\b", question, re.I):
        reply, _ = asyncio.run(graph_completion(CONFIGS[model_key], [
            {"role": "system", "content": "Identify independently requested answer subjects in a manual question. "
             "If only one result is requested, including one procedure, fault or a difference between two concepts, return empty items. "
             "For multiple subjects, copy each subject verbatim from the question as label. Supply its short Korean and English manual "
             "names, including singular/plural (e.g. axis, axes). english_noun is the English head noun alone. condition_ko and "
             "condition_en are the short equivalent names of the common event (e.g. power failure), not whole clauses or operator "
             "verbs. If there is no common event use empty strings. Do not predict outcomes."},
            {"role": "user", "content": question}], ItemQuery))
        parts = ItemQuery.model_validate_json(reply)
        items = {i.label.strip(): [i.label, i.english_noun, *i.synonyms] for i in parts.items if i.label.strip() and i.label.strip() in question}
        if len(items) > 1:
            return "items", question, parts.condition_en, "", "", ([], []), ([], []), (items, [parts.condition_ko, parts.condition_en])
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
    if re.search(r"어떻|어떡|어찌|해야|조치|대처|방법|절차|순서|주의할|주의점|유의사항|복구|재가동|"
                   r"(?:무엇|뭘|무슨|어떤).{0,16}(?:확인|누르|점검|조작|해야)|"
                   r"다시\s*(?:시작|가동)|how (?:do|can|should|to)|what (?:to do|should)|precautions|procedure", question, re.I):
        intent, _ = asyncio.run(graph_completion(CONFIGS[model_key], [
            {"role": "system", "content": "Does the user explicitly ask what the operator should DO, how to perform a task, "
             "or which precautions and steps to follow in a stated situation? For a bare symptom report, a definition, "
             "comparison, number, indicator meaning, required access level, or what happens when a button is pressed, "
             "return action_requested=false. For an action request give equivalent short Korean and English terms for "
             "the initiating event or component ONLY, excluding the goal, unrelated faults, and broader synonyms. "
             "goal is the requested action and its short manual search terms in both languages. Do not give instructions."},
            {"role": "user", "content": question}], ActionQuery))
        action = ActionQuery.model_validate_json(intent)
        if action.action_requested:
            return ("action", question + " " + plan["ko"] + " " + action.goal, question + " " + plan["en"] + " " + action.goal, code, "",
                    (action.situation_ko, []), (action.situation_en, []), None)
    ko = question if scope == "other" else question + " " + plan["ko"]
    symptom = str(plan.get("symptom") or "").strip()
    if scope != "specific" or symptom.casefold() not in question.casefold():
        symptom = ""
    def fault_terms(lang):
        if scope != "specific" or code:
            return (), ()
        return plan[f"targets_{lang}"], plan[f"states_{lang}"]

    return scope, ko, question + " " + plan["en"], code, symptom, fault_terms("ko"), fault_terms("en"), None




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
        scope, korean_query, english_query, code, symptom, korean_fault, english_fault, item_query = _search_terms(question, model_key)
    except Exception as exc:
        raise KnowledgeGraphSearchError("영문 매뉴얼 검색어를 생성하지 못했습니다.") from exc
    datasets, sources = [], []
    if machine:
        dataset, evidence = _rank(machine, question, korean_query, "dhf8000", "DHF8000 장비 조작설명서", 0, scope, code, korean_fault, item_query)
        datasets.append(dataset)
        sources.extend(evidence)
    dataset, evidence = _rank(controller, question, english_query, "fanuc", "FANUC 제어기 매뉴얼", len(sources), scope, code, english_fault, item_query)
    datasets.append(dataset)
    sources.extend(evidence)
    return dict(scope=scope, items=item_query[0] if item_query else {}, symptom=symptom, alarm=code, targets={"dhf8000": korean_fault[0], "fanuc": english_fault[0]},
                question=question, corpora=[d["id"] for d in datasets], sources=sources,
                snapshot=sha256(json.dumps([question, sources]).encode()).hexdigest(),
                datasets=datasets)


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
        scope, ko, en, code, symptom, ko_fault, en_fault, item_query = _search_terms(question, model_key)
    except Exception as exc:
        raise KnowledgeGraphSearchError("매뉴얼 검색어를 생성하지 못했습니다.") from exc
    fault = tuple(list(a) + list(b) for a, b in zip(ko_fault, en_fault))
    for key, name in documents:
        path = folder / "documents" / (key + ".json")
        index = _equipment_index(path, key)
        dataset, evidence = _rank(index, question, ko + " " + en, name, name, len(sources), scope, code, fault, item_query)
        datasets.append(dataset)
        sources.extend(evidence)
        targets[name] = fault[0]
    return dict(scope=scope, items=item_query[0] if item_query else {}, symptom=symptom, alarm=code, targets=targets,
                question=question, corpora=[d["id"] for d in datasets], sources=sources,
                snapshot=sha256(json.dumps([question, sources]).encode()).hexdigest(),
                datasets=datasets)


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


def _action_column(rows, target):
    """Read the chosen condition down a comparison table, including merged cells."""
    if not any(target.fullmatch(cell["text"].strip()) for row in rows[:3] for cell in row[1:]):
        return ""
    spans = {}
    for r, row in enumerate(rows):
        col = 0
        for cell in row:
            while (r, col) in spans:
                col += 1
            for dy in range(cell.get("rowspan", 1)):
                for dx in range(cell.get("colspan", 1)):
                    spans[r + dy, col + dx] = cell["text"]
            col += cell.get("colspan", 1)
    width = 1 + max(c for _, c in spans)
    grid = [[spans.get((r, c), "") for c in range(width)] for r in range(len(rows))]
    for i, row in enumerate(grid[:3]):
        for col, header in enumerate(row[1:], 1):
            if target.fullmatch(header.strip()) and i + 1 < len(grid):
                first_value = next((j for j, value in enumerate(row) if value != row[0]), col)
                lines = [header]
                for line in grid[i+1:]:
                    label = " · ".join(dict.fromkeys(line[:first_value]))
                    lines.append(f"{label} | {line[col]}")
                return "\n".join(lines)
    return ""


def _rank(index, question, query, corpus, title, start, scope, code, fault, item_query=None):
    import numpy as np
    nodes, contexts, vectorizer, terms, transition, counts = index
    weights = (terms @ vectorizer.transform([query]).T).toarray().ravel()
    excerpts = {}
    action_evidence = {}
    item_hits = {}
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
    elif scope == "action" and target:
        message = re.search(r"\b[A-Za-z]+(?:[ \t]+[A-Za-z]+){2,}\b", question)
        for pos, i in enumerate(contexts):
            node = nodes[i]
            body = node["content"]
            exact_message = message and re.search(re.escape(message.group()).replace(r"\ ", r"\s+"), body, re.I)
            match = exact_message or target.search(body)
            if not match:
                continue
            rows = node.get("rows") or []
            column = _action_column(rows, target)
            step_table = rows and re.search(r"순서|절차|step", body.splitlines()[0], re.I)
            section = re.sub(r"^[\d.()\s]+", "", node["label"])
            # The initiating condition belongs to the procedure itself, not a later incidental step.
            applicable_steps = step_table and (target.match(section) or any(
                len(row) > 1 and target.match(row[1]["text"].strip()) for row in rows[1:3]))
            line = next((line for line in body.splitlines() if target.search(line) and re.search(
                r"반드시|확인한\s*후|확인하신\s*후|확인하고|before proceeding|make sure", line, re.I)), "")
            detail = next((s for s in re.split(r"(?<=[.!?])\s+|\n", body) if target.search(s) and re.search(
                r"(?:해제|복귀|조작)할\s*때(?:는|에).*(?:버튼|스위치)", s)), "") if not rows else ""
            start_at = max(0, match.start() - 160) if not step_table else 0
            text = column or (body if applicable_steps else body[start_at:start_at + 1400])
            if not column and not step_table and re.search(r"\.{3,}\s*\d+", text):
                weights[pos] = 0
                continue
            excerpts[i] = node["label"] + "\n" + text
            if exact_message:
                weights[pos] += 4
                if rows:
                    # Message tables may contain several numbered alarms on a single page.
                    header = re.compile(r"^\s*\d+\s*\|")
                    lines = body.splitlines()
                    for n, value in enumerate(lines):
                        if header.match(value) and message.group().casefold() in value.casefold():
                            end = next((j for j in range(n + 1, len(lines)) if header.match(lines[j])), len(lines))
                            excerpts[i] = "\n".join(lines[n:end])
                            action_evidence[i] = "message"
                            break
            if detail:
                action_evidence[i] = "operation_detail"
                excerpts[i] = detail
                weights[pos] += 2
            elif column or applicable_steps or (line and not rows):
                action_evidence[i] = "comparison" if column else "steps" if applicable_steps else "precaution"
                if line and not rows:
                    excerpts[i] = section + "\n" + line
                weights[pos] += 2
            elif re.search(r"주의|확인|해제|준비|반드시|caution|check|release", text, re.I):
                weights[pos] += 0.18
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
    if item_query:
        items, condition_terms = item_query
        # The manual can separate the event name from its verb (e.g. "press ... button").
        en_words = condition_terms[-1].split()
        condition = _term_pattern([*condition_terms, *(" ".join(pair) for pair in zip(en_words, en_words[1:]))])
        item_patterns = [_term_pattern(aliases) for aliases in items.values()]
        for label, term in zip(items, item_patterns):
            best = []
            for pos, i in enumerate(contexts):
                body = nodes[i]["content"]
                if not term.search(body) or (condition and not condition.search(body)):
                    continue
                best_excerpt = ""
                coverage = 0
                for hit in term.finditer(body):
                    begin = max(0, hit.start() - 650)
                    end = min(len(body), hit.end() + 500)
                    excerpt = body[begin:end]
                    if condition and not condition.search(excerpt):
                        continue
                    # Prefer passages that also cover the other subjects under the same condition.
                    count = sum(bool(p.search(excerpt)) for p in item_patterns)
                    if count > coverage:
                        coverage, best_excerpt = count, excerpt
                    if count == len(items):
                        break
                if best_excerpt:
                    best.append((weights[pos] + coverage, pos, best_excerpt))
            for score, pos, excerpt in sorted(best, key=lambda hit: -hit[0])[:2]:
                item_hits.setdefault(pos, {})[label] = excerpt
        positions = list(item_hits)
        for pos, matches in item_hits.items():
            weights[pos] += len(matches)
            excerpts[contexts[pos]] = "\n".join(dict.fromkeys(matches.values()))
    else:
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
        if item_query:
            final = sorted(direct, key=lambda i: -scores[i])

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
        if item_query:
            source["item_hits"] = next(matches for pos, matches in item_hits.items() if contexts[pos] == node_id)
        if node_id in action_evidence:
            source["action_evidence"] = action_evidence[node_id]
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
