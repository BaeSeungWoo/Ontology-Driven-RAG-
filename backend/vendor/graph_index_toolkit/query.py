"""Turn one question into the embedding expected by an existing index."""
import os

import numpy as np
from openai import OpenAI

from .graph import unit


def embed_question(manifest, question, base_url=None):
    if not question.strip():
        raise ValueError("질문을 입력하세요.")
    client = OpenAI(
        base_url=(base_url or manifest["embedding_base_url"]).rstrip("/"),
        api_key=os.environ.get("EMBEDDING_API_KEY", "EMPTY"),
        timeout=120,
        max_retries=2,
    )
    response = client.embeddings.create(
        model=manifest["embedding_model"], input=[question], encoding_format="float"
    )
    vector = np.asarray(response.data[0].embedding, dtype=np.float32)
    if vector.shape != (int(manifest["embedding_dimensions"]),):
        raise ValueError("질문 임베딩과 인덱스의 차원이 다릅니다.")
    return unit(vector)
