
from pathlib import Path
from typing import Any
from text.generate_chunks import process_document, save_jsonl

class TextParser:
    def __init__(self):
        pass
    
    def parse(self,txt_path: str, output_dir: dict[str, Any]) -> list[dict[str, Any]]:
        """
        
        """
        struct_dir = Path(output_dir.get("struct"))
        chunks = process_document(txt_path=txt_path)
        output_path = Path(struct_dir) / f"{Path(txt_path).stem}.jsonl"
        save_jsonl(chunks, output_path)
        return chunks