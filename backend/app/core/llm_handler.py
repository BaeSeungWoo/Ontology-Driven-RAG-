# backend/app/core/llm_handler.py

import os
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_anthropic import ChatAnthropic

from app.factories.config import Config


class LLMProvider:
    @staticmethod
    def get_model(config: Config):
        """
        config.llm.provider 에 따라 LangChain 호환 LLM 인스턴스를 반환합니다.
        반환된 객체는 .ainvoke() / .astream() 공통 인터페이스를 지원합니다.

        지원 공급자:
            "openai"    → ChatOpenAI    (OPENAI_API_KEY 환경변수 필요)
            "ollama"    → ChatOllama    (config.llm.base_url 로컬 서버 필요)
            "anthropic" → ChatAnthropic (ANTHROPIC_API_KEY 환경변수 필요)
        """
        provider = config.llm.provider

        if provider == "openai":
            return ChatOpenAI(
                model=config.llm.model_name,
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=0,
                streaming=True,
            )

        if provider == "ollama":
            return ChatOllama(
                model=config.llm.model_name,
                base_url=config.llm.base_url,
                temperature=0,
                num_ctx=8192,   # 긴 매뉴얼·도면 컨텍스트 처리용
            )

        if provider == "anthropic":
            return ChatAnthropic(
                model=config.llm.model_name,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                temperature=0,
                streaming=True,
            )

        raise ValueError(
            f"[{config.id}] 지원하지 않는 LLM 공급자입니다: '{provider}'\n"
            f"  허용값: 'openai' | 'ollama' | 'anthropic'"
        )