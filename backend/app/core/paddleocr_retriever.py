"""Hybrid retrieval over all five LCV6700 OCR manuals."""
import shutil

from pipeline.paddleocr_standalone import DEFAULT_DB, expand_md_sources, page_images, search


class PaddleOCRRetriever:
    def __init__(self, config):
        self.config = config

    def get_context(self, query: str, machine_code: str = "ALL"):
        if self.config.id != "yunam":
            return "", [], [], []
        # All five imported manuals explicitly cover these two LCV6700 machines.
        if machine_code not in {"ALL", "M049", "M050"}:
            return "", [], [], []
        results = search(DEFAULT_DB, query, 5, distinct_pages=True, hybrid=True)
        results = expand_md_sources(results)
        chunks, context = [], []
        for index, row in enumerate(results, 1):
            meta = row["metadata"]
            asset_root = DEFAULT_DB.parent / "assets" / meta["document_id"]
            image_paths = []
            for image, _label in page_images(meta["source_path"]):
                if image is None:
                    continue
                asset_root.mkdir(parents=True, exist_ok=True)
                target = asset_root / image.name
                if not target.exists() or target.stat().st_mtime_ns != image.stat().st_mtime_ns:
                    shutil.copy2(image, target)
                image_paths.append("data/" + target.relative_to(DEFAULT_DB.parents[1]).as_posix())
            metadata = {**meta, "source_kind": "paddleocr", "container_type": "texts",
                        "page_range": str(meta["page_num"]), "asset_path": "",
                        "page_image_paths": image_paths}
            chunks.append({"index": index, "retrieval_rank": index, "document": row["page_content"],
                           "metadata": metadata, "similarity": row["score"],
                           "distance": 1 - row["score"],
                           **{key: row.get(key) for key in
                              ("vector_rank", "bm25_rank", "bm25_score", "rrf_score")}})
            context.append(f"[chunk:{index}]\n[문서: {meta['source_doc_name']}]\n{row['page_content']}")
        # The UI exposes only images belonging to cited MD chunks, not every candidate.
        return "\n\n".join(context), [], [], chunks
