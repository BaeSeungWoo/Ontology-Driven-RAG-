import json
import os
import time
from pathlib import Path
import urllib.request

import requests
from dotenv import load_dotenv

UPSTAGE_KEY = os.getenv("UPSTAGE_API_KEY")

def upstage_request(api_key: str, file_path: Path) -> dict:
    """Upstage를 통한 PDF 먼저 요청을 보냄.

    Args:
        api_key (str): Upstage API 키
        file_path (Path): 입력 PDF 경로

    Returns:
        dict: 요청 결과 값, 다만 요청 결과 값에 존재하는 request_id 만 사용.
    """
    url = "https://api.upstage.ai/v1/document-digitization/async"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {
                "model": "document-parse-260128",
                "ocr": "auto",
                "chart_recognition": False,
                "coordinates": True,
                "output_formats": '["text"]',
                "base64_encoding": '["table"]',
            }
            response = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"에러 발생: {e}")

def upstage_async_process(api_key: str, request_id: str, output_json_path: Path, poll_interval: int = 2) -> None:
    """`upstage_request`에서 받은 request_id를 통해 처리 상태가 completed가 되었을 경우 
    해당 추출 값을 다운받을 수 있는 url을 가진 객체를 리턴 받음.

    Args:
        api_key (str): Upstage API 키
        request_id (str): 추출 진행 중인 PDF의 상태 확인 키
            해당 상태가 완료 된 경우 추출 결과를 다운로드 받을 수 있는 download_url 생성
        output_json_path (Path): 저장될 JSON 경로
        poll_interval (int, Optional): 상태 확인 주기
            기본값 2초

    """
    url = "https://api.upstage.ai/v1/document-digitization/requests/"+request_id
    headers = {"Authorization": f"Bearer {api_key}"}

    while True:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        # 'status'가 'completed' 또는 'failed'일 때까지 확인 (Upstage API 가이드 기준)
        status = result.get("status")
        if status == "completed":
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"성공: {output_json_path}")
            return
        if status == "failed":
            raise RuntimeError(f"처리 실패: request_id={request_id}, result={result}")

        print(f"처리 중... (status: {status})")
        time.sleep(poll_interval)

def download_result(async_json_path: Path, output_dir: Path) -> None:
    """`upstage_async_process`를 통해 생성한 추출물을 기준으로 

    해당 download_url을 통하여 추출 결과를 다운받음.

    Args:
        async_json_path (Path): process 결과 JSON 형태
        output_dir (Path): 추출 결과가 저장될 경로
    """
    if not async_json_path.exists():
        raise FileNotFoundError(f"download할 파일이 없습니다: {async_json_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(async_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    batches = data.get("batches", [])
    if not batches:
        print(f"추출 결과가 존재하지 않습니다: {async_json_path}")
        return

    for batch in batches:
        url = batch.get("download_url")
        if not url:
            continue 

        # 파일명 추출
        filename = url.split("/")[-1].split("?")[0]
        filepath = output_dir / filename  # 하위 폴더 경로에 저장

        print(f"다운로드 중: {filename}")
        urllib.request.urlretrieve(url, filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)

        print(f"저장 완료: {filepath}")

def process_one_pdf(pdf_path: Path, input_root_dir: Path, async_result_root_dir: Path, batch_json_root_dir: Path, api_key: str) -> None:
    """PDF 문서 한개를 upstage 추출 및 결과 download까지 진행하는 함수

    `upstage_request`를 통해 추출 요청 실시

    `upstage_async_process`를 통해 추출 상태를 확인, download_url 반환

    `download_result`를 통해 download_url에서 추출된 결과를 다운로드

    Args:
        pdf_path (Path): 처리할 PDF 파일 경로
        input_root_dir (Path): 처리할 PDF 들이 모여있는 기준 루트 폴더
        async_result_root_dir (Path): 추출이 완료된 결과를 다운로드 받기 위한 download_url 가진 json 경로
        batch_json_root_dir (Path): download_url을 통해 다운받은 결과 저장 경로
        api_key (str): Upstage API 키

    """
    if not api_key:
        raise RuntimeError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    relative_parent = pdf_path.parent.relative_to(input_root_dir)
    async_json_path = async_result_root_dir / relative_parent / f"{pdf_path.stem}.json"
    output_dir = batch_json_root_dir / relative_parent / pdf_path.stem

    print("=" * 60)
    print(f"처리 시작: {pdf_path}")

    req_res = upstage_request(api_key=api_key, file_path=pdf_path)
    request_id = req_res.get("request_id")
    if not request_id:
        raise RuntimeError(f"request_id 없음: {req_res}")

    upstage_async_process(
        api_key=api_key,
        request_id=request_id,
        output_json_path=async_json_path,
    )

    download_result(
        async_json_path=async_json_path,
        output_dir=output_dir,
    )

    print(f"처리 완료: {pdf_path}")

def process_all_pdf(input_root_dir: Path, async_result_root_dir: Path, batch_json_root_dir: Path, api_key: str) -> None:
    """분할된 PDF 목록을 순회하며 `process_one_pdf`함수를 실행
    
    Args:
        input_root_dir (Path): 처리할 PDF 들이 모여있는 기준 루트 폴더
        async_result_root_dir (Path): 추출이 완료된 결과를 다운로드 받기 위한 download_url 가진 json 경로
        batch_json_root_dir (Path): download_url을 통해 다운받은 결과 저장 경로
        api_key (str): Upstage API 키
    """
    if not api_key:
        raise RuntimeError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    pdf_files = sorted(input_root_dir.rglob("*.pdf"))

    if not pdf_files:
        print(f"PDF 파일이 없습니다: {input_root_dir}")
        return

    for pdf_path in pdf_files:
        process_one_pdf(
            pdf_path=pdf_path,
            input_root_dir=input_root_dir,
            async_result_root_dir=async_result_root_dir,
            batch_json_root_dir=batch_json_root_dir,
            api_key=api_key,
        )

