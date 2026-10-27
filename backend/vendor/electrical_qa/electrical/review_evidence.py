"""Small, source-preserving helpers for electrical answer review."""
import re


_TAG = r'[A-Z][A-Z0-9_]*(?:\.\d+)?'
_TOKEN = r'[+-]?[A-Z0-9_]+(?:\.\d+)?[+]?'
_VOLTAGE = r'[+-]?\d+(?:\.\d+)?\s*V'


def fact_text_error(text, source):
    """Keep drawing descriptions separate from invented test procedures."""
    procedure = (r'(?:확인|점검|측정|검사|테스트|체크|조작|인가|분리|차단)\s*'
                 r'(?:하(?:세요|십시오|라|자|여|고|면|기|는|도록|려|지)|한다|해(?:야|서|보|주)?|할\s*(?:수|것|필요))'
                 r'|(?:이어야|여야|되어야|돼야|있어야|없어야|해야)'
                 r'|\b(?:check|inspect|measure|test)\s+(?:the|that|whether)\b')
    if re.search(procedure, text, re.I):
        return ('점검·측정 지시를 도면의 사실 설명에 섞지 마세요. '
                '지시어만 지우지 말고, 요구한 정상 상태나 고장 판단도 제거한 뒤 같은 원문의 연결·주소를 평서문으로 다시 설명하세요.')
    if re.search(r'정상(?:적으로|인\s*경우|\s*상태|\s*시)|제대로|정상\s*여부', text):
        return ('도면의 연결 설명만으로 정상 동작 상태를 정하지 마세요. '
                '정상 여부 판단 대신 원문에 명시된 접점 종류·연결·조건을 설명하세요.')
    if re.search(r'(?:명시|확인|기재|표시)되지|알\s*수\s*없', text) and not re.search(
            r'not\s+(?:specified|shown|confirmed)|unknown|unclear|미상|불명|(?:명시|확인|기재|표시)되지', source, re.I):
        return ('선택한 관계절에 없다는 이유로 전체 도면에 연결이 없거나 불명확하다고 단정하지 마세요. '
                '원문에 실제로 명시된 연결만 설명하세요.')
    if re.search(r'코일|\bcoil\b', text, re.I) and not re.search(
            r'코일|\bcoil\b|\bdrives?\s+(?:the\s+)?relay\b', source, re.I):
        return '인용한 원문 관계절에 코일 연결이 없습니다. 접점·부하 출력·보드 전원을 코일 공급으로 바꾸지 마세요.'
    if re.search(r'다이오드|\bdiode\b', text, re.I) and not re.search(r'다이오드|\bdiode\b', source, re.I):
        return '인용한 관계절에 다이오드 표기가 없습니다. 장치 사양을 내부 부품의 사양으로 옮기지 마세요.'
    dependency = (r'(?:에|이|가)\s*필요|필요(?:한|하|\s*조건)|필수|전제\s*조건|없으면|때만|경우에만|의존'
                  r'|(?:누르|닫히|열리|인가되|공급되|켜지|꺼지|작동하|동작하|해제되|성립하|충족되)면'
                  r'|\b(?:requires?|required|necessary|essential|depends?\s+on|only\s+(?:if|when))\b')
    source_condition = (dependency + r'|\b(?:if|when|unless|interlock|permissive|condition|via|through)\b'
                        r'|조건|인터록|인터록크|(?:닫힐|열릴|공급될|인가될)\s*때')
    if re.search(dependency, text, re.I) and not re.search(source_condition, source, re.I):
        return ('인용한 원문 관계절에는 필요조건·동작조건이 없습니다. 전원·연결 설명에 '
                '기동 신호 전달의 필요조건이나 조작 후 동작을 단정하지 말고, 원문에 명시된 관계만 설명하세요.')
    return None


def source_facts(records):
    """Keep whole clauses and bind trailing catalogue notes to their device."""
    facts = []
    for record in records:
        text = record['text']
        headings = set(re.findall(r'(?:^|\n)\s*(-?' + _TAG + r')\s*:', text))
        subject = record.get('symbol') or (next(iter(headings)) if len(headings) == 1 else '')
        catalogue = re.search(r'(?:\s*\[[^\[\]]*\])+\s*$', text)
        body = text[:catalogue.start()] if catalogue else text
        clauses, start, depth = [], 0, 0
        for offset, char in enumerate(body):
            if char in '([':
                depth += 1
            elif char in ')]':
                depth = max(0, depth - 1)
            elif char == ';' and not depth:
                clauses.append(body[start:offset])
                start = offset + 1
        clauses.append(body[start:])
        quotes = [(clause, 'relationship') for clause in clauses]
        if catalogue:
            quotes.extend((match[0], 'catalogue_annotation') for match in re.finditer(r'\[[^\[\]]*\]', catalogue[0]))
        for number, (clause, kind) in enumerate(quotes, 1):
            quote = clause.strip()
            if quote:
                facts.append({'id': f"{record['id']}#{number}", 'record': record['id'],
                              'quote': quote, 'subject': subject, 'kind': kind})
    return facts


def draft_hints(draft, records):
    """Return bounded literal hints; a draft never supplies evidence."""
    pattern = r'(?<![A-Z0-9_.])-?(' + _TAG + r')(?![A-Z0-9_.])'
    source = '\n'.join(record['text'] for record in records)
    present = {value.upper() for value in re.findall(pattern, source, re.I)
               if any(char.isdigit() for char in value)}
    hints = []
    for value in re.findall(pattern, draft or '', re.I):
        value = value.upper()
        if value in present and value not in hints:
            hints.append(value)
            if len(hints) == 20:
                break
    return hints


def _literal(value):
    return r'(?<![A-Z0-9_.])-?' + re.escape(value.lstrip('-')) + r'(?![A-Z0-9_.])'


def _claimed_voltage(text, endpoint, voltage):
    """Recognise an explicit supply assertion, not an across-pair measurement."""
    destination = _literal(endpoint)
    value = re.escape(re.sub(r'\s+', '', voltage))
    # Korean coordinated destinations retain the second destination's particle.
    following = destination + r'\s*(?:에|으로|로)\s*' + value + r'\s*(?:가|이|를|을)?\s*(?:공급|전달|인가)'
    preceding = value + r'\s*(?:를|을)?\s*' + destination + r'\s*(?:에|으로|로)\s*(?:공급|전달|인가)'
    english = r'(?:supply|supplies|supplied|feed|feeds|fed|deliver|delivers)\s+' + value + r'\s+to\s+' + destination
    return any(re.search(pattern, text, re.I) for pattern in (following, preceding, english))


def _coil_return_error(text, source, subject):
    """Keep an explicitly traced return coil terminal out of a supply role."""
    terminal = r'(?=[A-Z0-9]*\d)[A-Z0-9]+'
    coils = list(re.finditer(r'\bcoil\s+(?:terminal\s+)?(' + terminal + r')(?![A-Z0-9_.])', source, re.I))
    supplies, returns = set(), set()
    owner = subject
    for number, coil in enumerate(coils):
        named = re.search(r'(' + _TAG + r')(?:[’\']s)?\s+(?:relay\s+)?$', source[:coil.start()], re.I)
        if named and any(char.isdigit() for char in named[1]):
            owner = named[1].upper()
        if not owner:
            continue
        end = coils[number + 1].start() if number + 1 < len(coils) else len(source)
        clause = re.split(r'[;\n]', source[coil.end():end], maxsplit=1)[0]
        pin = coil[1].upper()
        voltage = re.match(r'\s+on\s+(\+\d+(?:\.\d+)?)\s*V\b', clause, re.I)
        if voltage and float(voltage[1]) > 0:
            supplies.add((owner, pin))
        direct = re.match(r'\s*(?:\([^)]*\)\s*)?returns?\s+to\s+' + _TOKEN + r'(?![A-Z0-9_.])', clause, re.I)
        chain = re.search(r'\bto\s+(' + _TOKEN + r')\s*,\s*\1\s+returns?\s+to\s+' + _TOKEN + r'(?![A-Z0-9_.])', clause, re.I)
        if direct or chain:
            returns.add((owner, pin))
    returns = {(owner, pin) for owner, pin in returns
               if any(other_owner == owner and other_pin != pin for other_owner, other_pin in supplies)}
    claims = list(re.finditer(r'(?:코일\s*(?:의\s*)?(?:단자\s*)?|coil\s+(?:terminal\s+)?)('
                             + terminal + r')(?![A-Z0-9_.])', text, re.I))
    owner = subject
    for number, coil in enumerate(claims):
        named = re.search(r'(' + _TAG + r')\s*(?:(?:릴레이|relay)\s*)?$', text[:coil.start()], re.I)
        if named and any(char.isdigit() for char in named[1]):
            owner = named[1].upper()
        if (owner, coil[1].upper()) not in returns:
            continue
        end = claims[number + 1].start() if number + 1 < len(claims) else len(text)
        clause = re.split(r'[,;.!?\n]', text[coil.end():end], maxsplit=1)[0]
        if re.search(r'아니|않|없|\bnot\b', clause, re.I):
            continue
        role = re.search(r'공급\s*측|전원\s*입력|\bsupply\s+(?:side|terminal)\b', clause, re.I)
        if role and any(pin.upper() != coil[1].upper() for pin in re.findall(
                r'(?<![A-Z0-9_.])(' + terminal + r')\s*(?:번|단자)', clause[:role.start()], re.I)):
            continue
        if role:
            return (f'원문은 {owner} 코일 단자 {coil[1]}의 경로가 귀환한다고 명시하고 다른 단자에 양전원을 연결합니다. '
                    '이 귀환 단자를 공급 측이나 전원 입력으로 바꾸지 마세요.')
    return None


def relation_error(text, source):
    """Reject only literal contradictions of explicit source associations.

    This is deliberately not a circuit parser: unknown wording is left to the
    semantic reviewer. Neither a tag named M nor a numbered terminal alone
    establishes a supply, return, ownership, or normal measurement value.
    """
    text = text.replace('**', '')
    paired = (r'\b(?:switch|switches|connect|connects)\s+(' + _VOLTAGE + r')\s*/\s*('
              + _TOKEN + r')\s+to\s+(' + _TOKEN + r')\s*/\s*(' + _TOKEN + r')(?![A-Z0-9_.])')
    for match in re.finditer(paired, source, re.I):
        supply, other, supplied, returned = match.groups()
        if supply.upper().replace(' ', '') == other.upper().replace(' ', ''):
            continue
        wrong = _claimed_voltage(text, returned, supply)
        # The second destination can precede the first in a coordinated claim.
        group = (_literal(returned) + r'\s*(?:및|와|과|,|and)\s*'
                 + _literal(supplied) + r'\s*(?:에|으로|로)\s*'
                 + re.escape(supply) + r'\s*(?:가|이|를|을)?\s*(?:공급|전달|인가)')
        if wrong or re.search(group, text, re.I):
            return (f'원문은 {supplied}에 {supply}, {returned}에 {other}를 각각 연결합니다. '
                    '두 선을 같은 공급 전원으로 바꾸지 말고 원문의 대응 관계를 유지하세요.')

    # Check a terminal only when the source explicitly names its own voltage.
    direct = (r'\bcoil\s+(?:terminal\s+)?([A-Z0-9]+)\s+(?:on|connected\s+to|fed\s+from)\s+('
              + _VOLTAGE + r')(?![A-Z0-9_.])')
    headings = set(re.findall(r'(?:^|\n)\s*(-?' + _TAG + r')\s*:', source))
    subject = next(iter(headings)).lstrip('-').upper() if len(headings) == 1 else ''
    # A local pin and another connector's port in one parenthesis are distinct.
    cross_reference = r'\(\s*pin\s+([A-Z0-9]+)\s*,\s*(-?' + _TAG + r')\s+([A-Z0-9]+)\s*\)'
    for match in re.finditer(cross_reference, source, re.I):
        pin, connector, port = match.groups()
        if connector.lstrip('-').upper() == subject or pin.upper() == port.upper():
            continue
        explicit = _literal(connector) + r'\s*(?:pin\s+|:\s*)' + _literal(pin)
        if re.search(explicit, source, re.I):
            continue
        claim = (_literal(connector) + r'\s*(?:커넥터\s*)?(?:' + _literal(port)
                 + r'\s*(?:의\s*)?)?(?:핀|pin)\s*' + _literal(pin))
        if re.search(claim, text, re.I):
            return (f'원문의 pin {pin}과 {connector} {port}는 구분된 연결 표기입니다. '
                    f'pin {pin}을 {connector}의 핀으로 옮기지 말고 두 표기를 분리하세요.')
    issue = _coil_return_error(text, source, subject)
    if issue:
        return issue
    for match in re.finditer(direct, source, re.I):
        named = re.search(r'(' + _TAG + r')(?:[’\']s)?\s+$', source[:match.start()], re.I)
        if named and any(char.isdigit() for char in named[1]) and named[1].upper() != subject:
            continue
        terminal, expected = match.groups()
        claim = (r'(?:코일\s*(?:의\s*)?(?:단자\s*)?|coil\s+(?:terminal\s+)?)'
                 + re.escape(terminal) + r'(?![A-Z0-9_.])\s*(?:번\s*)?(?:단자\s*)?'
                 + r'(?:에|는|은|on|at)\s*(' + _VOLTAGE + r')\s*(?:가|이|를|을)?\s*(?:공급|전달|인가)')
        for found in re.finditer(claim, text, re.I):
            named = re.search(r'(' + _TAG + r')\s*(?:릴레이\s*)?$', text[:found.start()], re.I)
            if subject and named and any(char.isdigit() for char in named[1]) and named[1].upper() != subject:
                continue
            actual = found[1]
            if re.sub(r'\s+', '', actual).upper() != re.sub(r'\s+', '', expected).upper():
                return f'원문에서 코일 단자 {terminal}의 공급은 {expected}입니다. 다른 전압을 이 단자에 연결하지 마세요.'
    return None
