// Converts a tailored Markdown draft (lib/promptBuild.js's output) into a PDF
// buffer for download. Most ATS upload fields reject .md, so the file that
// leaves the app has to be a PDF — this is the one place that conversion
// happens, on demand at download time, so it always reflects whatever is
// currently on disk (including a hand-edit made after generation).

import { chromium } from "playwright";
import { marked } from "marked";

// Matches the shape every base-resume.md / draft actually has: H1 name, a
// contact line, H2 section headers, H3 employer/program lines, bold
// role+dates, bullet lists. Kept plain and print-safe rather than themed —
// this is what an ATS parser and a human reviewer both see.
const RESUME_CSS = `
  @page { size: Letter; margin: 0.55in 0.65in; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.38;
    color: #1a1a1a;
  }
  h1 {
    font-size: 19pt;
    margin: 0 0 2pt 0;
  }
  h1 + p {
    margin: 0 0 10pt 0;
    color: #333;
    font-size: 9.5pt;
  }
  h2 {
    font-size: 11.5pt;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #999;
    margin: 14pt 0 6pt 0;
    padding-bottom: 2pt;
  }
  h2:first-of-type { margin-top: 0; }
  h3 {
    font-size: 10.5pt;
    margin: 8pt 0 0 0;
  }
  h3 + p {
    margin: 1pt 0 4pt 0;
  }
  p { margin: 0 0 6pt 0; }
  ul {
    margin: 2pt 0 8pt 0;
    padding-left: 16pt;
  }
  li {
    margin-bottom: 2.5pt;
    break-inside: avoid;
  }
  strong { font-weight: 600; }
  a { color: #1a1a1a; text-decoration: none; }
`;

function markdownToHtml(markdown) {
  const body = marked.parse(markdown, { breaks: false });
  return `<!doctype html><html><head><meta charset="utf-8"><style>${RESUME_CSS}</style></head><body>${body}</body></html>`;
}

// Renders `markdown` to a PDF buffer. One-shot: launches Chromium, renders,
// closes — this runs at most once per download click, not worth pooling.
export async function renderMarkdownToPdf(markdown) {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setContent(markdownToHtml(markdown), { waitUntil: "load" });
    return await page.pdf({ format: "Letter", printBackground: true });
  } finally {
    await browser.close();
  }
}
