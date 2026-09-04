/** A simulated run of the diagnostics engine's snapshot output.
 *
 *  Client-only and openly synthetic — the real engine reads /proc, which does
 *  not exist in a browser, and pretending otherwise would be a lie told to
 *  make a demo look better. It exists to show the *shape* of the output: what
 *  the C++ layer emits, what the Python layer merges in, and where the LLM
 *  summary attaches.
 *
 *  Starts only when scrolled into view, and stops when it leaves. */

const LINES = [
  { k: 'engine', v: 'libsysdiag 0.3.1 (C++20)', d: 90 },
  { k: 'source', v: '/proc/meminfo, /proc/stat, /proc/net/dev', d: 120 },
  { sep: true },
  { k: 'mem.total', v: '32.0 GiB', d: 70 },
  { k: 'mem.available', v: '4.2 GiB', bar: 0.87, warn: true, d: 110 },
  { k: 'mem.swap_used', v: '3.1 GiB', bar: 0.62, warn: true, d: 90 },
  { k: 'cpu.load_1m', v: '2.14', d: 70 },
  { k: 'cpu.iowait', v: '11.3%', bar: 0.11, d: 90 },
  { sep: true },
  { k: 'net.ping[1.1.1.1]', v: '14.2 ms', d: 130 },
  { k: 'net.dns[cloudflare]', v: '31 ms', d: 100 },
  { k: 'net.port[443]', v: 'open', d: 80 },
  { k: 'net.retrans', v: '0.8%', d: 90 },
  { sep: true },
  { k: 'analyzer', v: 'gemini · structured prompt', d: 160 },
  { note: 'Memory pressure is the bottleneck, not the network. Swap is', d: 60 },
  { note: 'absorbing 3.1 GiB while iowait sits at 11.3% — the disk is', d: 60 },
  { note: 'paying for RAM. Close the largest resident process or add swap', d: 60 },
  { note: 'headroom before investigating latency further.', d: 60 },
];

function lineHtml(item) {
  if (item.sep) return '<div>&nbsp;</div>';
  if (item.note) return `<div class="k">  ${item.note}</div>`;

  const bar = item.bar
    ? ` <span class="bar">${'█'.repeat(Math.round(item.bar * 14)).padEnd(14, '·')}</span>`
    : '';
  const cls = item.warn ? 'warn' : 'v';
  return `<div><span class="k">${item.k.padEnd(22, ' ')}</span><span class="${cls}">${item.v}</span>${bar}</div>`;
}

export function mountTelemetry(root) {
  root.innerHTML = `
    <div class="demo">
      <div class="demo-head">
        <div class="demo-title">
          <span>SYS.DIAGNOSTICS</span>
          <span style="color:var(--faint)">/</span>
          <span>telemetry readout</span>
        </div>
        <span class="demo-badge" style="color:var(--muted);border-color:var(--line-bright)">simulated</span>
      </div>
      <div style="padding:1.3rem">
        <div class="readout" data-role="out"></div>
      </div>
      <div class="demo-foot">
        Synthetic sample data. The real engine reads /proc, which a browser does
        not have — this shows the output shape, not a live machine.
      </div>
    </div>`;

  const out = root.querySelector('[data-role="out"]');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let i = 0;
  let timer = null; // non-null means a step is queued

  const step = () => {
    if (i >= LINES.length) {
      timer = null;
      return;
    }
    out.insertAdjacentHTML('beforeend', lineHtml(LINES[i]));
    out.scrollTop = out.scrollHeight;
    const d = LINES[i].d ?? 80;
    i += 1;
    timer = setTimeout(step, d);
  };

  if (reduced) {
    out.innerHTML = LINES.map(lineHtml).join('');
    return;
  }

  // Print while visible, hold while not, and resume from where it stopped.
  const io = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        if (timer === null && i < LINES.length) step();
      } else {
        clearTimeout(timer);
        timer = null;
      }
    },
    { threshold: 0.25 }
  );
  io.observe(out);
}
