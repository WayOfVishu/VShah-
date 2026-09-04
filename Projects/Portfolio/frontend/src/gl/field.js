/**
 * The hero's background field.
 *
 * A domain-warped fBm rendered as thin contour lines, plus a technical grid, a
 * slow horizontal sweep, and a soft light that follows the cursor. Amber and
 * teal on charcoal, matching the rest of the site.
 *
 * Hand-rolled WebGL2 rather than three.js: this is one fullscreen triangle and
 * one fragment shader, so a 600KB scene-graph library would be almost entirely
 * dead weight on the critical path. No vertex buffer either — the triangle is
 * generated from gl_VertexID.
 *
 * It gives up gracefully in three ways: no WebGL2 leaves the CSS gradient
 * underneath visible, prefers-reduced-motion draws exactly one static frame,
 * and scrolling the hero offscreen (or hiding the tab) stops the loop so it
 * costs nothing to leave the page open.
 */

const VERT = `#version 300 es
// Fullscreen triangle from the vertex id. No attributes, no buffers.
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision highp float;
out vec4 fragColor;

uniform vec2  uRes;
uniform float uTime;
uniform vec2  uMouse;    // 0..1, smoothed in JS
uniform float uIntensity;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);            // smoothstep fade
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0, amp = 0.5;
  for (int i = 0; i < 5; i++) {
    v += amp * noise(p);
    p *= 2.02;                                  // slightly off 2.0 to break up tiling
    amp *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p  = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;

  float t = uTime * 0.045;

  // Two rounds of domain warping. One looks like noise; two looks like flow.
  vec2 q = vec2(fbm(p * 1.6 + t), fbm(p * 1.6 + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p * 1.6 + 2.0 * q + vec2(1.7, 9.2) + 0.15 * t),
                fbm(p * 1.6 + 2.0 * q + vec2(8.3, 2.8) - 0.13 * t));
  float f = fbm(p * 1.6 + 2.0 * r);

  // Slice the field into contour bands, then keep only the band edges, so the
  // result reads as topography rather than as fog.
  float bands = fract(f * 7.0 - t * 0.55);
  float edge  = 1.0 - (smoothstep(0.0, 0.055, bands) * smoothstep(1.0, 0.945, bands));

  vec3 bg    = vec3(0.047, 0.055, 0.075);
  vec3 amber = vec3(0.886, 0.639, 0.231);
  vec3 teal  = vec3(0.310, 0.690, 0.647);

  vec3 col = bg;
  col += amber * edge * 0.17 * smoothstep(0.20, 0.90, f);
  col += teal  * edge * 0.11 * (1.0 - smoothstep(0.10, 0.70, f));

  // Technical grid, kept crisp at any DPR by measuring in screen-space derivs.
  vec2 gv = uv * vec2(56.0, 32.0);
  vec2 gw = fwidth(gv);
  vec2 gf = abs(fract(gv - 0.5) - 0.5) / max(gw, vec2(1e-5));
  float grid = 1.0 - min(min(gf.x, gf.y), 1.0);
  col += vec3(0.33, 0.38, 0.48) * grid * 0.055;

  // Cursor light.
  float aspect = uRes.x / uRes.y;
  float md = length((uv - uMouse) * vec2(aspect, 1.0));
  col += amber * 0.085 * exp(-md * 3.6);

  // Slow sweep, bottom to top.
  float sweep = fract(uTime * 0.055);
  col += teal * 0.055 * exp(-abs(uv.y - sweep) * 90.0);

  // Vignette, then dither: at these low contrasts 8-bit output bands visibly,
  // and a sub-LSB of noise is cheaper than rendering to a float target.
  float vig = smoothstep(1.15, 0.25, length(uv - 0.5));
  col *= mix(0.55, 1.0, vig);
  col *= uIntensity;
  col += (hash(gl_FragCoord.xy + uTime) - 0.5) / 255.0;

  fragColor = vec4(col, 1.0);
}`;

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn('[field] shader compile failed:', gl.getShaderInfoLog(sh));
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

export function initField(canvas) {
  const gl = canvas.getContext('webgl2', {
    antialias: false,
    alpha: false,
    depth: false,
    stencil: false,
    powerPreference: 'low-power',
  });

  // No WebGL2: the CSS gradient behind the canvas is the fallback, so just
  // leave the canvas transparent and say so.
  if (!gl) {
    canvas.style.display = 'none';
    return { supported: false, destroy() {} };
  }

  const vs = compile(gl, gl.VERTEX_SHADER, VERT);
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) {
    canvas.style.display = 'none';
    return { supported: false, destroy() {} };
  }

  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.warn('[field] link failed:', gl.getProgramInfoLog(prog));
    canvas.style.display = 'none';
    return { supported: false, destroy() {} };
  }
  gl.useProgram(prog);

  const uRes = gl.getUniformLocation(prog, 'uRes');
  const uTime = gl.getUniformLocation(prog, 'uTime');
  const uMouse = gl.getUniformLocation(prog, 'uMouse');
  const uIntensity = gl.getUniformLocation(prog, 'uIntensity');

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const mouse = { x: 0.5, y: 0.55 };   // where the light sits
  const target = { x: 0.5, y: 0.55 };  // where the pointer actually is
  let raf = 0;
  let running = false;
  let visible = true;
  let start = performance.now();

  function resize() {
    // Clamp DPR: a 3x retina display gains nothing visible here and costs
    // ~2.25x the fragment work.
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.floor(canvas.clientWidth * dpr));
    const h = Math.max(1, Math.floor(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  function draw(now) {
    const t = (now - start) / 1000;
    // Ease the light toward the pointer so fast flicks do not snap.
    mouse.x += (target.x - mouse.x) * 0.06;
    mouse.y += (target.y - mouse.y) * 0.06;

    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, t);
    gl.uniform2f(uMouse, mouse.x, mouse.y);
    gl.uniform1f(uIntensity, 1.0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function frame(now) {
    if (!running) return;
    resize();
    draw(now);
    raf = requestAnimationFrame(frame);
  }

  function play() {
    if (running || reduced || !visible) return;
    running = true;
    // Rebase the clock so time does not jump after a pause.
    start = performance.now() - (start ? performance.now() - start : 0);
    raf = requestAnimationFrame(frame);
  }

  function pause() {
    running = false;
    cancelAnimationFrame(raf);
  }

  function onPointer(e) {
    const rect = canvas.getBoundingClientRect();
    target.x = (e.clientX - rect.left) / rect.width;
    target.y = 1 - (e.clientY - rect.top) / rect.height; // GL origin is bottom-left
  }

  function onVisibility() {
    if (document.hidden) pause();
    else play();
  }

  // Stop entirely once the hero is scrolled away — there is no reason to keep
  // a fragment shader running behind three screens of text.
  const io = new IntersectionObserver(
    ([entry]) => {
      visible = entry.isIntersecting;
      if (visible) play();
      else pause();
    },
    { threshold: 0 }
  );
  io.observe(canvas);

  window.addEventListener('pointermove', onPointer, { passive: true });
  window.addEventListener('resize', resize, { passive: true });
  document.addEventListener('visibilitychange', onVisibility);

  resize();
  if (reduced) {
    // One static frame: the composition still reads, nothing moves.
    draw(performance.now());
  } else {
    play();
  }

  return {
    supported: true,
    destroy() {
      pause();
      io.disconnect();
      window.removeEventListener('pointermove', onPointer);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
    },
  };
}
