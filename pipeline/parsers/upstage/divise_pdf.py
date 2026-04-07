from pathlib import Path
import fitz  # PyMuPDF

def split_pdf_by_size(input_pdf_path: Path, output_dir: Path, max_size_mb: int = 45):
    """PDF를 용량 단위로 분할.

    스캔본의 경우는 기본 50MB가 넘는 애들이 많음.

    upstage의 경우 한번 PDF 파일 요청을 보낼 시 50MB 이상은 추출이 불가능.

    따라서 50MB보다 좀 더 여유롭게 45MB로 설정하여 PDF를 분할

    Args:
        input_pdf_path (Path): 입력 PDF 경로
        output_dir (Path): 출력 PDF 경로
        max_size_mb (int): PDF 분할 기준 용량
            기본값 45, 최대 50을 넘어서는 안됨.

    Returns:
        >>> 저장 형태 -> /projects/test_pdf/part_1.pdf
        >>> 저장 형태 -> /projects/test_pdf/part_2.pdf
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(input_pdf_path))
    total_pages = len(doc)
    
    current_writer = fitz.open()  # 새 PDF 객체
    file_count = 1
    
    # 임시 파일로 용량 체크
    temp_path = output_dir / "_temp_check.pdf"

    try:
        for page_num in range(total_pages):
            # 현재 페이지를 새 문서에 복사
            current_writer.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # 증분 저장(incremental)이 아닌 완전 저장을 통해 실제 파일 용량 확인
            current_writer.save(str(temp_path), garbage=3, deflate=True)
            current_size_mb = temp_path.stat().st_size / (1024 * 1024)

            # 용량 초과 시 (마지막 추가 페이지 제외하고 저장)
            if current_size_mb > max_size_mb:
                if current_writer.page_count > 1:
                    # 마지막 페이지 제거 후 저장
                    current_writer.delete_page(current_writer.page_count - 1)
                    output_path = output_dir / f"part_{file_count}.pdf"
                    current_writer.save(str(output_path), garbage=3, deflate=True)
                    print(f"저장 완료: {output_path} (약 {temp_path.stat().st_size/(1024*1024):.2f} MB)")
                    
                    # 새 작성기 시작 및 제외했던 페이지 다시 추가
                    current_writer.close()
                    current_writer = fitz.open()
                    current_writer.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    file_count += 1
                else:
                    # 단일 페이지 자체가 max_size를 넘는 경우 (도면 PDF에서 흔함)
                    print(f"경고: {page_num+1}페이지 단일 용량이 설정치를 초과합니다. 강제 저장합니다.")
                    output_path = output_dir / f"part_{file_count}_large.pdf"
                    current_writer.save(str(output_path), garbage=3, deflate=True)

                    current_writer.close()
                    current_writer = fitz.open()
                    file_count += 1

            # 남은 페이지 저장
            if current_writer.page_count > 0:
                output_path = output_dir / f"part_{file_count}.pdf"
                current_writer.save(output_path, garbage=3, deflate=True)
                print(f"마지막 파트 저장 완료: {output_path}")
    finally:
        current_writer.close()
        doc.close()
        if temp_path.exists():
            temp_path.unlink()  

def split_all_pdfs_in_folder(
    input_dir: Path,
    output_root_dir: Path
):
    """input_dir 안의 모든 PDF를 순회하면서

    `split_pdf_by_size` 함수 실행하여

    output_root_dir/{pdf파일명}/ 아래에 분할 저장한다.

    Args:
        input_dir (Path): 입력 PDF 경로
        output_root_dir (Path): 출력 PDF 경로
    """
    pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"PDF 파일이 없습니다: {input_dir}")
        return

    for pdf_path in pdf_files:
        pdf_output_dir = output_root_dir / pdf_path.stem

        print(f"\n처리 시작: {pdf_path}")
        split_pdf_by_size(
            input_pdf_path=pdf_path,
            output_dir=pdf_output_dir
        )
        print(f"처리 완료: {pdf_path}")
