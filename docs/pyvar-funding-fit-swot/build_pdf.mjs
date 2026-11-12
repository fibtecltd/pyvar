// Builds docs/pyvar-funding-fit-swot/pyvar-funding-fit-swot.pdf from docs/pyvar-funding-fit-swot.md.
// Needs pandoc and Playwright's Chromium (set PLAYWRIGHT_MODULE to its path if it does not resolve from the repository root). From the repository root:
//   node docs/pyvar-funding-fit-swot/build_pdf.mjs
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const root = path.resolve(new URL('../..', import.meta.url).pathname);
const docs = path.join(root, 'docs');
const outDir = path.join(docs, 'pyvar-funding-fit-swot');
const require = createRequire(root + '/');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const css = `
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Inter, "Helvetica Neue", Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1b1b19; }
h1 { font-size: 20pt; margin: 0 0 6pt; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1px solid #d9d8d3; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
li { margin: 2pt 0; }
img { display: block; width: 90%; height: auto; break-inside: avoid; margin: 6pt auto; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 8.6pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #d9d8d3; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: #f3f2ee; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 8.4pt; background: #f3f2ee; padding: 0 2pt; border-radius: 2pt; overflow-wrap: anywhere; }
a { color: #1d4ed8; overflow-wrap: anywhere; }
ul.task-list { list-style: none; padding-left: 4pt; }
input[type=checkbox] { margin-right: 5pt; }
`;

const mdPath = path.join(docs, 'pyvar-funding-fit-swot.md');
const cssPath = path.join(outDir, '.pdf.css');
const htmlPath = path.join(outDir, '.pdf.html');
fs.writeFileSync(cssPath, css);
execFileSync('pandoc', ['-f', 'gfm', '-t', 'html5', '--standalone', '--embed-resources', '--css', cssPath,
  '--metadata', 'title=pyvar: funding fit SWOT', '--metadata', 'pagetitle=pyvar: funding fit SWOT',
  '-o', htmlPath, mdPath], { cwd: docs, stdio: 'inherit' });
// pandoc prints the metadata title as a heading; the document already has its own h1.
fs.writeFileSync(htmlPath, fs.readFileSync(htmlPath, 'utf8').replace(/<header id="title-block-header">[\s\S]*?<\/header>/, ''));

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('file://' + htmlPath);
await page.pdf({
  path: path.join(outDir, 'pyvar-funding-fit-swot.pdf'), format: 'A4', printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: '<div style="font:8px Helvetica,Arial,sans-serif;color:#777;width:100%;padding:0 16mm;display:flex;justify-content:space-between"><span>pyvar: funding fit SWOT · version 1 · 12 November 2026</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
  margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' },
});
await browser.close();
fs.rmSync(cssPath); fs.rmSync(htmlPath);
console.log('wrote', path.join(outDir, 'pyvar-funding-fit-swot.pdf'));
