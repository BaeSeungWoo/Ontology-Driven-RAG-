"""래더 니모닉(RD/AND/OR/RD.STK/AND.STK/OR.STK/WRT) 스택 머신을 직렬/병렬 회로 트리로 복원한다.

참고 프로젝트(Fanuc_LAD_Decode)에는 대응하는 코드가 없다 - 이 파일이 신규 설계분이다
(계획 문서 2.2 참고).

화낙 니모닉은 "스택 top = 현재까지 조립된 부분회로"인 1-스택 머신이다:

  RD/RD.NOT addr        : 새 네트 시작 - 접점 하나를 push
  AND/AND.NOT addr       : top을 pop해서 새 접점과 직렬 결합 후 push (series 확장)
  OR/OR.NOT addr         : top을 pop해서 새 접점과 병렬 결합 후 push (parallel 확장)
  RD.STK/RD.STK.NOT addr : 기존 top은 그대로 둔 채 새 접점을 push (중첩 분기 시작)
  AND.STK                : 상위 2개를 pop해서 직렬 결합 후 push
  OR.STK                 : 상위 2개를 pop해서 병렬 결합 후 push
  WRT/WRT.NOT addr       : top을 peek(pop하지 않음)해서 코일 입력으로 쓰고 출력 목록에 추가
                           - 스택을 유지해야 같은 로직을 공유하는 여러 코일을 지원한다
  함수명령(SUB n)         : WRT와 동일하게 top을 peek해서 enable 입력으로 사용, 뒤따르는
                           param/data 셀을 피연산자로 수집. END1/END2/END는 회로 로직이
                           없으므로 건너뛴다.

노드는 매번 새 dict를 만들어서 반환한다(기존 노드를 제자리에서 수정하지 않음) - 그래야
WRT 시점에 top을 참조만 잡아도 이후 AND/OR가 "새 노드"를 만들어 쌓을 뿐 이미 내보낸
코일의 트리를 오염시키지 않는다.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .model import NON_LOGIC_SUBS, Step
from .symbols import Symbol


def _addr_key(step: Step) -> str:
    return str(step.operand)


def _contact_node(step: Step, symbol_map: Dict[str, Symbol]) -> dict:
    addr = step.operand
    negated = step.op.endswith(".NOT")
    sym = symbol_map.get(str(addr))
    return {
        "type": "contact_not" if negated else "contact",
        "address": str(addr),
        "symbol": sym.symbol if sym else "",
        "comment": sym.comment if sym else "",
    }


def _coil_node(step: Step, input_node: Optional[dict], symbol_map: Dict[str, Symbol]) -> dict:
    addr = step.operand
    negated = step.op.endswith(".NOT")
    sym = symbol_map.get(str(addr))
    return {
        "type": "coil_not" if negated else "coil",
        "address": str(addr),
        "symbol": sym.symbol if sym else "",
        "comment": sym.comment if sym else "",
        "input": input_node,
    }


def _combine(kind: str, a: dict, b: dict) -> dict:
    """series/parallel로 묶되, 같은 종류끼리는 평탄화한다
    (series(series(a,b),c) -> series(a,b,c))."""
    children: List[dict] = []
    for node in (a, b):
        if isinstance(node, dict) and node.get("type") == kind:
            children.extend(node["children"])
        else:
            children.append(node)
    return {"type": kind, "children": children}


def _operand_value(step: Step) -> dict:
    if isinstance(step.operand, str):
        # Address의 __str__ 결과가 이미 문자열로 들어오는 경우(토폴로지 호출 시점엔
        # 항상 Address 객체이므로 보통 이 분기는 .LST 파서 경유 데이터에서만 발생)
        return {"kind": "address", "value": step.operand}
    from .model import Address
    if isinstance(step.operand, Address):
        return {"kind": "address", "value": str(step.operand)}
    return {"kind": "const", "value": step.operand}


def build_net(
    steps: List[Step],
    net_index: int,
    program_label: str,
    symbol_map: Dict[str, Symbol],
) -> dict:
    """한 네트(그룹화된 Step 목록)를 트리 구조로 변환한다."""
    stack: List[dict] = []
    outputs: List[dict] = []
    warnings: List[str] = []

    i = 0
    n = len(steps)
    while i < n:
        step = steps[i]

        if step.kind == "basic":
            op = step.op

            if op in ("RD", "RD.NOT", "RD.STK", "RD.STK.NOT"):
                stack.append(_contact_node(step, symbol_map))

            elif op in ("AND", "AND.NOT"):
                if not stack:
                    warnings.append(f"step {step.index}: {op} - 앞선 RD 없이 등장")
                    stack.append(_contact_node(step, symbol_map))
                else:
                    top = stack.pop()
                    stack.append(_combine("series", top, _contact_node(step, symbol_map)))

            elif op in ("OR", "OR.NOT"):
                if not stack:
                    warnings.append(f"step {step.index}: {op} - 앞선 RD 없이 등장")
                    stack.append(_contact_node(step, symbol_map))
                else:
                    top = stack.pop()
                    stack.append(_combine("parallel", top, _contact_node(step, symbol_map)))

            elif op == "AND.STK":
                if len(stack) < 2:
                    warnings.append(f"step {step.index}: AND.STK - 스택에 항목 2개 미만")
                else:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(_combine("series", a, b))

            elif op == "OR.STK":
                if len(stack) < 2:
                    warnings.append(f"step {step.index}: OR.STK - 스택에 항목 2개 미만")
                else:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(_combine("parallel", a, b))

            elif op in ("WRT", "WRT.NOT"):
                if not stack:
                    warnings.append(f"step {step.index}: {op} - 빈 스택에서 호출")
                else:
                    outputs.append(_coil_node(step, stack[-1], symbol_map))

            else:
                warnings.append(f"step {step.index}: 알 수 없는 기본 명령 {op!r}")

        elif step.kind == "func":
            if step.sub in NON_LOGIC_SUBS:
                pass  # END1/END2/END - 회로 로직 없음, 렌더링에서 제외
            else:
                operands = []
                j = i + 1
                while j < n and steps[j].kind in ("param", "data"):
                    operands.append(_operand_value(steps[j]))
                    j += 1
                input_node = stack[-1] if stack else None
                if input_node is None:
                    warnings.append(
                        f"step {step.index}: 함수명령 {step.sub_name} - 빈 스택에서 호출"
                    )
                outputs.append({
                    "type": "function",
                    "sub": step.sub,
                    "subName": step.sub_name,
                    "operands": operands,
                    "input": input_node,
                })
                i = j - 1  # 소비한 param/data 셀만큼 건너뛴다

        elif step.kind in ("param", "data"):
            warnings.append(f"step {step.index}: 함수명령 없이 등장한 {step.kind} 셀")

        i += 1

    if len(stack) > 1:
        # RD.STK로 쌓은 조건 중 일부가 끝까지 AND.STK/OR.STK로 합쳐지지도, WRT/함수
        # 입력으로도 다시 쓰이지 않고 남는 경우 - 실제 화낙 래더에서도 흔히 나오는
        # 정상 패턴(한 net에서 여러 출력을 독립적으로 분배하는 경우 등)이라 에러는
        # 아니고, 참고용 메모로만 남긴다.
        warnings.append(
            f"참고: net 종료 시점에 소비되지 않은 조건이 {len(stack) - 1}개 남아있습니다"
        )

    return {
        "netIndex": net_index,
        "program": program_label,
        "outputs": outputs,
        "warnings": warnings,
    }
