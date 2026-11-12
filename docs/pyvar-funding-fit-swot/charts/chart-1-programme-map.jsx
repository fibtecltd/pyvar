export default () => <claude.Visualize data-claude-component='programme-map' sources={{rows:{kind:'data', data:[
{slug:'bridgeai', name:'BridgeAI', low:100, high:200, held:2, asked:7, when:'closes 8 Dec 2026', side:'r', hue:1, dy:0},
{slug:'eurostars', name:'Eurostars', low:306, high:306, held:1, asked:4, when:'closes 4 Mar 2027', side:'l', hue:2, dy:-22},
{slug:'eic', name:'EIC Accelerator', low:2125, high:2125, held:1, asked:6, when:'next full cut-off 17 Mar 2027', side:'r', hue:3, dy:0}
]}}}>{({rows, datum}) => {
const left = 84, y0 = 96, w = 636, h = 236;
const lo = Math.log(70), hi = Math.log(3500);
const px = v => left + v / 50 * w;
const py = v => y0 + h - (Math.log(v) - lo) / (hi - lo) * h;
const pct = r => r.held / r.asked * 100;
const money = v => v >= 1000 ? '£' + (v / 1000).toFixed(1).replace('.0', '') + 'm' : '£' + v + 'k';
const award = r => r.low === r.high ? 'up to about ' + money(r.high) : money(r.low) + ' to ' + money(r.high);
const hue = r => r.hue === 1 ? 'var(--cds-chart-categorical-1)' : r.hue === 2 ? 'var(--cds-chart-categorical-2)' : 'var(--cds-chart-categorical-3)';
const best = rows.reduce((a, r) => pct(r) > pct(a) ? r : a);
const least = rows.reduce((a, r) => pct(r) < pct(a) ? r : a);
const title = 'None of the three is close: ' + Math.round(pct(least)) + '% to ' + Math.round(pct(best)) + '% of asks held';
return <svg viewBox='0 0 760 430' role='img' aria-label={title} fontSize='12'>
<text x='24' y='28' fontSize='16' fill='var(--cds-text-primary)'>{title}</text>
<text data-claude-text-id='subtitle' x='24' y='50' fill='var(--cds-text-secondary)'>Award size against the share of each programme's asks we already hold. Euros converted at about £0.85.</text>
<g data-claude-anchor='y-axis'>
{[100, 300, 1000, 3000].map(v => <g key={v}><line x1={left} x2={left + w} y1={py(v)} y2={py(v)} stroke='var(--cds-chart-grid)' /><text x={left - 10} y={py(v) + 4} textAnchor='end' fill='var(--cds-text-secondary)'>{money(v)}</text></g>)}
<text data-claude-text-id='y-label' x='24' y='84' fill='var(--cds-text-secondary)'>Award size (log scale)</text>
</g>
<g data-claude-anchor='x-axis'>
<line x1={left} x2={left + w} y1={y0 + h} y2={y0 + h} stroke='var(--cds-chart-axis)' />
{[0, 10, 20, 30, 40, 50].map(v => <g key={v}><line x1={px(v)} x2={px(v)} y1={y0 + h} y2={y0 + h + 5} stroke='var(--cds-chart-axis)' /><text x={px(v)} y={y0 + h + 20} textAnchor='middle' fill='var(--cds-text-secondary)'>{v + '%'}</text></g>)}
<text data-claude-text-id='x-label' x={left + w / 2} y={y0 + h + 42} textAnchor='middle' fill='var(--cds-text-secondary)'>Share of the programme's asks we already hold today</text>
</g>
<g data-claude-anchor='programmes'>
{rows.map(r => <g key={r.slug} data-claude-anchor={'programme-' + r.slug}>
{r.low === r.high
? <circle cx={px(pct(r))} cy={py(r.high)} r='8' fill={hue(r)} stroke='var(--cds-surface, #fff)' strokeWidth='2' {...datum(r, 'held')}><title>{r.name + ': ' + Math.round(pct(r)) + '% of asks held, ' + award(r)}</title></circle>
: <rect x={px(pct(r)) - 6} y={py(r.high)} width='12' height={py(r.low) - py(r.high)} rx='6' fill={hue(r)} {...datum(r, 'held')}><title>{r.name + ': ' + Math.round(pct(r)) + '% of asks held, ' + award(r)}</title></rect>}
<text x={px(pct(r)) + (r.side === 'l' ? -16 : 16)} y={py(r.high) - 2 + r.dy} textAnchor={r.side === 'l' ? 'end' : 'start'} fontWeight='600' fill='var(--cds-text-primary)'>{r.name + ' · ' + Math.round(pct(r)) + '% held'}</text>
<text x={px(pct(r)) + (r.side === 'l' ? -16 : 16)} y={py(r.high) + 14 + r.dy} textAnchor={r.side === 'l' ? 'end' : 'start'} fill='var(--cds-text-secondary)'>{award(r) + ' · ' + r.when}</text>
</g>)}
</g>
<text data-claude-text-id='note' x='24' y='418' fontSize='11' fill='var(--cds-text-secondary)'>Held: Have = 1, Partly = ½, Gap and To check = 0; “Not asked” rows are left out. A judgement, for the adviser to overrule.</text>
</svg>; }}</claude.Visualize>;
