// =============================================================================
//  ROMPECABEZAS POR GESTOS - versión WEB (navegador)
//  Cámara + gestos con MediaPipe Tasks for Web; rompecabezas dibujado en canvas.
//  Todo corre en el navegador del visitante (ideal para desplegar en Vercel).
// =============================================================================
import {
  HandLandmarker,
  FilesetResolver,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

// ---------- Referencias al DOM ----------
const $ = (id) => document.getElementById(id);
const canvas = $("view");
const ctx = canvas.getContext("2d");
const video = $("cam");

const startScreen = $("startScreen");
const startMsg = $("startMsg");
const hud = $("hud");
const actions = $("actions");
const difBtns = $("difBtns");
const btnCapturar = $("btnCapturar");

// ---------- Configuración ----------
const DIFICULTADES = { 1: ["FACIL", 3], 2: ["MEDIO", 4], 3: ["DIFICIL", 5] };
const SEG_CONFIRM = 1.0;     // segundos para confirmar la dificultad
const CUENTA_TOTAL = 3.0;    // segundos de cuenta regresiva

// ---------- Estado global ----------
let state = "START";
let handLandmarker = null;
let smoother = new Smoother(7);
let puzzle = null;
let photoCanvas = document.createElement("canvas");

let tCuenta = 0;             // inicio de la cuenta regresiva
let opcion = null;           // dificultad sostenida en el menú
let tConfirm = 0;
let lastVideoTime = -1;
let dedosVivos = null;       // último conteo (para el badge)

// =============================================================================
//  ARRANQUE
// =============================================================================
$("btnIniciar").addEventListener("click", iniciar);

async function iniciar() {
  $("btnIniciar").disabled = true;
  startMsg.textContent = "Pidiendo acceso a la cámara…";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
  } catch (e) {
    startMsg.textContent = "⚠️ No se pudo acceder a la cámara. Revisa los permisos.";
    $("btnIniciar").disabled = false;
    return;
  }

  startMsg.textContent = "Cargando modelo de manos…";
  try {
    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
    );
    handLandmarker = await crearDetector(vision, "GPU").catch(() =>
      crearDetector(vision, "CPU")
    );
  } catch (e) {
    startMsg.textContent = "⚠️ No se pudo cargar el modelo. Revisa tu conexión.";
    $("btnIniciar").disabled = false;
    return;
  }

  startScreen.classList.add("hidden");
  cambiarEstado("DETECCION");
  requestAnimationFrame(loop);
}

function crearDetector(vision, delegate) {
  return HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
      delegate,
    },
    runningMode: "VIDEO",
    numHands: 1,
  });
}

// =============================================================================
//  DETECCIÓN DE DEDOS
// =============================================================================
class Smoother {
  constructor(n = 7) { this.n = n; this.h = []; }
  push(v) { this.h.push(v); if (this.h.length > this.n) this.h.shift(); }
  stable() {
    if (this.h.length < this.n) return null;
    const f = this.h[0];
    return this.h.every((x) => x === f) ? f : null;
  }
  clear() { this.h = []; }
}

function contarDedos(lm) {
  // lm: 21 landmarks {x,y,z} normalizados (0..1)
  let dedos = 0;
  const tips = [8, 12, 16, 20];
  const pips = [6, 10, 14, 18];
  for (let i = 0; i < 4; i++) {
    if (lm[tips[i]].y < lm[pips[i]].y) dedos++;   // dedo extendido (punta arriba)
  }
  // Pulgar: extendido si la punta (4) está más lejos del nudillo del meñique
  // (17) que la articulación (3). Es robusto al giro/espejo de la mano.
  const d = (a, b) => Math.hypot(lm[a].x - lm[b].x, lm[a].y - lm[b].y);
  if (d(4, 17) > d(3, 17)) dedos++;
  return dedos;
}

// =============================================================================
//  BUCLE PRINCIPAL
// =============================================================================
function loop(now) {
  requestAnimationFrame(loop);
  const { w, h } = ajustarCanvas();

  // Detección de manos (solo si el video avanzó)
  let stable = null;
  if (handLandmarker && video.readyState >= 2 && video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    const res = handLandmarker.detectForVideo(video, now);
    if (res.landmarks && res.landmarks.length) {
      dedosVivos = contarDedos(res.landmarks[0]);
    } else {
      dedosVivos = null;
    }
    smoother.push(dedosVivos == null ? -1 : dedosVivos);
  }
  stable = smoother.stable();

  // Fondo
  ctx.fillStyle = "#15151a";
  ctx.fillRect(0, 0, w, h);

  switch (state) {
    case "DETECCION": estadoDeteccion(w, h, stable); break;
    case "CUENTA": estadoCuenta(w, h); break;
    case "MENU": estadoMenu(w, h, stable); break;
    case "JUEGO": estadoJuego(w, h); break;
  }
}

// ---------- Estados ----------
function estadoDeteccion(w, h, stable) {
  dibujarVideo(w, h, true);
  textoCentrado("Muestra la MANO ABIERTA ✋", w / 2, 46, 26, "#39e639", true);
  badgeDedos(w, h);
  if (stable === 5) iniciarCuenta();
}

function estadoCuenta(w, h) {
  dibujarVideo(w, h, true);
  const restante = CUENTA_TOTAL - (performance.now() - tCuenta) / 1000;
  if (restante > 0) {
    const numero = Math.ceil(restante);
    textoCentrado("¡Prepárate!", w / 2, 46, 26, "#39e639", true);
    textoCentrado(String(numero), w / 2, h / 2 + 40, Math.min(w, h) * 0.4, "#ffc800", false);
  } else {
    capturarFoto();
    cambiarEstado("MENU");
    opcion = null;
  }
}

function estadoMenu(w, h, stable) {
  dibujarImagen(photoCanvas, w, h);
  // panel superior
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ctx.fillRect(0, 0, w, Math.min(170, h * 0.32));
  textoCentrado("ELIGE LA DIFICULTAD", w / 2, 40, 26, "#00e6e6", false);
  textoCentrado("1 dedo = Fácil 3×3   ·   2 = Medio 4×4   ·   3 = Difícil 5×5",
    w / 2, 78, 16, "#ffffff", false);
  badgeDedos(w, h);

  if (stable in DIFICULTADES) {
    if (stable !== opcion) { opcion = stable; tConfirm = performance.now(); }
    const [nombre] = DIFICULTADES[opcion];
    const frac = Math.min(1, (performance.now() - tConfirm) / 1000 / SEG_CONFIRM);
    textoCentrado(`Seleccionando: ${nombre}`, w / 2, h - 70, 22, "#39e639", true);
    barraInferior(w, h, frac);
    if (frac >= 1) {
      const [nom, n] = DIFICULTADES[opcion];
      iniciarPuzzle(n, nom);
    }
  } else {
    opcion = null;
    textoCentrado("Muestra 1, 2 o 3 dedos…", w / 2, h - 70, 20, "#c8c8c8", true);
  }
}

function estadoJuego(w, h) {
  if (!puzzle) return;
  puzzle.render(ctx, w, h);
  actualizarHud();
}

// =============================================================================
//  TRANSICIONES
// =============================================================================
function cambiarEstado(nuevo) {
  state = nuevo;
  smoother.clear();
  hud.classList.toggle("hidden", nuevo !== "JUEGO");
  // botones flotantes contextuales
  const mostrarAcc = nuevo === "DETECCION" || nuevo === "MENU";
  actions.classList.toggle("hidden", !mostrarAcc);
  btnCapturar.classList.toggle("hidden", nuevo !== "DETECCION");
  difBtns.classList.toggle("hidden", nuevo !== "MENU");
}

function iniciarCuenta() { tCuenta = performance.now(); cambiarEstado("CUENTA"); }

function capturarFoto() {
  const vw = video.videoWidth, vh = video.videoHeight;
  photoCanvas.width = vw; photoCanvas.height = vh;
  const p = photoCanvas.getContext("2d");
  p.save();
  p.translate(vw, 0); p.scale(-1, 1);     // espejo (selfie)
  p.drawImage(video, 0, 0, vw, vh);
  p.restore();
}

function iniciarPuzzle(n, nombre) {
  puzzle = new Puzzle(photoCanvas, n, nombre);
  cambiarEstado("JUEGO");
}

function nuevaFoto() { puzzle = null; cambiarEstado("DETECCION"); }

// =============================================================================
//  EL ROMPECABEZAS
// =============================================================================
class Puzzle {
  constructor(photo, n, nombre) {
    this.photo = photo; this.n = n; this.nombre = nombre;
    this.orden = Array.from({ length: n * n }, (_, i) => i);
    this._generarBordes();
    this._shuffle();
    this.seleccionada = null;
    this.resuelto = false;
    this.movimientos = 0;
    this.pistas = 0;
    this.tInicio = null;
    this.tFin = null;
    this.preview = false;
    this.pista = null;       // [origen, destino]
    this.pistaHasta = 0;
    this.layout = null;
  }

  _generarBordes() {
    const n = this.n, N = n * n;
    this.top = new Array(N).fill(0);
    this.bottom = new Array(N).fill(0);
    this.left = new Array(N).fill(0);
    this.right = new Array(N).fill(0);
    const rnd = () => (Math.random() < 0.5 ? 1 : -1);
    for (let i = 0; i < n; i++)
      for (let j = 0; j < n - 1; j++) {
        const s = rnd(), a = i * n + j, b = i * n + (j + 1);
        this.right[a] = s; this.left[b] = -s;
      }
    for (let i = 0; i < n - 1; i++)
      for (let j = 0; j < n; j++) {
        const s = rnd(), a = i * n + j, b = (i + 1) * n + j;
        this.bottom[a] = s; this.top[b] = -s;
      }
  }

  _shuffle() {
    const N = this.n * this.n;
    do {
      for (let i = N - 1; i > 0; i--) {
        const k = Math.floor(Math.random() * (i + 1));
        [this.orden[i], this.orden[k]] = [this.orden[k], this.orden[i]];
      }
    } while (this.orden.every((v, i) => v === i));
  }

  edges(p) {
    return { top: this.top[p], right: this.right[p], bottom: this.bottom[p], left: this.left[p] };
  }

  progreso() {
    const N = this.n * this.n;
    let ok = 0;
    for (let c = 0; c < N; c++) if (this.orden[c] === c) ok++;
    return ok / N;
  }

  tiempo() {
    if (this.tInicio == null) return 0;
    const fin = this.tFin ?? performance.now();
    return (fin - this.tInicio) / 1000;
  }

  computeLayout(w, h) {
    const n = this.n;
    const pa = this.photo.width / this.photo.height;
    let bw = w * 0.98, bh = h * 0.98;
    if (bw / bh > pa) bw = bh * pa; else bh = bw / pa;
    const cw = bw / n, ch = bh / n;
    return {
      ox: (w - bw) / 2, oy: (h - bh) / 2, bw, bh, cw, ch, n,
      r: 0.2 * Math.min(cw, ch),
      u: Math.max(0.6, Math.min(1.6, bw / 1100)),
    };
  }

  hitCell(px, py) {
    const L = this.layout; if (!L) return null;
    const x = px - L.ox, y = py - L.oy;
    if (x < 0 || y < 0 || x >= L.bw || y >= L.bh) return null;
    const col = Math.floor(x / L.cw), row = Math.floor(y / L.ch);
    if (col < 0 || row < 0 || col >= L.n || row >= L.n) return null;
    return row * L.n + col;
  }

  clickCell(t) {
    if (this.resuelto) return;
    if (this.tInicio == null) this.tInicio = performance.now();
    if (this.seleccionada == null) this.seleccionada = t;
    else if (this.seleccionada === t) this.seleccionada = null;
    else {
      const a = this.seleccionada, b = t;
      [this.orden[a], this.orden[b]] = [this.orden[b], this.orden[a]];
      this.seleccionada = null;
      this.movimientos++;
      this._verificar();
    }
  }

  _verificar() {
    if (this.orden.every((v, i) => v === i)) {
      this.resuelto = true;
      this.seleccionada = null;
      if (this.tFin == null) this.tFin = performance.now();
    }
  }

  pedirPista() {
    if (this.resuelto) return;
    const N = this.n * this.n;
    const mal = [];
    for (let c = 0; c < N; c++) if (this.orden[c] !== c) mal.push(c);
    if (!mal.length) return;
    const destino = mal[Math.floor(Math.random() * mal.length)];
    const origen = this.orden.indexOf(destino);
    this.pista = [origen, destino];
    this.pistaHasta = performance.now() + 3000;
    this.pistas++;
    if (this.tInicio == null) this.tInicio = performance.now();
  }

  reiniciar() {
    this.resuelto = false; this.seleccionada = null;
    this.movimientos = 0; this.pistas = 0;
    this.tInicio = null; this.tFin = null; this.pista = null;
    this._shuffle();
  }

  render(ctx, w, h) {
    const L = this.computeLayout(w, h); this.layout = L;
    const { ox, oy, bw, bh, cw, ch, r, u, n } = L;
    ctx.save();
    ctx.translate(ox, oy);

    // Fondo ambiental (foto muy oscurecida)
    ctx.fillStyle = "#1c1c20"; ctx.fillRect(0, 0, bw, bh);
    ctx.globalAlpha = 0.16; ctx.drawImage(this.photo, 0, 0, bw, bh); ctx.globalAlpha = 1;

    // Piezas
    for (let t = 0; t < n * n; t++) {
      const p = this.orden[t];
      const tc = t % n, tr = Math.floor(t / n);
      const oc = p % n, orow = Math.floor(p / n);
      const X = tc * cw, Y = tr * ch;
      const dx = X - oc * cw, dy = Y - orow * ch;
      const e = this.edges(p);

      // Sombra (relieve)
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,0.5)";
      ctx.shadowBlur = 8 * u; ctx.shadowOffsetX = 4 * u; ctx.shadowOffsetY = 5 * u;
      piecePath(ctx, X, Y, cw, ch, e, r);
      ctx.fillStyle = "#000"; ctx.fill();
      ctx.restore();

      // Imagen recortada con la silueta de la pieza
      ctx.save();
      piecePath(ctx, X, Y, cw, ch, e, r);
      ctx.clip();
      ctx.drawImage(this.photo, dx, dy, bw, bh);
      ctx.restore();

      // Contorno (resaltado si está seleccionada)
      piecePath(ctx, X, Y, cw, ch, e, r);
      if (t === this.seleccionada) {
        ctx.lineWidth = Math.max(2, 3 * u); ctx.strokeStyle = "#00e6e6";
      } else {
        ctx.lineWidth = 1; ctx.strokeStyle = "rgba(15,15,15,0.85)";
      }
      ctx.stroke();
    }

    // Pista
    if (this.pista && performance.now() <= this.pistaHasta) {
      this._dibujarPista(ctx, L);
    } else { this.pista = null; }

    // Vista previa de referencia
    if (this.preview) this._dibujarMini(ctx, L);

    // Victoria
    if (this.resuelto) this._dibujarVictoria(ctx, L);

    ctx.restore();
  }

  _dibujarPista(ctx, L) {
    const { cw, ch, n, u } = L;
    const [origen, destino] = this.pista;
    const rect = (c) => [(c % n) * cw, Math.floor(c / n) * ch];
    ctx.lineWidth = Math.max(2, 4 * u);
    let [ox, oy] = rect(origen);
    ctx.strokeStyle = "rgba(255,165,0,1)"; ctx.strokeRect(ox + 3, oy + 3, cw - 6, ch - 6);
    let [dx, dy] = rect(destino);
    ctx.strokeStyle = "rgba(0,220,0,1)"; ctx.strokeRect(dx + 3, dy + 3, cw - 6, ch - 6);
    flecha(ctx, [ox + cw / 2, oy + ch / 2], [dx + cw / 2, dy + ch / 2], "#fff", Math.max(2, 3 * u));
  }

  _dibujarMini(ctx, L) {
    const { bw, bh } = L;
    const mw = bw / 4, mh = bh / 4;
    const x = bw - mw - 10, y = bh - mh - 10;
    ctx.fillStyle = "#000"; ctx.fillRect(x - 3, y - 22, mw + 6, mh + 25);
    ctx.drawImage(this.photo, x, y, mw, mh);
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.strokeRect(x, y, mw, mh);
    ctx.fillStyle = "#fff"; ctx.font = "13px system-ui"; ctx.textAlign = "left";
    ctx.fillText("Referencia", x, y - 7);
  }

  _dibujarVictoria(ctx, L) {
    const { bw, bh, u } = L;
    for (let i = 0; i < 80; i++) {
      ctx.fillStyle = `hsl(${Math.random() * 360},90%,60%)`;
      ctx.beginPath();
      ctx.arc(Math.random() * bw, Math.random() * bh, 2 + Math.random() * 4, 0, 7);
      ctx.fill();
    }
    const lineas = [
      ["¡RESUELTO!", 40 * u, "#3cff58", "bold "],
      [`Tiempo: ${fmtTiempo(this.tiempo())}`, 22 * u, "#fff", ""],
      [`Movimientos: ${this.movimientos}    Pistas: ${this.pistas}`, 22 * u, "#fff", ""],
    ];
    ctx.textAlign = "center";
    let maxW = 0;
    for (const [t, s, , wgt] of lineas) {
      ctx.font = `${wgt}${s}px system-ui`;
      maxW = Math.max(maxW, ctx.measureText(t).width);
    }
    const padX = 50 * u, padY = 28 * u, gap = 16 * u;
    const totalH = lineas.reduce((a, [, s]) => a + s, 0) + gap * (lineas.length - 1) + padY * 2;
    const pw = maxW + padX * 2, ph = totalH;
    const cx = bw / 2, cy = bh / 2;
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(cx - pw / 2, cy - ph / 2, pw, ph);
    ctx.strokeStyle = "#3cff58"; ctx.lineWidth = Math.max(2, 3 * u);
    ctx.strokeRect(cx - pw / 2, cy - ph / 2, pw, ph);
    let y = cy - ph / 2 + padY;
    for (const [t, s, col, wgt] of lineas) {
      ctx.font = `${wgt}${s}px system-ui`;
      ctx.fillStyle = col;
      y += s;
      ctx.fillText(t, cx, y);
      y += gap;
    }
    ctx.textAlign = "left";
  }
}

// ---------- Silueta de una pieza (rectángulo + pestañas/huecos como arcos) ----------
function piecePath(ctx, X, Y, W, H, e, r) {
  const midX = X + W / 2, midY = Y + H / 2, X2 = X + W, Y2 = Y + H;
  ctx.beginPath();
  ctx.moveTo(X, Y);
  // Arriba (izq -> der)
  if (e.top === 0) ctx.lineTo(X2, Y);
  else { ctx.lineTo(midX - r, Y); ctx.arc(midX, Y, r, Math.PI, 0, e.top === -1); ctx.lineTo(X2, Y); }
  // Derecha (arriba -> abajo)
  if (e.right === 0) ctx.lineTo(X2, Y2);
  else { ctx.lineTo(X2, midY - r); ctx.arc(X2, midY, r, -Math.PI / 2, Math.PI / 2, e.right === -1); ctx.lineTo(X2, Y2); }
  // Abajo (der -> izq)
  if (e.bottom === 0) ctx.lineTo(X, Y2);
  else { ctx.lineTo(midX + r, Y2); ctx.arc(midX, Y2, r, 0, Math.PI, e.bottom === -1); ctx.lineTo(X, Y2); }
  // Izquierda (abajo -> arriba)
  if (e.left === 0) ctx.lineTo(X, Y);
  else { ctx.lineTo(X, midY + r); ctx.arc(X, midY, r, Math.PI / 2, 3 * Math.PI / 2, e.left === -1); ctx.lineTo(X, Y); }
  ctx.closePath();
}

// =============================================================================
//  UTILIDADES DE DIBUJO
// =============================================================================
function ajustarCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const cw = Math.round(w * dpr), ch = Math.round(h * dpr);
  if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w, h };
}

function dibujarVideo(w, h, mirror) { dibujarFuente(video, w, h, mirror); }
function dibujarImagen(img, w, h) { dibujarFuente(img, w, h, false); }

function dibujarFuente(src, w, h, mirror) {
  const sw = src.videoWidth || src.width, sh = src.videoHeight || src.height;
  if (!sw || !sh) return;
  const pa = sw / sh;
  let dw = w, dh = w / pa;
  if (dh > h) { dh = h; dw = h * pa; }
  const ox = (w - dw) / 2, oy = (h - dh) / 2;
  ctx.save();
  if (mirror) { ctx.translate(ox + dw, oy); ctx.scale(-1, 1); ctx.drawImage(src, 0, 0, dw, dh); }
  else ctx.drawImage(src, ox, oy, dw, dh);
  ctx.restore();
}

function textoCentrado(txt, cx, y, size, color, bg) {
  ctx.font = `bold ${size}px system-ui`;
  ctx.textAlign = "center";
  if (bg) {
    const tw = ctx.measureText(txt).width;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(cx - tw / 2 - 12, y - size, tw + 24, size + 14);
  }
  ctx.fillStyle = color;
  ctx.fillText(txt, cx, y);
  ctx.textAlign = "left";
}

function badgeDedos(w, h) {
  const txt = dedosVivos == null ? "Sin mano" : `Dedos: ${dedosVivos}`;
  ctx.font = "16px system-ui"; ctx.textAlign = "left";
  const tw = ctx.measureText(txt).width;
  ctx.fillStyle = "rgba(0,0,0,0.5)";
  ctx.fillRect(12, h - 40, tw + 20, 28);
  ctx.fillStyle = "#fff";
  ctx.fillText(txt, 22, h - 21);
}

function barraInferior(w, h, frac) {
  const m = 60, y = h - 36;
  ctx.fillStyle = "#505050"; ctx.fillRect(m, y, w - 2 * m, 16);
  ctx.fillStyle = "#00c8ff"; ctx.fillRect(m, y, (w - 2 * m) * frac, 16);
}

function flecha(ctx, a, b, color, lw) {
  const [x1, y1] = a, [x2, y2] = b;
  const ang = Math.atan2(y2 - y1, x2 - x1), head = 14 + lw * 2;
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = lw;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - head * Math.cos(ang - 0.4), y2 - head * Math.sin(ang - 0.4));
  ctx.lineTo(x2 - head * Math.cos(ang + 0.4), y2 - head * Math.sin(ang + 0.4));
  ctx.closePath(); ctx.fill();
}

function fmtTiempo(s) {
  s = Math.max(0, Math.floor(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// =============================================================================
//  HUD (barra superior HTML)
// =============================================================================
function actualizarHud() {
  if (!puzzle) return;
  $("hudDif").textContent = `${puzzle.nombre} ${puzzle.n}×${puzzle.n}`;
  $("hudMov").textContent = puzzle.movimientos;
  $("hudTime").textContent = fmtTiempo(puzzle.tiempo());
  $("hudPistas").textContent = puzzle.pistas;
  const pct = Math.round(puzzle.progreso() * 100);
  $("hudBar").style.width = pct + "%";
  $("hudBar").style.background = pct >= 100 ? "#3cb44b" : "#00e6e6";
  $("hudPct").textContent = pct + "%";
}

// =============================================================================
//  EVENTOS DE INTERFAZ
// =============================================================================
canvas.addEventListener("pointerdown", (e) => {
  if (state !== "JUEGO" || !puzzle) return;
  const rect = canvas.getBoundingClientRect();
  const t = puzzle.hitCell(e.clientX - rect.left, e.clientY - rect.top);
  if (t != null) puzzle.clickCell(t);
});

btnCapturar.addEventListener("click", () => { if (state === "DETECCION") iniciarCuenta(); });

difBtns.querySelectorAll(".btn-dif").forEach((b) =>
  b.addEventListener("click", () => {
    if (state !== "MENU") return;
    const n = parseInt(b.dataset.n, 10);
    const nombre = { 3: "FACIL", 4: "MEDIO", 5: "DIFICIL" }[n];
    iniciarPuzzle(n, nombre);
  })
);

$("btnPista").addEventListener("click", () => puzzle && puzzle.pedirPista());
$("btnVista").addEventListener("click", (e) => {
  if (!puzzle) return;
  puzzle.preview = !puzzle.preview;
  e.currentTarget.classList.toggle("active", puzzle.preview);
});
$("btnReiniciar").addEventListener("click", () => puzzle && puzzle.reiniciar());
$("btnNuevaFoto").addEventListener("click", nuevaFoto);

window.addEventListener("keydown", (e) => {
  if (state !== "JUEGO" || !puzzle) return;
  const k = e.key.toLowerCase();
  if (k === "h") puzzle.pedirPista();
  else if (k === "p") { puzzle.preview = !puzzle.preview; $("btnVista").classList.toggle("active", puzzle.preview); }
  else if (k === "r") puzzle.reiniciar();
});
