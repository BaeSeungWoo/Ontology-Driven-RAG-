"""Independent annotated PaddleOCR indexing and RAG: python -m pipeline.paddleocr_standalone."""

import argparse
import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request, urlopen

import numpy as np


DEFAULT_DB = Path(__file__).resolve().parent / "data/paddleocr_experiment/index_filtered.sqlite3"


def is_warning_icon(label):
    # Match the image's title, not warnings mentioned inside a machine diagram description.
    title = re.split(r"[:：]", label, maxsplit=1)[0].strip()
    return bool(re.fullmatch(
        r"(?:warning|caution|danger)(?:\s+(?:sign|symbol|icon|label|pictogram))*"
        r"|(?:위험\s*)?(?:경고|주의|위험)"
        r"|(?:(?:위험|경고|주의|고압|전기|안전|danger|warning|caution)\s*)+"
        r"(?:(?:기호|아이콘|표지|표시)\s*)+", title, re.IGNORECASE,
    ))


def remove_icon_annotations(text):
    return re.sub(
        r"(?m)^\*\*\[그림\]\s*(.*?)\*\*[^\n]*(?:\n[ \t]+-[^\n]*)*",
        lambda match: "" if is_warning_icon(match[1]) else match[0], text,
    )


class PageText(HTMLParser):
    """Keep Markdown prose, HTML table cell boundaries and image descriptions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.images = []
        self.image_labels = {}
        self.filtered_images = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            if is_warning_icon(attrs.get("alt", "")):
                self.filtered_images += 1
                return
            self.images.append(attrs.get("src", ""))
            self.image_labels[attrs.get("src", "")] = attrs.get("alt", "")
            if attrs.get("alt"):
                self.parts.append("\n[그림 설명] " + attrs["alt"] + "\n")
        elif tag in ("tr", "div", "p", "br", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in ("tr", "div", "p", "table"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def split_text(text, size, overlap):
    if not 0 <= overlap < size:
        raise ValueError("chunk-overlap must be >= 0 and smaller than chunk-size")
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start + overlap:
                end = boundary + 1
        if text[start:end].strip():
            yield text[start:end].strip()
        if end == len(text):
            break
        start = end - overlap


def load_chunks(root, size=1600, overlap=200):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8-sig"))
    chunks, counts = [], {"documents": 0, "pages": 0, "empty_pages": 0, "missing_images": 0, "filtered_images": 0}
    for doc in manifest["documents"]:
        folder = root / doc["id"]
        counts["documents"] += 1
        # Read numbered annotated pages only: all_pages.md and raw OCR duplicate them.
        for page in range(1, doc["pages"] + 1):
            source = folder / "annotated" / f"page_{page:04d}.md"
            raw = source.read_text(encoding="utf-8-sig")
            parser = PageText()
            parser.feed(raw)
            parser.close()
            text = remove_icon_annotations("".join(parser.parts))
            md_images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)
            counts["filtered_images"] += parser.filtered_images + sum(is_warning_icon(alt) for alt, _ in md_images)
            md_images = [(alt, src) for alt, src in md_images if not is_warning_icon(alt)]
            text = re.sub(r"!\[([^\]]*)\]\([^)]+\)",
                          lambda m: "" if is_warning_icon(m[1]) else "[그림 설명] " + m[1], text)
            text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()
            images = []
            for src in dict.fromkeys(parser.images + [src for _, src in md_images]):
                candidates = [source.parent / src, folder / "paddleocr" / src]
                asset = next((p.resolve() for p in candidates if p.is_file()), None)
                if asset:
                    images.append(str(asset))
                else:
                    counts["missing_images"] += 1
            counts["pages"] += 1
            counts["empty_pages"] += int(not text)
            for part, content in enumerate(split_text(text, size, overlap)):
                chunk_id = f"paddleocr:{doc['id']}:{page:04d}:{part:03d}"
                chunks.append({
                    "id": chunk_id,
                    "page_content": content,
                    "metadata": {
                        "chunk_id": chunk_id, "source_doc_name": doc["original_name"],
                        "document_id": doc["id"], "page_num": page, "page_range": str(page),
                        "source_path": str(source), "page_image_paths": images,
                        "parser": "paddleocr_annotated",
                    },
                })
    if not chunks:
        raise ValueError("No annotated text found")
    counts["chunks"] = len(chunks)
    return chunks, counts


def post_json(url, payload):
    request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=300) as response:
        result = json.load(response)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result


def embed(url, model, texts):
    result = post_json(url.rstrip("/") + "/api/embed", {
        "model": model, "input": texts, "truncate": False,
    })
    vectors = np.asarray(result["embeddings"], dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(texts) or not np.isfinite(vectors).all():
        raise ValueError("Invalid embedding response")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("Empty embedding vector")
    return vectors / norms


def build_index(db_path, chunks, model, url, batch_size=16):
    # Fingerprint prevents mixing changed sources/models with a previous or interrupted run.
    fingerprint = hashlib.sha256(json.dumps([model, chunks], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    db_path = Path(db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and tables != {"ocr_meta", "ocr_chunks"}:
            raise ValueError("Not a standalone OCR database; choose a new --db path")
        conn.execute("CREATE TABLE IF NOT EXISTS ocr_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS ocr_chunks (id TEXT PRIMARY KEY, record TEXT NOT NULL, vector BLOB NOT NULL)")
        saved = dict(conn.execute("SELECT key, value FROM ocr_meta"))
        if saved and saved.get("fingerprint") != fingerprint:
            raise ValueError("Source or embedding model changed; choose a new --db path")
        meta = {"fingerprint": fingerprint, "model": model, "url": url, "count": str(len(chunks)), "status": "building"}
        conn.executemany("INSERT OR REPLACE INTO ocr_meta VALUES (?, ?)", meta.items())
        conn.commit()
        existing = {r[0] for r in conn.execute("SELECT id FROM ocr_chunks")}
        pending = [c for c in chunks if c["id"] not in existing]
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            vectors = embed(url, model, ["passage: " + c["page_content"] for c in batch])
            conn.executemany("INSERT INTO ocr_chunks VALUES (?, ?, ?)", [
                (c["id"], json.dumps(c, ensure_ascii=False), v.tobytes()) for c, v in zip(batch, vectors)
            ])
            conn.commit()
            print(f"Indexed {len(existing) + offset + len(batch)}/{len(chunks)}", flush=True)
        conn.execute("UPDATE ocr_meta SET value='ready' WHERE key='status'")
        conn.commit()
    return db_path


def search(db_path, question, top_k=5, embedding_url=None, document_id=None, distinct_pages=False,
           hybrid=False):
    if top_k < 1:
        raise ValueError("top-k must be positive")
    path = Path(db_path).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
        meta = dict(conn.execute("SELECT key, value FROM ocr_meta"))
        rows = list(conn.execute("SELECT record, vector FROM ocr_chunks ORDER BY id"))
    if meta.get("status") != "ready" or len(rows) != int(meta["count"]):
        raise ValueError("Index is incomplete; resume the same index command first")
    if document_id:
        rows = [(record, vector) for record, vector in rows
                if json.loads(record)["metadata"].get("document_id") == document_id]
        if not rows:
            raise ValueError(f"No indexed document: {document_id}")
    query = embed(embedding_url or meta["url"], meta["model"], ["query: " + question])[0]
    vectors = np.stack([np.frombuffer(blob, dtype=np.float32) for _, blob in rows])
    scores = vectors @ query
    order = np.argsort(-scores, kind="stable")
    ranks = {}
    if hybrid:
        from rank_bm25 import BM25Okapi
        from backend.app.core.bm25_tokenizer import tokenize_for_bm25

        records = [json.loads(record) for record, _ in rows]
        bm25 = BM25Okapi([tokenize_for_bm25(r["page_content"]) for r in records])
        keyword_scores = bm25.get_scores(tokenize_for_bm25(question))
        candidate_k = max(top_k * 4, 20)
        for label, indices in (("vector", order),
                               ("bm25", np.argsort(-keyword_scores, kind="stable"))):
            for rank, idx in enumerate(indices[:candidate_k], 1):
                entry = ranks.setdefault(int(idx), {"vector_rank": None, "bm25_rank": None,
                                                    "bm25_score": None, "rrf_score": 0.0})
                entry[label + "_rank"] = rank
                entry["rrf_score"] += 1.0 / (60 + rank)
                if label == "bm25":
                    entry["bm25_score"] = float(keyword_scores[idx])
        order = sorted(ranks, key=lambda idx: ranks[idx]["rrf_score"], reverse=True)
    results = []
    seen = set()
    for idx in order:
        record = json.loads(rows[idx][0])
        page_key = record["metadata"].get("source_path")
        if distinct_pages and page_key in seen:
            continue
        seen.add(page_key)
        results.append({**record, "score": float(scores[idx]), **ranks.get(int(idx), {})})
        if len(results) == top_k:
            break
    return results


def expand_md_sources(results):
    """The vector hit selects a page MD; give its full filtered text to the LLM."""
    expanded = []
    for result in results:
        parser = PageText()
        parser.feed(Path(result["metadata"]["source_path"]).read_text(encoding="utf-8-sig"))
        parser.close()
        text = remove_icon_annotations("".join(parser.parts))
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)",
                      lambda m: "" if is_warning_icon(m[1]) else "[그림 설명] " + m[1], text)
        text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()
        expanded.append({**result, "matched_excerpt": result["page_content"], "page_content": text})
    return expanded


MD_IMAGE_POLICY = (
    "[MD 이미지 연결]\n각 검색 근거는 하나의 MD입니다. 답변에 실제 사용한 MD의 번호를 "
    "기존 [chunk:N] 인용 규칙대로 표시하세요. 해당 MD 내부 이미지는 HTML에서 자동 표시합니다. "
    "이미지 경로나 사용하지 않은 MD의 인용을 만들어내지 마세요."
)


def citation_numbers(response):
    return {int(n) for group in re.findall(r"\[(?:chunk:)?(\d+(?:\s*,\s*\d+)*)\]", response)
            for n in re.findall(r"\d+", group)}


def answer_messages(question, results, md_images=True):
    from backend.app.core.prompt_manager import PromptManager
    from backend.app.factories.config import CONFIGS

    context = "\n\n".join(
        f"[chunk:{i}]\n[문서: {r['metadata']['source_doc_name']}]\n{r['page_content']}"
        for i, r in enumerate(results, 1)
    )
    manager = PromptManager(str(Path(__file__).resolve().parents[1] / "backend/prompts/registry.json"))
    messages = manager.build("tech_expert", question, context=context, mode="rag",
                             m_info=CONFIGS["ollama_config"].machines["M050"])
    if md_images:
        messages[0]["content"] += "\n\n" + MD_IMAGE_POLICY
    return messages


def answer(question, results, model, url, md_images=True):
    from backend.app.factories.config import CONFIGS

    config = CONFIGS["ollama_config"].llm
    messages = answer_messages(question, results, md_images)
    # Same text framing as OllamaLLM._to_prompt in the existing application.
    roles = {"system": "[SYSTEM]", "user": "[USER]", "assistant": "[ASSISTANT]"}
    prompt = "".join(f"{roles[m['role']]}\n{m['content']}\n\n" for m in messages) + "[ASSISTANT]\n"
    response = post_json(url.rstrip("/") + "/api/generate", {
        "model": model, "stream": False, "think": False, "prompt": prompt,
        "options": {"temperature": config.temperature, "num_ctx": config.num_ctx,
                    "num_predict": config.max_tokens},
    })
    content = (response.get("response") or response.get("content")
               or response.get("message", {}).get("content", "")).strip()
    if not content:
        raise ValueError("LLM returned an empty answer")
    return content


def format_sources(results, response=None):
    selected = citation_numbers(response) if response is not None else set(range(1, len(results) + 1))
    lines = ["\nLLM이 인용한 MD 근거 (페이지는 PDF 첫 페이지부터 1):"]
    for i, result in enumerate(results, 1):
        if i not in selected:
            continue
        meta = result["metadata"]
        lines.append(f"[{i}] {meta['source_doc_name']} / p.{meta['page_num']} / score={result['score']:.4f}")
        excerpt = result["page_content"][:400]
        if len(result["page_content"]) > 400:
            excerpt += " … (이하 생략)"
        lines.append(f"    검색 문단 발췌: {excerpt}")
        lines.append(f"    원문: {meta['source_path']}")
    return "\n".join(lines)


def page_images(source):
    source = Path(source)
    parser = PageText()
    raw = source.read_text(encoding="utf-8-sig")
    parser.feed(raw)
    parser.close()
    labels = dict(parser.image_labels)
    labels.update({src: alt for alt, src in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", raw)})
    images = []
    for src, label in labels.items():
        if is_warning_icon(label):
            continue
        candidates = [source.parent / src, source.parent.parent / "paddleocr" / src]
        path = next((p.resolve() for p in candidates if p.is_file()), None)
        images.append((path, label or src))
    return images


def write_report(path, question, response, results):
    """Show images only from MDs explicitly cited by the answer, never adjacent pages."""
    def figures(source):
        cards = []
        for image, label in page_images(source):
            if image is None:
                cards.append(f"<p>이미지 파일을 찾을 수 없습니다: {escape(label)}</p>")
                continue
            mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
            cards.append(f'<figure><a href="{escape(image.as_uri())}"><img '
                         f'src="data:{mime};base64,{encoded}" alt="{escape(label)}"></a>'
                         f'<figcaption>{escape(label)}</figcaption></figure>')
        return "".join(cards)

    selected = citation_numbers(response)
    invalid = selected - set(range(1, len(results) + 1))
    sections = []
    candidates = []
    displayed_images = 0
    for i, result in enumerate(results, 1):
        meta = result["metadata"]
        source = Path(meta["source_path"]).resolve()
        heading = f'[{i}] {escape(meta["source_doc_name"])} · PDF {meta["page_num"]}페이지'
        if i not in selected:
            candidates.append(f'<details><summary>{heading} — 미채택</summary>'
                              f'<pre>{escape(result.get("matched_excerpt", result["page_content"]))}</pre></details>')
            continue
        cards = figures(source) if source.is_file() else '<p>원본 MD를 찾을 수 없습니다.</p>'
        displayed_images += cards.count('<img ')
        sections.append(f'<section id="source-{i}" class="adopted"><h3>{heading} — 채택</h3>'
                        f'<p>MD: {escape(source.name)} · 검색 점수 {result.get("score", 0):.4f}</p>'
                        f'<details><summary>LLM에 전달한 MD 본문 보기</summary><pre>{escape(result["page_content"])}</pre></details>'
                        f'<h4>이 MD 내부 이미지 (경고 아이콘 제외)</h4>'
                        f'{cards or "<p>이 MD에는 표시할 이미지가 없습니다. 다른 페이지 그림을 대신 붙이지 않습니다.</p>"}'
                        f'<a href="{escape(source.as_uri())}">원본 Markdown</a></section>')
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>OCR 질문답변</title>
<style>body{max-width:1050px;margin:40px auto;padding:0 24px;font:16px/1.7 system-ui;color:#17212b;background:#f4f6f8}
section{background:white;padding:24px;margin:20px 0;border:1px solid #d5dce3;border-radius:12px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}img{max-width:100%;max-height:720px;object-fit:contain}
figure{margin:20px 0;padding:16px;border:1px solid #ddd}figcaption{color:#465564}a{color:#1759a8}
.adopted{border-left:5px solid #167858}summary{cursor:pointer;font-weight:600}details{margin:16px 0}.notice{padding:16px;background:#fff1d6}</style>'''
    document += f'<h1>{escape(question)}</h1><nav><a href="#evidence">채택 MD와 이미지</a> · <a href="#candidates">미채택 후보</a></nav>'
    document += f'<p>검색 후보 {len(results)}개 MD → LLM 인용 {len(sections)}개 MD → 내부 이미지 {displayed_images}개</p>'
    document += '<p>채택은 답변의 [chunk:N] 인용 기준입니다. 이미지 자체를 LLM이 판독한 것은 아니며, 인용의 정확성은 원문과 대조해야 합니다.</p>'
    if invalid:
        document += f'<p class="notice">유효하지 않은 인용 번호: {sorted(invalid)}. 해당 근거/이미지는 표시하지 않습니다.</p>'
    document += f'<section><h2>답변</h2><pre>{escape(response)}</pre></section>'
    document += '<h2 id="evidence">LLM이 채택한 MD와 내부 이미지</h2>' + ("".join(sections) or '<p>LLM이 유효한 MD 번호를 인용하지 않았습니다. 이미지를 임의로 첨부하지 않습니다.</p>')
    document += '<h2 id="candidates">검색됐지만 채택하지 않은 후보</h2>' + ("".join(candidates) or '<p>없음</p>')
    document += '</html>'
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path


def main():
    from backend.app.factories.config import CONFIGS

    # OCR includes characters outside the Windows console's legacy code page.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    config = CONFIGS["ollama_config"]
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("index", help="Read annotated pages and build a separate index")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--db", type=Path, default=DEFAULT_DB)
    ingest.add_argument("--dry-run", action="store_true", help="Parse and report without calling models or writing a DB")
    ingest.add_argument("--chunk-size", type=int, default=1600)
    ingest.add_argument("--chunk-overlap", type=int, default=200)
    ingest.add_argument("--batch-size", type=int, default=16)
    ingest.add_argument("--embedding-model", default=config.embedding.model)
    ingest.add_argument("--embedding-url", default=config.get_embedding_base_url())
    for name in ("search", "ask"):
        command = commands.add_parser(name)
        command.add_argument("question")
        command.add_argument("--db", type=Path, default=DEFAULT_DB)
        command.add_argument("--top-k", type=int, default=5)
        command.add_argument("--embedding-url", help="Override saved embedding server, keeping the saved model")
        command.add_argument("--document-id", help="Restrict to one manifest document, e.g. 05_lcv_operation_maintenance")
        if name == "ask":
            command.add_argument("--llm-model", default=config.llm.model_name)
            command.add_argument("--llm-url", default=config.llm.base_url)
    args = parser.parse_args()
    try:
        if args.command == "index":
            if args.batch_size < 1:
                raise ValueError("batch-size must be positive")
            chunks, counts = load_chunks(args.input, args.chunk_size, args.chunk_overlap)
            print(json.dumps(counts, ensure_ascii=False, indent=2), flush=True)
            if not args.dry_run:
                print(build_index(args.db, chunks, args.embedding_model, args.embedding_url, args.batch_size))
        else:
            results = search(args.db, args.question, args.top_k, args.embedding_url,
                             document_id=args.document_id, distinct_pages=True)
            results = expand_md_sources(results)
            if args.command == "search":
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                response = answer(args.question, results, args.llm_model, args.llm_url)
                print(response)
                print(format_sources(results, response))
                report = write_report(args.db.parent / "answer.html", args.question, response, results)
                print(f'\n이미지 포함 결과: {report}\n브라우저로 열기: Start-Process "{report}"')
    except (OSError, ValueError, RuntimeError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
