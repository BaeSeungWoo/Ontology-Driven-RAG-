from fastapi import APIRouter, HTTPException

from app.database import database

promptRouter = APIRouter(prefix="/api/prompts", tags=["prompts"])


@promptRouter.post("/getPromptList")
def getPromptList():
    try:
        prompt_list = database.getPromptList()
        json_data = []

        for row in prompt_list:
            json_data.append(
                {
                    "PROMPT_NO": row[0],
                    "PROMPT_NAME": row[1],
                    "PROMPT_TXT": row[2],
                    "CREATE_USER": row[3],
                    "SEL_YN": "N",
                }
            )

        return json_data
    except Exception as e:
        print(f"get_prompt_list error: {e}")
        raise HTTPException(
            status_code=500,
            detail="프롬프트 목록 조회 중 오류가 발생했습니다.",
        )
