"""Web entry point with progress events and drawing previews."""
import json
import os
from pathlib import Path
import sys
import uuid

from qa_portable import load_config, worker
from runtime_support import report_progress


def run(request):
    config = load_config(request["config_path"])
    config.update(model=request["model"], base_url=request["base_url"], max_tokens=request["max_tokens"],
                  provider="vllm", api_key_env="OPENAI_API_KEY")
    os.environ.update(
        VLLM_API_BASE=config["base_url"], VLLM_API_MODEL=config["model"], LLM_NAME=config["model"],
        GRAPHRAG_PROVIDER=config["provider"], GRAPHRAG_CONTEXT_TOKENS=str(config["context_tokens"]),
        GRAPHRAG_MAX_TOKENS=str(config["max_tokens"]), GRAPHRAG_MAX_IMAGES=str(config["max_images"]),
        OPENAI_API_KEY=os.getenv(config["api_key_env"], ""),
    )
    run_id = uuid.uuid4().hex
    run_dir = Path(config["output_dir"]) / run_id
    run_dir.mkdir(parents=True)
    payload = worker({**request, "config": config, "run_dir": str(run_dir), "persona_type": "engineer"})
    if not payload.get("ok"):
        return payload
    result = payload["result"]
    report_progress("답변에 연결할 도면 미리보기를 준비하는 중")
    import pypdfium2
    asset_root = Path(__file__).resolve().parents[3] / "pipeline" / "data"
    preview_dir = Path(config["output_dir"]).parent / "previews" / run_id
    preview_dir.mkdir(parents=True)
    with pypdfium2.PdfDocument(config["pdf"]) as pdf:
        for chunk in result["chunks"]:
            meta = chunk["metadata"]
            page_number = int(meta["page"])
            target = preview_dir / f"page-{page_number}.png"
            page = pdf[page_number - 1]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil()
            try:
                image.save(target)
            finally:
                image.close()
                bitmap.close()
                page.close()
            meta.update(asset_path=target.relative_to(asset_root).as_posix(), container_type="pictures", machine_code=request["machine_code"], site_id=request["factory_id"])
            meta.pop("pdf", None)
            meta.pop("pdf_uri", None)
    return {"ok": True, "result": {key: result[key] for key in
            ("answer", "chunks", "images", "tables", "grounding_reviewed")}}


if __name__ == "__main__":
    os.environ["ELECTRICAL_QA_PROGRESS"] = "1"
    print(json.dumps({"type": "result", "data": run(json.load(sys.stdin))}, ensure_ascii=False), flush=True)
