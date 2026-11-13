// Renders one chart source (docs/pyvar-funding-fit-swot/charts/*.jsx) to a PNG, outside Claude's visualisation runtime.
// The sources are written for Claude's `claude.Visualize` component, which exists only there; this script supplies a minimal
// stand-in (it hands each data source to the render function and ignores `datum`, which only tags marks for editing), runs the
// source through esbuild and React's server renderer, and screenshots the SVG with Playwright's Chromium at 2x scale.
// Checked by re-rendering chart 2 and comparing it with the PNG first committed for it: mean difference 0.000, 0% of pixels differ.
//
// Setup (once, in a folder outside the repository, so nothing is added to it):
//   mkdir chart-deps && cd chart-deps && npm init -y && npm install esbuild@0.21.5 react@18.3.1 react-dom@18.3.1
// Run, from the repository root:
//   CHART_DEPS=/path/to/chart-deps node docs/pyvar-funding-fit-swot/charts/render_chart.mjs \
//     docs/pyvar-funding-fit-swot/charts/chart-1-programme-map.jsx docs/pyvar-funding-fit-swot/chart-1-programme-map.png
// CHART_DEPS is the folder that holds node_modules. PLAYWRIGHT_MODULE works as in build_pdf.mjs.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(path.join(path.resolve(process.env.CHART_DEPS || '.'), 'noop.js'));
const esbuild = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const [src, out] = process.argv.slice(2);
// The sources are written for a component that hands each data source to a render function as an array and
// returns whatever that function returns; `datum` only tags marks for editing and adds nothing visible.
globalThis.React = React;
globalThis.claude = {
  Visualize: ({ sources, children }) =>
    children({ ...Object.fromEntries(Object.entries(sources).map(([k, v]) => [k, v.data])), datum: () => ({}) }),
};
const built = esbuild.transformSync(fs.readFileSync(src, 'utf8'), { loader: 'jsx', jsx: 'transform', jsxFactory: 'React.createElement', format: 'esm' });
const tmp = path.join(os.tmpdir(), 'chart-' + process.pid + '.mjs');
fs.writeFileSync(tmp, built.code);
const Chart = (await import(pathToFileURL(tmp).href)).default;
fs.rmSync(tmp);
const svg = renderToStaticMarkup(React.createElement(Chart));
const [vw, vh] = svg.match(/viewBox="0 0 (\d+) (\d+)"/).slice(1).map(Number);

// Design tokens the sources refer to, sampled from the PNGs first committed with them.
const vars = {
  '--cds-text-primary': '#1b1b19', '--cds-text-secondary': '#5e5d59', '--cds-surface': '#ffffff',
  '--cds-chart-axis': '#9d9c96', '--cds-chart-grid': '#e6e5e0', '--cds-chart-reference': '#77766f',
  '--cds-chart-status-warning': '#dfa201', '--cds-chart-status-critical': '#d84545', '--cds-chart-status-good': '#2a9d6a',
  '--cds-chart-muted': '#b7b7b1',
  '--cds-chart-categorical-1': '#2f6fdb', '--cds-chart-categorical-2': '#d2691e', '--cds-chart-categorical-3': '#2a9d8f',
};
const css = ':root{' + Object.entries(vars).map(([k, v]) => k + ':' + v).join(';') + '}body{margin:0;background:#fff;font-family:Inter,sans-serif}svg{display:block;width:' + vw + 'px;height:' + vh + 'px}';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: 2 });
await page.setContent('<style>' + css + '</style>' + svg);
await page.locator('svg').screenshot({ path: out });
await browser.close();
console.log('wrote', out, vw * 2 + 'x' + vh * 2);
