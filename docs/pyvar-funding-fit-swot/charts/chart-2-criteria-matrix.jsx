export default () => <claude.Visualize data-claude-component='criteria-matrix' sources={{rows:{kind:'data', data:[
{row:0, col:0, dim:'Applicant eligibility', prog:'BridgeAI', status:'check', label:'To check', note:'SME status to confirm'},
{row:0, col:1, dim:'Applicant eligibility', prog:'Eurostars', status:'check', label:'To check', note:'SME, age, headcount: confirm'},
{row:0, col:2, dim:'Applicant eligibility', prog:'EIC Accelerator', status:'check', label:'To check', note:'Grant only; SME to confirm'},
{row:1, col:0, dim:'Scope fit (own test)', prog:'BridgeAI', status:'partly', label:'Partly', note:'Assistant exists; fit to test'},
{row:1, col:1, dim:'Scope fit (own test)', prog:'Eurostars', status:'partly', label:'Partly', note:'R&D question drafted'},
{row:1, col:2, dim:'Scope fit (own test)', prog:'EIC Accelerator', status:'gap', label:'Gap', note:'No breakthrough shown'},
{row:2, col:0, dim:'Technology readiness', prog:'BridgeAI', status:'partly', label:'Partly', note:'MVP in dev; typed path off'},
{row:2, col:1, dim:'Technology readiness', prog:'Eurostars', status:'none', label:'Not asked', note:'No TRL stated'},
{row:2, col:2, dim:'Technology readiness', prog:'EIC Accelerator', status:'partly', label:'Partly', note:'Live; TRL 6–8 case to make'},
{row:3, col:0, dim:'Independent evidence', prog:'BridgeAI', status:'partly', label:'Partly', note:'Own evaluation; no outsider'},
{row:3, col:1, dim:'Independent evidence', prog:'Eurostars', status:'none', label:'Not asked', note:'Can be the R&D itself'},
{row:3, col:2, dim:'Independent evidence', prog:'EIC Accelerator', status:'gap', label:'Gap', note:'Not independently validated'},
{row:4, col:0, dim:'Partner in place', prog:'BridgeAI', status:'gap', label:'Gap', note:'No medium/large UK deployer'},
{row:4, col:1, dim:'Partner in place', prog:'Eurostars', status:'gap', label:'Gap', note:'No partner identified'},
{row:4, col:2, dim:'Partner in place', prog:'EIC Accelerator', status:'none', label:'Not asked', note:'Single applicant'},
{row:5, col:0, dim:'IP and market traction', prog:'BridgeAI', status:'gap', label:'Gap', note:'No named deployment yet'},
{row:5, col:1, dim:'IP and market traction', prog:'Eurostars', status:'none', label:'Not asked', note:'Not stated on page read'},
{row:5, col:2, dim:'IP and market traction', prog:'EIC Accelerator', status:'gap', label:'Gap', note:'Open source; no named client'},
{row:6, col:0, dim:'Match funding', prog:'BridgeAI', status:'partly', label:'Partly', note:'Own share; sum not shown'},
{row:6, col:1, dim:'Match funding', prog:'Eurostars', status:'partly', label:'Partly', note:'Own 40%; sum not shown'},
{row:6, col:2, dim:'Match funding', prog:'EIC Accelerator', status:'partly', label:'Partly', note:'Own 30%; sum not shown'}
]}}}>{({rows, datum}) => {
const x0 = 200, cw = 176, gap = 6, y0 = 100, ch = 50, rg = 6;
const cx = r => x0 + r.col * (cw + gap);
const cy = r => y0 + r.row * (ch + rg);
const fill = r => r.status === 'partly' ? 'var(--cds-chart-status-warning)' : r.status === 'gap' ? 'var(--cds-chart-status-critical)' : r.status === 'have' ? 'var(--cds-chart-status-good)' : r.status === 'none' ? 'var(--cds-chart-muted)' : 'none';
const op = r => r.status === 'none' ? 0.18 : r.status === 'check' ? 0 : 0.28;
const credit = r => r.status === 'have' ? 1 : r.status === 'partly' ? 0.5 : 0;
const heads = rows.filter(r => r.row === 0);
const dims = rows.filter(r => r.col === 0);
const ready = h => { const asked = rows.filter(r => r.col === h.col && r.status !== 'none'); return Math.round(asked.reduce((s, r) => s + credit(r), 0) / asked.length * 100); };
const lg = [{s:'partly', t:'Partly'}, {s:'gap', t:'Gap'}, {s:'check', t:'To check'}, {s:'none', t:'Not asked'}];
return <svg viewBox='0 0 760 572' role='img' aria-label='What each programme asks, and how much of it pyvar holds today' fontSize='12'>
<text data-claude-text-id='title' x='24' y='28' fontSize='16' fill='var(--cds-text-primary)'>No programme’s asks are fully met today; the gaps differ by programme</text>
<text data-claude-text-id='subtitle' x='24' y='50' fill='var(--cds-text-secondary)'>Seven asks compared across the three programmes, rated from the official pages and our records.</text>
<g data-claude-anchor='column-heads'>
{heads.map(r => <g key={r.prog}><text x={cx(r)} y={78} fontWeight='600' fill='var(--cds-text-primary)'>{r.prog}</text><text x={cx(r)} y={94} fontSize='11' fill='var(--cds-text-secondary)'>{ready(r) + '% of asks held'}</text></g>)}
</g>
<g data-claude-anchor='row-labels'>
{dims.map(r => <text key={r.dim} x={24} y={cy(r) + ch / 2 + 4} fill='var(--cds-text-primary)'>{r.dim}</text>)}
</g>
<g data-claude-anchor='cells'>
{rows.map(r => <g key={r.row + '-' + r.col}>
<rect x={cx(r)} y={cy(r)} width={cw} height={ch} rx='6' fill={fill(r)} fillOpacity={op(r)} stroke={r.status === 'check' ? 'var(--cds-chart-axis)' : 'none'} strokeDasharray={r.status === 'check' ? '4 3' : 'none'} {...datum(r, 'status')}><title>{r.prog + ' · ' + r.dim + ': ' + r.label + '. ' + r.note}</title></rect>
<text x={cx(r) + 10} y={cy(r) + 20} fontWeight='600' fill='var(--cds-text-primary)'>{r.label}</text>
<text x={cx(r) + 10} y={cy(r) + 38} fontSize='10.5' fill='var(--cds-text-secondary)'>{r.note}</text>
</g>)}
</g>
<g data-claude-anchor='legend'>
{lg.map((l, i) => <g key={l.s}><rect x={24 + i * 104} y={516} width='16' height='16' rx='4' fill={l.s === 'partly' ? 'var(--cds-chart-status-warning)' : l.s === 'gap' ? 'var(--cds-chart-status-critical)' : l.s === 'none' ? 'var(--cds-chart-muted)' : 'none'} fillOpacity={l.s === 'none' ? 0.18 : 0.28} stroke={l.s === 'check' ? 'var(--cds-chart-axis)' : 'none'} strokeDasharray={l.s === 'check' ? '4 3' : 'none'} /><text x={24 + i * 104 + 24} y={529} fill='var(--cds-text-secondary)'>{l.t}</text></g>)}
</g>
<text data-claude-text-id='note' x='24' y='556' fontSize='11' fill='var(--cds-text-secondary)'>“To check” means we lack the fact, not that the answer is no. “Not asked” means the programme page does not ask for it.</text>
</svg>; }}</claude.Visualize>;
