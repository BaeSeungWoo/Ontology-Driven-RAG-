'use client';

import { layoutNet } from '../utils/ladderLayoutUtils.js';
import { LABEL_FONT_SIZE, WIRE_OFFSET, ROW_HEIGHT, TABLE_COLUMNS, TABLE_ROW_HEIGHT } from '../constants/ladderLayoutConstants.js';

// 색상은 ladderViewLayout.css의 CSS 변수에서 가져온다(라이트/다크 테마 전환은
// html[data-theme]에 따라 CSS가 처리). SVG 속성(stroke="var(..)")은 브라우저마다
// 해석이 달라서 style 객체로 넣는다.
const WIRE_COLOR = 'var(--ladder-wire)';
const RAIL_COLOR = 'var(--ladder-rail)';
const SYMBOL_STROKE = 'var(--ladder-symbol-stroke)';
const ON_COLOR = 'var(--ladder-on)';
const ON_PAD = 'var(--ladder-on-pad)';
const COIL_OFF_FILL = 'var(--ladder-coil-off)';
const SELECT_COLOR = 'var(--ladder-select)';
const TICK_HALF = 10;

// 표시 모드에 따라 위/아래 라벨을 정한다.
// both: 위=주소, 아래=심볼 / address: 위=주소 / symbol: 위=심볼(없으면 주소)
function labelsFor(el, displayMode) {
    if (displayMode === 'symbol') return { top: el.symbol || el.address, bottom: '' };
    if (displayMode === 'address') return { top: el.address, bottom: '' };
    return { top: el.address, bottom: el.symbol || '' };
}

function Labels({ cx, el, displayMode }) {
    const { top, bottom } = labelsFor(el, displayMode);
    return (
        <>
            <text x={cx} y={el.wireY - 15} fontSize={LABEL_FONT_SIZE} textAnchor="middle" className="ladder-addr-label">
                {top}
            </text>
            {bottom && (
                <text x={cx} y={el.wireY + 27} fontSize={LABEL_FONT_SIZE} textAnchor="middle" className="ladder-symbol-label">
                    {bottom}
                </text>
            )}
        </>
    );
}

function Wire({ x1, y1, x2, y2, on, glowId }) {
    if (x2 < x1 || y2 < y1 || (x1 === x2 && y1 === y2)) return null;
    return (
        <line
            x1={x1} y1={y1} x2={x2} y2={y2}
            style={{ stroke: on ? ON_COLOR : WIRE_COLOR }}
            strokeWidth={on ? 3 : 2}
            strokeLinecap="round"
            filter={on ? `url(#${glowId})` : undefined}
        />
    );
}

// 클릭/키보드로 선택 가능한 그룹(접점/코일)
function Selectable({ el, selKey, selected, onSelect, onJump, children, className }) {
    const handleKey = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect?.(el);
        }
    };
    return (
        <g
            className={`${className}${selected ? ' is-selected' : ''}`}
            role="button"
            tabIndex={0}
            aria-label={`${el.address} ${el.symbol || ''} 선택`}
            data-sel-key={selKey}
            onClick={() => onSelect?.(el)}
            onDoubleClick={() => onJump?.(el)}
            onKeyDown={handleKey}
        >
            <title>{[el.address, el.symbol, el.comment].filter(Boolean).join(' / ')}</title>
            <rect
                x={el.x + 4} y={el.wireY - 30} width={el.width - 8} height={64} rx={8}
                style={{
                    fill: selected ? 'var(--ladder-select-fill)' : 'transparent',
                    stroke: selected ? SELECT_COLOR : 'transparent',
                }}
                strokeWidth={1.5}
            />
            {children}
        </g>
    );
}

function ContactGlyph({ el, on, powerIn, displayMode, glowId, selKey, selected, onSelect, onJump }) {
    const cx = el.x + el.width / 2;
    const t1 = cx - 8;
    const t2 = cx + 8;
    const y = el.wireY;
    const tickColor = on ? ON_COLOR : SYMBOL_STROKE;

    return (
        <Selectable el={el} selKey={selKey} selected={selected} onSelect={onSelect} onJump={onJump} className={`ladder-contact${on ? ' is-on' : ''}`}>
            <Wire x1={el.x} y1={y} x2={t1} y2={y} on={powerIn} glowId={glowId} />
            <Wire x1={t2} y1={y} x2={el.x + el.width} y2={y} on={powerIn && on} glowId={glowId} />
            {on && <rect x={cx - 15} y={y - 14} width={30} height={28} rx={7} style={{ fill: ON_PAD }} />}
            <line x1={t1} y1={y - TICK_HALF} x2={t1} y2={y + TICK_HALF} style={{ stroke: tickColor }} strokeWidth={2.4} strokeLinecap="round" />
            <line x1={t2} y1={y - TICK_HALF} x2={t2} y2={y + TICK_HALF} style={{ stroke: tickColor }} strokeWidth={2.4} strokeLinecap="round" />
            {el.negated && (
                <line x1={t1 - 4} y1={y + TICK_HALF} x2={t2 + 4} y2={y - TICK_HALF} style={{ stroke: tickColor }} strokeWidth={2} strokeLinecap="round" />
            )}
            <Labels cx={cx} el={el} displayMode={displayMode} />
        </Selectable>
    );
}

function CoilGlyph({ el, on, powerIn, displayMode, glowId, selKey, selected, onSelect, onJump }) {
    const cx = el.x + el.width / 2;
    const r = 12;
    const y = el.wireY;

    return (
        <Selectable el={el} selKey={selKey} selected={selected} onSelect={onSelect} onJump={onJump} className={`ladder-coil${on ? ' is-on' : ''}`}>
            <Wire x1={el.x} y1={y} x2={cx - r} y2={y} on={powerIn} glowId={glowId} />
            <circle
                cx={cx} cy={y} r={r}
                style={{ fill: on ? ON_COLOR : COIL_OFF_FILL, stroke: on ? ON_COLOR : SYMBOL_STROKE }}
                strokeWidth={2}
                filter={on ? `url(#${glowId})` : undefined}
            />
            <Wire x1={cx + r} y1={y} x2={el.x + el.width} y2={y} on={on} glowId={glowId} />
            {el.negated && (
                <line x1={cx - r} y1={y + r} x2={cx + r} y2={y - r} style={{ stroke: on ? COIL_OFF_FILL : SYMBOL_STROKE }} strokeWidth={2} />
            )}
            <Labels cx={cx} el={el} displayMode={displayMode} />
            {el.comment && (
                <text x={el.commentX} y={y + 4} fontSize={LABEL_FONT_SIZE + 1} className="ladder-comment-label">
                    {el.comment}
                </text>
            )}
        </Selectable>
    );
}

function FunctionGlyph({ el }) {
    const boxX = el.x + 4;
    const boxY = el.wireY - 14;
    const boxHeight = el.height - 20;
    const dividerX = boxX + 76;
    const operands = el.operands || [];
    const subLabel = el.sub == null ? el.subName : `SUB${el.sub}`;
    return (
        <g className="ladder-function">
            <title>{[subLabel, el.subName, ...operands.map(operand => [operand.value, operand.symbol].filter(value => value !== undefined && value !== '').join(' · '))].join(' ')}</title>
            <line x1={el.x} y1={el.wireY} x2={boxX} y2={el.wireY} style={{ stroke: WIRE_COLOR }} strokeWidth={2} />
            <rect x={boxX} y={boxY} width={el.width - 8} height={boxHeight} rx={6} style={{ fill: COIL_OFF_FILL, stroke: SYMBOL_STROKE }} strokeWidth={1.5} />
            {el.ports?.map(port => <text key={port.label} x={boxX - 8} y={el.wireY + port.offset - 8}
                textAnchor="end" fontSize={LABEL_FONT_SIZE} className="ladder-func-label">{port.label}</text>)}
            <line x1={boxX + el.width - 8} y1={el.wireY} x2={el.x + el.width} y2={el.wireY} style={{ stroke: WIRE_COLOR }} strokeWidth={2} />
            <text x={boxX + 8} y={boxY + 16} fontSize={LABEL_FONT_SIZE} className="ladder-func-label">
                {subLabel}
            </text>
            {el.subName !== subLabel && <text x={boxX + 8} y={boxY + 34} fontSize={LABEL_FONT_SIZE} className="ladder-func-label">{el.subName}</text>}
            {operands.length > 0 && <line x1={dividerX} y1={boxY} x2={dividerX} y2={boxY + boxHeight} style={{ stroke: SYMBOL_STROKE }} />}
            {operands.map((operand, index) => <g key={index}>
                <text x={dividerX + 8} y={boxY + 16 + index * ROW_HEIGHT} fontSize={LABEL_FONT_SIZE} className="ladder-addr-label">{String(operand.value)}</text>
                {operand.symbol && <text x={dividerX + 8} y={boxY + 34 + index * ROW_HEIGHT} fontSize={LABEL_FONT_SIZE} className="ladder-symbol-label">{operand.symbol}</text>}
            </g>)}
        </g>
    );
}

function FunctionDataTable({ el }) {
    return <g className="ladder-data-table" aria-label="CODB 변환 데이터 표">
        {Array.from({ length: Math.ceil(el.values.length / TABLE_COLUMNS) }, (_, row) => (
            <g key={row}>
                <text x={el.x} y={el.y + (row + 1) * TABLE_ROW_HEIGHT} fontSize={LABEL_FONT_SIZE} className="ladder-symbol-label">
                    {String(row * TABLE_COLUMNS).padStart(3, '0')}
                </text>
                {el.values.slice(row * TABLE_COLUMNS, (row + 1) * TABLE_COLUMNS).map((value, column) => (
                    <text key={column} x={el.x + 56 + column * 88} y={el.y + (row + 1) * TABLE_ROW_HEIGHT}
                        fontSize={LABEL_FONT_SIZE} className="ladder-addr-label">{value < 0 ? '-' : ''}{String(Math.abs(value)).padStart(5, '0')}</text>
                ))}
            </g>
        ))}
    </g>;
}

// 통전 여부: a접점=비트 1일 때, b접점(NOT)=비트 0일 때 통전(LADDER-III 온라인 표시와 동일).
// 코일은 비트 값 그대로. 아직 실시간 값을 못 읽은 주소는 표시하지 않는다.
function isOn(el, energizedSet, knownSet) {
    if (!el.address || !knownSet || !knownSet.has(el.address)) return false;
    const bit = energizedSet.has(el.address);
    return el.kind === 'contact' && el.negated ? !bit : bit;
}

/**
 * 왼쪽 레일에서 출발한 "전류"가 어디까지 흐르는지 계산해서 선 색을 정한다.
 * layoutNet()의 엘리먼트는 좌표만 갖고 있으므로 행(y)별로 왼쪽→오른쪽으로 훑는다.
 * - 왼쪽 레일에 닿지 않는 행(병렬/출력 분기의 아래 행)은 바로 위 행의 같은 x 지점
 *   통전 상태를 이어받는다.
 * - 세로선(병렬 합류점)은 그 x에서 끝나는 통전 구간이 하나라도 있으면 통전이고,
 *   통전된 합류점 오른쪽은 다시 통전으로 본다(OR). 이 두 단계를 2번 반복한다.
 */
function computePower(elements, energizedSet, knownSet, leftRailX) {
    const powered = new Array(elements.length).fill(false);
    const vwireOn = new Array(elements.length).fill(false);
    if (!knownSet || knownSet.size === 0) return { powered, vwireOn };

    const byRow = new Map();
    elements.forEach((el, i) => {
        if (el.kind === 'vwire') return;
        const y = el.kind === 'hwire' ? el.y : el.wireY;
        if (y === undefined) return;
        if (!byRow.has(y)) byRow.set(y, []);
        byRow.get(y).push({ el, i, x: el.kind === 'hwire' ? el.x1 : el.x });
    });
    const ys = [...byRow.keys()].sort((a, b) => a - b);
    ys.forEach((y) => byRow.get(y).sort((a, b) => a.x - b.x));
    const vwires = elements.map((el, i) => ({ el, i })).filter(({ el }) => el.kind === 'vwire');

    const runRows = () => {
        const trace = new Map();
        const powerAt = (y, x) => {
            let p = false;
            (trace.get(y) || []).forEach((pt) => { if (pt.x <= x + 0.5) p = pt.p; });
            return p;
        };
        ys.forEach((y, rowIdx) => {
            const items = byRow.get(y);
            const pts = [];
            let p;
            if (items[0].x <= leftRailX + 1) {
                p = true;
            } else {
                p = rowIdx > 0 ? powerAt(ys[rowIdx - 1], items[0].x) : false;
            }
            pts.push({ x: items[0].x, p });
            items.forEach(({ el, i }) => {
                // 통전된 합류점(세로선)이 이 지점에 닿아 있으면 여기부터 통전
                const boosted = vwires.some(({ el: v, i: vi }) => vwireOn[vi]
                    && Math.abs(v.x - (el.kind === 'hwire' ? el.x1 : el.x)) < 0.5
                    && y >= v.y1 - 0.5 && y <= v.y2 + 0.5);
                if (boosted) p = true;
                // CODB 출력은 RST/ACT 접점만으로 계산하지 않고 실제 코일 수신값을 사용한다.
                if (el.signalAddress) p = knownSet.has(el.signalAddress) && energizedSet.has(el.signalAddress);
                powered[i] = p;
                if (el.kind === 'function' && el.ports) {
                    p = false;
                    pts.push({ x: el.x + el.width, p });
                }
                if (el.kind === 'contact') {
                    p = p && isOn(el, energizedSet, knownSet);
                    pts.push({ x: el.x + el.width, p });
                }
            });
            trace.set(y, pts);
        });
    };

    const runVwires = () => {
        vwires.forEach(({ el: v, i: vi }) => {
            vwireOn[vi] = elements.some((other, j) => {
                if (!powered[j]) return false;
                if (other.kind === 'hwire') {
                    return Math.abs(other.x2 - v.x) < 0.5 && other.y >= v.y1 - 0.5 && other.y <= v.y2 + 0.5;
                }
                if (other.kind === 'contact') {
                    return Math.abs(other.x + other.width - v.x) < 0.5
                        && other.wireY >= v.y1 - 0.5 && other.wireY <= v.y2 + 0.5
                        && isOn(other, energizedSet, knownSet);
                }
                return false;
            });
        });
    };

    for (let pass = 0; pass < 2; pass += 1) {
        runRows();
        runVwires();
    }
    return { powered, vwireOn };
}

/**
 * =====================================================
 * LadderNetSvg
 * =====================================================
 * net 하나를 다크 테마 SVG로 그린다. 통전 경로는 라임색으로 은은하게 빛나게
 * 표시하고, 접점/코일은 클릭하면 onSelect(element, net, index)로 선택을 알리고,
 * 더블클릭하면 onJump(element, net, index)로 같은 주소의 다음 심볼 이동을 요청한다.
 * net끼리 간격 없이 붙여서 좌/우 레일이 한 줄로 이어져 보이게 한다.
 * =====================================================
 */
export default function LadderNetSvg({
    net, energizedSet, knownSet, railGap, zoom = 1, displayMode = 'both', selectedKey, selectedAddress = "", onSelect, onJump, highlighted = false,
}) {
    const { width, height, elements, leftRailX, rightRailX } = layoutNet(net, railGap);
    const hasWarning = net.warnings && net.warnings.length > 0;
    const glowId = `ladder-glow-${net.netIndex}`;
    const { powered, vwireOn } = computePower(elements, energizedSet, knownSet, leftRailX);

    // 이벤트에 원소 인덱스를 실어 보내려고 원소별로 감싼다
    const selectHandler = (i) => (el) => onSelect?.(el, net, i);
    const jumpHandler = (i) => (el) => onJump?.(el, net, i);

    return (
        <svg
            className={`ladder-net-svg${highlighted ? ' is-highlighted' : ''}`}
            data-net-index={net.netIndex}
            width={width * zoom}
            height={height * zoom}
            viewBox={`0 0 ${width} ${height}`}
        >
            <defs>
                {/* 가로선은 높이가 0이라 objectBoundingBox 기준 필터 영역이 0이 되어 선이
                    사라진다 - 필터 영역을 SVG 전체 좌표(userSpaceOnUse)로 잡는다. */}
                <filter id={glowId} filterUnits="userSpaceOnUse" x={0} y={0} width={width} height={height}>
                    <feGaussianBlur stdDeviation="2.4" result="blur" />
                    <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                    </feMerge>
                </filter>
            </defs>
            <text x={6} y={4 + WIRE_OFFSET + 4} fontSize={LABEL_FONT_SIZE - 1} className="ladder-net-no">
                {String(net.netIndex).padStart(3, '0')}
                {hasWarning ? ' ⚠' : ''}
                {hasWarning && <title>{net.warnings.join('\n')}</title>}
            </text>
            <line x1={leftRailX} y1={0} x2={leftRailX} y2={height} style={{ stroke: RAIL_COLOR }} strokeWidth={3} />
            <line x1={rightRailX} y1={0} x2={rightRailX} y2={height} style={{ stroke: RAIL_COLOR }} strokeWidth={3} />
            {elements.map((el, i) => {
                const on = isOn(el, energizedSet, knownSet);
                const selKey = selectionKey(net, i);
                const selected = selectedAddress ? el.address === selectedAddress : selectedKey === selKey;
                switch (el.kind) {
                    case 'contact':
                        return (
                            <ContactGlyph key={i} el={el} on={on} powerIn={powered[i]} displayMode={displayMode}
                                glowId={glowId} selKey={selKey} selected={selected}
                                onSelect={selectHandler(i)} onJump={jumpHandler(i)} />
                        );
                    case 'coil':
                        return (
                            <CoilGlyph key={i} el={el} on={on} powerIn={powered[i]} displayMode={displayMode}
                                glowId={glowId} selKey={selKey} selected={selected}
                                onSelect={selectHandler(i)} onJump={jumpHandler(i)} />
                        );
                    case 'function':
                        return <FunctionGlyph key={i} el={el} />;
                    case 'data-table':
                        return <FunctionDataTable key={i} el={el} />;
                    case 'hwire':
                        return <Wire key={i} x1={el.x1} y1={el.y} x2={el.x2} y2={el.y} on={powered[i]} glowId={glowId} />;
                    case 'vwire':
                        return <Wire key={i} x1={el.x} y1={el.y1} x2={el.x} y2={el.y2} on={vwireOn[i]} glowId={glowId} />;
                    default:
                        return null;
                }
            })}
        </svg>
    );
}

// 선택 키 - net 번호 + layoutNet() 원소 인덱스. 원소 순서는 레일 간격(railGap)과
// 무관해서, 더보기로 레일 간격이 바뀌어도 선택이 유지된다.
export function selectionKey(net, index) {
    return `${net.netIndex}:${index}`;
}
