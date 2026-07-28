from __future__ import annotations

from typing import Any

class ChunkRefiner:
    """Docling, Upstage 추출물에서 변환된 jsonl 형태의 구조화된 청크 객체 들을
    실제 VectorDB에 들어갈 청크로 변환하는 클래스

    Args:
        chunk_size (int): 청크 사이즈
        chunk_overlap (int): 청크 오버랩 사이즈
        separators (list[int]: Optional): 구분자
    """
    def __init__(
        self, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200,
        separators: list[str] | None = None
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def _flatten_metadata(self, chunk: dict[str, Any]) -> dict[str, Any]:
        """청크 메타데이터 목록을 뽑아내 VectorDB 필터링에 용이하도록 평탄화
        
        Args:
            chunk (dict[str, Any]): 구조화된 청크 객체

        Returns:
            dict[str, Any]: 평탄화된 메타데이터 -> 실제로는 위 형태로 메타데이터가 들어간다.
        """
        meta = chunk.get("metadata", {})
        source = meta.get("source", {})
        section = meta.get("section", {})
        pages = meta.get("pages", {})
        container = meta.get("container", {})

        return {
            "chunk_id": chunk.get("chunk_id") or "",
            "source_doc_name": source.get("doc_name") or "",
            "section_title": section.get("title") or "",
            "section_level": str(section.get("level")) if section.get("level") is not None else "0",
            "page_range": pages.get("range") or "",
            "container_type": container.get("type") or "",
            "asset_path": container.get("asset_path") if container.get("asset_path") is not None else ""
        }

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """텍스트를 구분자 단위로 분할 후 chunk_size에 맞춰 재조립

        입력 텍스트가 chunk_size 보다 작을 경우 텍스트를 그대로 반환하며
        
        overlap 사이즈에 따라 겹치는 부분을 결정

        Args:
            text (str): 분할할 텍스트
            separators (list[str]): 분할 단위 구분자 목록

        Returns:
            list[str]: 분할된 텍스트 목록
        """
        # 현재 텍스트가 chunk_size 보다 작을 시 분할 x
        if len(text) <= self.chunk_size:
            return [text]

        # 현재 단계에서 사용할 구분자(separator), 다음 단계용 구분자(new_separators) 결정 
        separator = separators[-1] # 기본값 ""
        new_separators = []
        for i, s in enumerate(separators):
            if s == "":
                separator = s
                break
            if s in text:
                separator = s
                new_separators = separators[i + 1:] # 현재 구분자 이후 것들만 다음 단계로 전달
                break

        # 선택된 구분자로 분할 
        splits = text.split(separator) if separator != "" else list(text)

        # 분할된 조각들을 chunk_size와 overlap에 맞춰 재조합
        final_splits = []
        for s in splits:
            if len(s) <= self.chunk_size:
                final_splits.append(s)
            else:
                # 현재 조각(s)이 너무 크므로 남은 구분자 사용하여 다시 분할
                recursive_result = self._recursive_split(s, new_separators)
                final_splits.extend(recursive_result)
        
        # 분할 완료된 조각들을 chunk_size와 overlap에 맞춰 재조합
        final_chunks = []
        current_doc = ""
        for s in final_splits:
            if current_doc and len(current_doc) + len(separator) + len(s) > self.chunk_size:
                final_chunks.append(current_doc)

                # Overlap 처리
                overlap_start = max(0, len(current_doc) - self.chunk_overlap)
                current_doc = current_doc[overlap_start:]

            if current_doc:
                # 구분자가 ""일 경우를 대비하여 처리
                current_doc += (separator if separator != "" else "") + s
            else:
                current_doc = s

        if current_doc:
            final_chunks.append(current_doc)

        return final_chunks

    def convert(self, raw_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """청크 목록을 받아 vectorDB에 들어갈 형태로 청크를 변환
        
        Args:
            raw_chunks (list[dict[str, Any]]): Docling, Upstage 추출물을 구조화 시킨 청크

        Returns:
            list[dict[str, Any]]: 변환 청크
        """
        final_docs = []

        for chunk in raw_chunks:
            text = (chunk.get("text") or "").strip()
            asset_path = chunk.get("metadata", {}).get("container", {}).get("asset_path")
            if not text and not asset_path:
                continue

            original_chunk_id = chunk.get("chunk_id", "unknown")
            base_metadata = self._flatten_metadata(chunk)

            # 텍스트 분할 로직 수행
            container_type = base_metadata.get("container_type")
            if container_type == "texts":
                split_texts = self._recursive_split(text, self.separators)
            else:
                split_texts = [text]
            total_parts = len(split_texts)

            if total_parts == 0 and asset_path:
                split_texts = [""]
                total_parts = 1

            for idx, content in enumerate(split_texts, start=1):
                doc_metadata = base_metadata.copy()
                doc_metadata["chunk_part"] = f"{idx}/{total_parts}"
                
                unique_id = f"{original_chunk_id}_p{idx}" if total_parts > 1 else original_chunk_id
                # doc_metadata["chunk_id"] = unique_id
                
                final_docs.append({
                    "id": unique_id,
                    "page_content": content,
                    "metadata": doc_metadata
                })

        return final_docs

    @staticmethod
    def _flatten_ladder_value(
        value: Any,
        prefix: str,
    ) -> dict[str, str | int | float | bool]:
        """dict/list를 Chroma가 저장 가능한 scalar metadata로 완전 평탄화한다."""
        flat: dict[str, str | int | float | bool] = {}

        if isinstance(value, dict):
            # 빈 dict와 키 자체가 없던 경우를 구분하기 위해 type을 남긴다.
            flat[f"{prefix}__type"] = "dict"

            for key, child in value.items():
                flat.update(
                    ChunkRefiner._flatten_ladder_value(
                        child,
                        f"{prefix}__{key}",
                    )
                )
            return flat

        if isinstance(value, list):
            # 빈 list도 보존한다.
            flat[f"{prefix}__type"] = "list"
            flat[f"{prefix}__length"] = len(value)

            for index, child in enumerate(value):
                flat.update(
                    ChunkRefiner._flatten_ladder_value(
                        child,
                        f"{prefix}__{index:03d}",
                    )
                )
            return flat

        if value is None:
            # 키가 없던 경우와 `key: null`을 구분한다.
            flat[f"{prefix}__is_null"] = True
            return flat

        if isinstance(value, (str, int, float, bool)):
            flat[prefix] = value
            return flat

        raise TypeError(
            f"지원하지 않는 래더 metadata 타입: "
            f"{type(value).__name__} ({prefix})"
        )
    
    def ladder_convert(self, raw_chunks: dict[str, Any], site_id: str) -> list[dict[str, Any]]:
        source_file = str(raw_chunks.get("source_file", "unknown"))
        source_stem = source_file.rsplit(".", 1)[0]
        final_docs = []

        for block in raw_chunks["nblocks"]:
            nblock = str(block["nblock"])
            chunk_id = f"ladder:{source_stem}:{nblock}"

            # search_text는 page_content에 이미 보존되므로 metadata에서는 제외한다.
            block_details = {
                key: value
                for key, value in block.items()
                if key != "search_text"
            }

            metadata: dict[str, str | int | float | bool] = {
                "chunk_id": chunk_id,
                "site_id": site_id,
                "source_type": "mnemonic",
                "mnemonic_kind": "ladder",
                "source_doc_name": source_file,
                "source_section": str(raw_chunks["section"]),

                # 기존 검색/응답 코드와 호환하기 위한 필드
                "section_title": nblock,
                "page_range": "",
                "container_type": "ladder",
                "asset_path": "",
            }

            # summary, steps, operand, sub_instruction 등을 모두 scalar로 변환
            metadata.update(
                self._flatten_ladder_value(
                    value=block_details,
                    prefix="ladder",
                )
            )

            final_docs.append({
                "id": chunk_id,
                "page_content": str(block["search_text"]),
                "metadata": metadata,
            })

        return final_docs