"""Present reviewed drawing facts with separate, conservative troubleshooting guidance."""
import re
from difflib import SequenceMatcher


def deduplicate_items(payload):
    """Remove close paraphrases of the same fact, retaining distinct terminals and conditions."""
    result = {'connections': [], 'checks': []}
    seen = []
    for section in result:
        for item in payload.get(section, []):
            text = re.sub(r'[\s*`]+', '', item['text'])
            labels = re.findall(r'[A-Za-z0-9]+(?:[.:/+-][A-Za-z0-9]+)*', text)
            duplicate = False
            for previous, prior_text, prior_labels in seen:
                if item.get('fact') != previous.get('fact') or item['records'] != previous['records']:
                    continue
                if text == prior_text or (labels == prior_labels
                        and not re.search(r'경우|때|이면|동안|아니|않|없|차단|정지', text + prior_text)
                        and SequenceMatcher(None, text, prior_text).ratio() >= 0.88):
                    duplicate = True
                    break
            if not duplicate:
                result[section].append(item)
                seen.append((item, text, labels))
    return result


def diagnostic_guidance(question, payload, records):
    """Use only reviewed facts to name observation targets; do not invent PLC logic or setpoints."""
    if not re.search(r'고장|알람|에러|오류|않|불가|안\s|못\s|점검|멈|문제', question):
        return ''
    by_id = {record['id']: record for record in records}
    inputs, outputs, loads, button_signals = [], [], [], []
    for item in payload['connections'] + payload['checks']:
        record = by_id[item['records'][0]]
        text, source = item['text'], record['text']
        # Require both a reviewed Korean description and an explicit source role.
        for role, pattern, bucket in (
            ('input|입력', r'(?<![A-Z0-9])X\d+\.\d+(?![A-Za-z0-9_.])', inputs),
            ('output|출력', r'(?<![A-Z0-9])Y\d+\.\d+(?![A-Za-z0-9_.])', outputs),
        ):
            if re.search(role, source, re.I):
                for tag in re.findall(pattern, text):
                    if tag in source and (tag, str(record['page'])) not in bucket:
                        bucket.append((tag, str(record['page'])))
        if re.search(r'push\s*button|푸시버튼|조작반.*버튼', source, re.I):
            for tag in re.findall(r'(?<![A-Z0-9])X\d+\.\d+(?![A-Za-z0-9_.])', text):
                if tag in source and (tag, str(record['page'])) not in button_signals:
                    button_signals.append((tag, str(record['page'])))
        if (re.search(r'solenoid|motor|솔레노이드|모터', source, re.I)
                and re.search(r'터미널|단자|접속|연결', text)):
            symbol = str(record.get('symbol') or '')
            if not symbol:
                heading = re.search(r'(?:^|\n)(-?[A-Z][A-Z0-9]*):', source)
                symbol = heading[1] if heading else ''
            if symbol and symbol in text and (symbol, str(record['page'])) not in loads:
                loads.append((symbol, str(record['page'])))

    def targets(rows):
        grouped = {}
        for tag, page in rows:
            grouped.setdefault(tag, set()).add(page)
        return ', '.join(f'**{tag}** (' + ', '.join('p' + page for page in sorted(pages, key=int)) + ')'
                         for tag, pages in grouped.items())

    steps = []
    if inputs:
        steps.append('**조작 입력부터 확인** — 진단 화면에서 ' + targets(inputs)
            + '의 표시 상태와 조작 전후 변화를 기록하세요. 장비의 정식 조작·안전 절차 안에서 확인하고, '
              '입력이 인식되지 않는 것으로 확인되면 아래 도면 근거의 버튼·입력 배선·접속부를 점검 대상으로 좁히세요. '
              '정상 극성이나 반드시 바뀌어야 하는 값은 장비 매뉴얼·래더와 대조해야 합니다.')
    elif button_signals:
        steps.append('**조작 신호부터 확인** — 도면의 버튼 연결에 나타난 ' + targets(button_signals)
            + '의 표시 위치와 조작 전후 변화를 장비 매뉴얼·진단 화면에서 확인하세요. '
              '장비의 정식 조작·안전 절차를 따르고, 신호의 입출력 구분과 정상 ON/OFF는 매뉴얼·래더와 대조하세요. '
              '이 연결 기록만으로 PLC 논리나 동작 허가 조건을 단정할 수 없습니다.')
    if outputs:
        steps.append('**출력 명령과 허가 조건 확인** — 진단 화면에서 ' + targets(outputs)
            + '의 상태를 확인하세요. 조작이 인식되는데 출력 명령이 나오지 않으면 해당 출력의 래더 조건·인터록·관련 알람을 확인하세요. '
              '전기도면의 입력·출력 기록만으로 두 신호 사이의 PLC 논리나 정상 ON/OFF를 단정할 수 없습니다.')
    if loads:
        steps.append('**부하 측 연결 확인** — 점검 대상은 ' + targets(loads)
            + '의 아래 인용된 단자·배선·귀환 연결입니다. '
              '출력 명령이 확인되어도 실제 동작이 없으면 자격을 갖춘 정비자가 승인된 절차에 따라 이 구간의 배선·접속 상태를 확인하세요. '
              '출력 비트만으로 부하에 전원이 전달됐거나 부품이 고장 났다고 판단하지 마세요. '
              '전기 연결이 확인돼도 증상이 남으면 해당 장치의 기계·유공압 및 동작 조건은 별도 정비 매뉴얼로 확인해야 합니다.')
    if not steps:
        return ''
    intro = ('> [!SUMMARY] 먼저 확인할 순서\n'
             '> 현재 도면 근거만으로 고장 원인이나 교체 부품을 확정할 수 없습니다. '
             '아래는 확인 대상을 좁히기 위한 진단 안내이며, 제조사가 제시한 고장 해결 절차를 인용한 것은 아닙니다.\n>\n'
             '> 배선·접속부 점검은 전원 분리와 잔류 에너지 해소 등 장비의 안전 절차를 따른 뒤 수행하세요. '
             '출력 강제 구동이나 인터록 우회는 하지 마세요.\n>\n')
    body = '\n>\n'.join(f'> {index}. {step}' for index, step in enumerate(steps, 1))
    return intro + body + ('\n>\n> 다음 판단에는 관련 알람과 입력·출력의 조작 전후 관찰 결과가 필요합니다. '
                          '확인 결과를 알려주시면 점검 범위를 더 좁힐 수 있습니다.\n\n')
