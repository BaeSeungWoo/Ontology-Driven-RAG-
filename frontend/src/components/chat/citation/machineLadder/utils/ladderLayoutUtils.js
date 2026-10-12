// 래더 트리(back/ladder/topology.py의 build_net() 출력) -> SVG 그리기용 절대좌표
// 엘리먼트 목록으로 바꾸는 순수 함수. React/DOM에 전혀 의존하지 않는다.
//
// FANUC LADDER-III 화면 배치를 따른다:
// - 왼쪽/오른쪽 레일은 모든 net에서 같은 x에 고정(railGap을 호출부가 통일해서 넘김)
// - 회로의 주 가로선은 각 노드의 맨 윗행에 있고, 병렬 분기는 그 아래로 늘어진다
// - 코일은 항상 오른쪽 레일에 붙고, 코멘트는 레일 바깥 오른쪽에 쓴다
// - 같은 입력 회로를 공유하는 연속된 출력(코일 여러 개)은 입력을 한 번만 그리고
//   코일 바로 앞에서 세로로 분기한다

import {
    MIN_RAIL_GAP,
    CELL_WIDTH,
    ROW_HEIGHT,
    WIRE_OFFSET,
    JOIN_STUB,
    OUTPUT_BRANCH_GAP,
    LEFT_GUTTER,
    COMMENT_WIDTH,
} from '../constants/ladderLayoutConstants.js';

const NET_PAD_Y = 4;

// ---- 1단계: 크기 계산 -------------------------------------------------------

function measure(node) {
    if (!node) return { width: CELL_WIDTH, height: ROW_HEIGHT };

    switch (node.type) {
        case 'contact':
        case 'contact_not':
            return { width: CELL_WIDTH, height: ROW_HEIGHT };

        case 'series': {
            const sizes = node.children.map(measure);
            return {
                width: sizes.reduce((sum, s) => sum + s.width, 0),
                height: Math.max(ROW_HEIGHT, ...sizes.map((s) => s.height)),
            };
        }

        case 'parallel': {
            const sizes = node.children.map(measure);
            return {
                width: Math.max(...sizes.map((s) => s.width)) + JOIN_STUB * 2,
                height: sizes.reduce((sum, s) => sum + s.height, 0),
            };
        }

        default:
            return { width: CELL_WIDTH, height: ROW_HEIGHT };
    }
}

// ---- 2단계: 위치 지정 -------------------------------------------------------
// (x, y)는 노드 영역의 왼쪽 위. 노드의 주 가로선은 y + WIRE_OFFSET.

function place(node, x, y, elements) {
    if (!node) return;
    const wireY = y + WIRE_OFFSET;

    switch (node.type) {
        case 'contact':
        case 'contact_not':
            elements.push({
                kind: 'contact',
                negated: node.type === 'contact_not',
                address: node.address,
                symbol: node.symbol,
                comment: node.comment,
                x,
                y,
                width: CELL_WIDTH,
                wireY,
            });
            break;

        case 'series': {
            let curX = x;
            node.children.forEach((child) => {
                place(child, curX, y, elements);
                curX += measure(child).width;
            });
            break;
        }

        case 'parallel': {
            const size = measure(node);
            const right = x + size.width;
            let curY = y;
            let lastWireY = wireY;
            node.children.forEach((child) => {
                const cs = measure(child);
                const childX = x + JOIN_STUB;
                const childWireY = curY + WIRE_OFFSET;
                place(child, childX, curY, elements);
                elements.push({ kind: 'hwire', x1: x, x2: childX, y: childWireY });
                elements.push({ kind: 'hwire', x1: childX + cs.width, x2: right, y: childWireY });
                lastWireY = childWireY;
                curY += cs.height;
            });
            elements.push({ kind: 'vwire', x, y1: wireY, y2: lastWireY });
            elements.push({ kind: 'vwire', x: right, y1: wireY, y2: lastWireY });
            break;
        }

        default:
            break;
    }
}

// ---- net 단위 -------------------------------------------------------------

// 연속된 출력 중 입력 회로가 똑같은 것끼리 묶는다(WRT 여러 개가 같은 스택 top을 공유하는 경우).
function groupOutputs(outputs) {
    const groups = [];
    let prevKey = null;
    outputs.forEach((output) => {
        const key = JSON.stringify(output.input ?? null);
        if (groups.length > 0 && key === prevKey) {
            groups[groups.length - 1].outputs.push(output);
        } else {
            groups.push({ input: output.input, outputs: [output] });
        }
        prevKey = key;
    });
    return groups;
}

/** 이 net을 그리는 데 필요한 최소 레일 간격 - 호출부에서 화면의 모든 net 중 최대값으로 통일한다. */
export function requiredRailGap(net) {
    const groups = groupOutputs(net.outputs || []);
    const maxInput = Math.max(0, ...groups.map((g) => (g.input ? measure(g.input).width : 0)));
    return Math.max(MIN_RAIL_GAP, maxInput + OUTPUT_BRANCH_GAP + CELL_WIDTH + 40);
}

/**
 * net 하나를 {width, height, elements, leftRailX, rightRailX}로 변환한다.
 * railGap: 좌/우 레일 간격(화면의 모든 net이 같은 값을 써야 레일이 한 줄로 이어진다).
 */
export function layoutNet(net, railGap = MIN_RAIL_GAP) {
    const leftRailX = LEFT_GUTTER;
    const rightRailX = LEFT_GUTTER + railGap;
    const coilX = rightRailX - CELL_WIDTH;
    const branchX = coilX - OUTPUT_BRANCH_GAP;
    const elements = [];

    const groups = groupOutputs(net.outputs || []);
    let curY = NET_PAD_Y;

    groups.forEach((group) => {
        const inputSize = group.input ? measure(group.input) : { width: 0, height: ROW_HEIGHT };
        const groupHeight = Math.max(inputSize.height, group.outputs.length * ROW_HEIGHT);
        const mainWireY = curY + WIRE_OFFSET;

        if (group.input) place(group.input, leftRailX, curY, elements);
        const inputEndX = leftRailX + inputSize.width;

        const multi = group.outputs.length > 1;
        // 입력 끝 -> (분기점 또는) 첫 코일
        elements.push({ kind: 'hwire', x1: inputEndX, x2: multi ? branchX : coilX, y: mainWireY });

        group.outputs.forEach((output, i) => {
            const rowY = curY + i * ROW_HEIGHT;
            const wireY = rowY + WIRE_OFFSET;
            if (multi) {
                elements.push({ kind: 'hwire', x1: branchX, x2: coilX, y: wireY });
            }
            if (output.type === 'function') {
                elements.push({
                    kind: 'function',
                    subName: output.subName || `SUB${output.sub ?? ''}`,
                    operands: output.operands || [],
                    x: coilX,
                    y: rowY,
                    width: CELL_WIDTH,
                    wireY,
                });
            } else {
                elements.push({
                    kind: 'coil',
                    negated: output.type === 'coil_not',
                    address: output.address,
                    symbol: output.symbol,
                    comment: output.comment,
                    x: coilX,
                    y: rowY,
                    width: CELL_WIDTH,
                    wireY,
                    commentX: rightRailX + 10,
                });
            }
        });

        if (multi) {
            const lastWireY = curY + (group.outputs.length - 1) * ROW_HEIGHT + WIRE_OFFSET;
            elements.push({ kind: 'vwire', x: branchX, y1: mainWireY, y2: lastWireY });
        }

        curY += groupHeight;
    });

    if (groups.length === 0) curY += ROW_HEIGHT;

    const height = curY + NET_PAD_Y;
    const width = rightRailX + COMMENT_WIDTH;
    return { width, height, elements, leftRailX, rightRailX };
}
