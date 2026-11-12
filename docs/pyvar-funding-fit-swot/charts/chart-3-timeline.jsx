export default () => <claude.Visualize data-claude-component='deadline-timeline' sources={{rows:{kind:'data', data:[
{id:'a1', panel:'A', lane:0, kind:'span', from:'2026-11-17', to:'2026-11-24', label:'17–24 Nov: ask Innovate UK if the strand fits', pos:'d', anchor:'start'},
{id:'a3', panel:'A', lane:0, kind:'key', from:'2026-12-08', to:'2026-12-08', label:'8 Dec, 11:00: closes', pos:'u', anchor:'start'},
{id:'a4', panel:'A', lane:1, kind:'key', from:'2026-12-17', to:'2026-12-17', label:'17 Dec: opens (per the note)', pos:'u', anchor:'end'},
{id:'a5', panel:'A', lane:2, kind:'span', from:'2026-11-12', to:'2026-12-20', label:'Short proposals: any time; feedback in 4–6 weeks', pos:'u', anchor:'start'},
{id:'b1', panel:'B', lane:0, kind:'key', from:'2026-12-08', to:'2026-12-08', label:'8 Dec: closes', pos:'u', anchor:'start'},
{id:'b2', panel:'B', lane:0, kind:'dot', from:'2027-02-01', to:'2027-02-01', label:'1 Feb: decisions', pos:'u', anchor:'start'},
{id:'b3', panel:'B', lane:0, kind:'span', from:'2027-04-01', to:'2027-08-31', label:'Projects: start by 1 Apr, end by 31 Aug', pos:'u', anchor:'start'},
{id:'b4', panel:'B', lane:1, kind:'span', from:'2026-12-17', to:'2027-03-04', label:'17 Dec to 4 Mar: window (per the note)', pos:'u', anchor:'start'},
{id:'b5', panel:'B', lane:2, kind:'dot', from:'2027-01-20', to:'2027-01-20', label:'20 Jan', pos:'u', anchor:'middle'},
{id:'b6', panel:'B', lane:2, kind:'dot', from:'2027-03-17', to:'2027-03-17', label:'17 Mar', pos:'u', anchor:'middle'},
{id:'b7', panel:'B', lane:2, kind:'dot', from:'2027-09-01', to:'2027-09-01', label:'1 Sep', pos:'u', anchor:'middle'}
]}, lanes:{kind:'data', data:[
{lane:0, name:'BridgeAI', hue:1},
{lane:1, name:'Eurostars', hue:2},
{lane:2, name:'EIC Accelerator', hue:3}
]}, meta:{kind:'data', data:[
{today:'2026-11-12', aStart:'2026-11-09', aEnd:'2026-12-21', bStart:'2026-12-01', bEnd:'2027-10-01'}
]}}}>{({rows, lanes, meta, datum}) => {
const m = meta.at(0);
const DAY = 86400000, x0 = 130, w = 606, lh = 52;
const hue = h => h === 1 ? 'var(--cds-chart-categorical-1)' : h === 2 ? 'var(--cds-chart-categorical-2)' : 'var(--cds-chart-categorical-3)';
const laneHue = l => hue(l.hue);
const rowHue = r => r.lane === 0 ? hue(1) : r.lane === 1 ? hue(2) : hue(3);
const t0 = r => r.panel === 'A' ? Date.parse(m.aStart) : Date.parse(m.bStart);
const t1 = r => r.panel === 'A' ? Date.parse(m.aEnd) : Date.parse(m.bEnd);
const sx = (r, d) => x0 + (Date.parse(d) - t0(r)) / (t1(r) - t0(r)) * w;
const py = r => (r.panel === 'A' ? 96 : 304) + r.lane * lh;
const close = Math.round((Date.parse(rows.find(r => r.id === 'a3').from) - Date.parse(m.today)) / DAY);
const title = 'BridgeAI closes in ' + close + ' days, before Eurostars opens; EIC short proposals can go in any time';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ticksA = [0, 1, 2, 3, 4, 5].map(i => Date.parse(m.aStart) + i * 7 * DAY);
const ticksB = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => Date.UTC(2026, 11 + i, 1));
const fa = Date.parse(m.aStart), la = Date.parse(m.aEnd), fb = Date.parse(m.bStart), lb = Date.parse(m.bEnd);
const ax = t => x0 + (t - fa) / (la - fa) * w;
const bx = t => x0 + (t - fb) / (lb - fb) * w;
const dl = t => new Date(t).getUTCDate() + ' ' + MON[new Date(t).getUTCMonth()];
const ml = t => MON[new Date(t).getUTCMonth()] + (new Date(t).getUTCMonth() === 0 ? ' ' + new Date(t).getUTCFullYear() : '');
const todayX = ax(Date.parse(m.today));
return <svg viewBox='0 0 760 536' role='img' aria-label={title} fontSize='12'>
<text x='24' y='28' fontSize='16' fill='var(--cds-text-primary)'>{title}</text>
<text data-claude-text-id='subtitle' x='24' y='50' fill='var(--cds-text-secondary)'>Two views of the same dates: the next six weeks, then the period to September 2027.</text>
<text data-claude-text-id='panel-a' x='24' y='78' fontWeight='600' fill='var(--cds-text-primary)'>Next six weeks</text>
<g data-claude-anchor='axis-a'>
<line x1={x0} x2={x0 + w} y1={252} y2={252} stroke='var(--cds-chart-axis)' />
{ticksA.map(t => <g key={t}><line x1={ax(t)} x2={ax(t)} y1={252} y2={257} stroke='var(--cds-chart-axis)' /><text x={ax(t)} y={271} textAnchor='middle' fontSize='11' fill='var(--cds-text-secondary)'>{dl(t)}</text></g>)}
<line x1={todayX} x2={todayX} y1={88} y2={252} stroke='var(--cds-chart-reference)' strokeDasharray='4 3' />
<text x={todayX + 5} y={100} fontSize='11' fill='var(--cds-text-secondary)'>{'Today, ' + dl(Date.parse(m.today))}</text>
</g>
<text data-claude-text-id='panel-b' x='24' y='302' fontWeight='600' fill='var(--cds-text-primary)'>To September 2027</text>
<g data-claude-anchor='axis-b'>
<line x1={x0} x2={x0 + w} y1={462} y2={462} stroke='var(--cds-chart-axis)' />
{ticksB.map(t => <g key={t}><line x1={bx(t)} x2={bx(t)} y1={462} y2={467} stroke='var(--cds-chart-axis)' /><text x={bx(t)} y={480} textAnchor='middle' fontSize='11' fill='var(--cds-text-secondary)'>{ml(t)}</text></g>)}
</g>
<g data-claude-anchor='lane-labels'>
{lanes.map(l => <g key={l.name}>
<text x={24} y={96 + l.lane * lh + 30} fontWeight='600' fill='var(--cds-text-primary)'>{l.name}</text>
<rect x={24} y={96 + l.lane * lh + 36} width='28' height='4' rx='2' fill={laneHue(l)} />
<text x={24} y={304 + l.lane * lh + 30} fontWeight='600' fill='var(--cds-text-primary)'>{l.name}</text>
<rect x={24} y={304 + l.lane * lh + 36} width='28' height='4' rx='2' fill={laneHue(l)} />
</g>)}
</g>
<g data-claude-anchor='events'>
{rows.map(r => <g key={r.id}>
{r.kind === 'span'
? <rect x={sx(r, r.from)} y={py(r) + 23} width={Math.max(sx(r, r.to) - sx(r, r.from), 4)} height='8' rx='4' fill={rowHue(r)} fillOpacity='0.85' {...datum(r, 'from')}><title>{r.label}</title></rect>
: r.kind === 'key'
? <rect x={sx(r, r.from) - 7} y={py(r) + 20} width='14' height='14' rx='2' transform={'rotate(45 ' + sx(r, r.from) + ' ' + (py(r) + 27) + ')'} fill={rowHue(r)} {...datum(r, 'from')}><title>{r.label}</title></rect>
: <circle cx={sx(r, r.from)} cy={py(r) + 27} r='5' fill={rowHue(r)} stroke='var(--cds-surface, #fff)' strokeWidth='2' {...datum(r, 'from')}><title>{r.label}</title></circle>}
<text x={r.anchor === 'middle' ? sx(r, r.from) : r.anchor === 'end' ? sx(r, r.to) + 2 : sx(r, r.from) + 6} y={r.pos === 'u' ? py(r) + 14 : py(r) + 48} textAnchor={r.anchor} fontSize='11' fill='var(--cds-text-primary)'>{r.label}</text>
</g>)}
</g>
<text data-claude-text-id='note-1' x='24' y='506' fontSize='11' fill='var(--cds-text-secondary)'>BridgeAI and EIC dates: official pages, read 12 Nov 2026. Eurostars dates: the owner’s note, not yet confirmed on an official page.</text>
<text data-claude-text-id='note-2' x='24' y='522' fontSize='11' fill='var(--cds-text-secondary)'>EIC marks are full-proposal cut-offs (5pm Brussels); the next after September is 4 Nov 2027. Diamonds are closing or opening dates.</text>
</svg>; }}</claude.Visualize>;
