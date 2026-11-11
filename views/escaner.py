"""Escáner QR en vivo con selector de cámara (MediaDevices API), para PC y celulares.

Reemplaza a `st.camera_input`, que solo saca fotos y usa la cámara por defecto del navegador (en PC con
varias webcams, o con la webcam ocupada por otra app, fallaba sin explicación). Este componente:
  * lista las cámaras con `enumerateDevices()` y deja elegir; recuerda la elección en el navegador;
  * prefiere la cámara trasera en celulares (`facingMode: environment`);
  * decodifica en vivo, sin sacar fotos: `BarcodeDetector` nativo si existe (Chrome Android/macOS, Safari)
    o jsQR como alternativa universal (Chrome/Edge en Windows no traen BarcodeDetector);
  * explica en español cada error (permiso denegado, cámara en uso, sin cámara, sitio sin https);
  * evita lecturas repetidas: el mismo código no se vuelve a enviar durante unos segundos.

Usa `st.components.v2` (Streamlit ≥ 1.50): el JavaScript corre en la página y devuelve el texto leído a
Python con `setTriggerValue`, que provoca una única recarga con el valor.
"""
from __future__ import annotations

import streamlit as st

_HTML = """
<div class="sia-esc">
  <div class="barra">
    <select class="camara" aria-label="Elegir cámara"></select>
    <button type="button" class="alternar">⏸ Pausar</button>
  </div>
  <div class="visor">
    <video playsinline muted></video>
    <div class="mira"></div>
  </div>
  <div class="estado" role="status">Preparando cámara…</div>
  <button type="button" class="reintentar" hidden>🔄 Reintentar</button>
</div>
"""

_CSS = """
.sia-esc { font-family: 'Plus Jakarta Sans', Inter, system-ui, sans-serif; max-width: 100%; }
.barra { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: .5rem; }
.camara { flex: 1 1 180px; min-width: 0; max-width: 100%; padding: .45rem .6rem; border-radius: 12px;
  border: 1px solid #7979B1; background: #fff; color: #0E2747; font: inherit; font-size: .9rem; }
button { border-radius: 12px; border: 1px solid #346FB0; background: #346FB0; color: #fff; padding: .45rem .9rem;
  font: inherit; font-size: .9rem; font-weight: 700; cursor: pointer; }
button:hover { background: #7979B1; border-color: #7979B1; }
.visor { position: relative; width: 100%; aspect-ratio: 4 / 3; background: #003467; border-radius: 16px;
  overflow: hidden; }
video { width: 100%; height: 100%; object-fit: cover; display: block; }
.mira { position: absolute; inset: 18%; border: 3px solid rgba(183,143,182,.95); border-radius: 18px;
  box-shadow: 0 0 0 9999px rgba(0,20,45,.28); transition: border-color .15s ease; pointer-events: none; }
.sia-esc.leido .mira { border-color: #2E9E77; }
.estado { margin-top: .5rem; font-size: .9rem; color: #0E2747; background: #F3ECF4; border-left: 5px solid #B78FB6;
  border-radius: 10px; padding: .5rem .7rem; overflow-wrap: anywhere; }
.estado.error { background: #FDECEC; border-left-color: #D9534F; }
.reintentar { margin-top: .5rem; }
"""

_JS = """
export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const raiz = parentElement.querySelector('.sia-esc');
  const select = raiz.querySelector('.camara');
  const video = raiz.querySelector('video');
  const estadoEl = raiz.querySelector('.estado');
  const btnAlternar = raiz.querySelector('.alternar');
  const btnReintentar = raiz.querySelector('.reintentar');
  const opciones = data || {};
  const CLAVE = 'sia_camara_' + (opciones.perfil || 'general');
  const ESPERA = opciones.espera_ms || 4000;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  let stream = null, timer = null, detector = null, pausado = false, ultimo = '', ultimoTs = 0, contador = 0, vivo = true;

  const estado = (texto, error) => { estadoEl.textContent = texto; estadoEl.classList.toggle('error', !!error); btnReintentar.hidden = !error; };

  async function cargarJsQR() {
    if (window.jsQR) return;
    await new Promise((ok, falla) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
      s.onload = ok; s.onerror = falla; document.head.appendChild(s);
    });
  }
  async function prepararDecodificador() {
    if ('BarcodeDetector' in window) {
      try {
        const formatos = await window.BarcodeDetector.getSupportedFormats();
        if (formatos.includes('qr_code')) { detector = new window.BarcodeDetector({ formats: ['qr_code'] }); return; }
      } catch (e) { /* sigue con jsQR */ }
    }
    await cargarJsQR();
  }
  function detener() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  }
  async function listarCamaras(actual) {
    const camaras = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
    select.innerHTML = '';
    camaras.forEach((c, i) => {
      const o = document.createElement('option');
      o.value = c.deviceId; o.textContent = c.label || ('Cámara ' + (i + 1));
      select.appendChild(o);
    });
    if (actual) select.value = actual;
    select.hidden = camaras.length < 2;
  }
  function mensajeError(e) {
    const tipo = e && e.name;
    const textos = {
      NotAllowedError: 'Permiso de cámara denegado. Habilitalo en el candado de la barra de direcciones y tocá Reintentar.',
      SecurityError: 'El navegador bloqueó la cámara: la app tiene que abrirse con https.',
      NotFoundError: 'No se encontró ninguna cámara conectada.',
      NotReadableError: 'La cámara está siendo usada por otra aplicación (Zoom, Meet, otra pestaña). Cerrala y tocá Reintentar.',
      OverconstrainedError: 'La cámara elegida ya no está disponible. Elegí otra de la lista.',
      AbortError: 'La cámara no respondió. Tocá Reintentar.',
    };
    return textos[tipo] || ('No se pudo abrir la cámara (' + (tipo || 'error desconocido') + ').');
  }
  async function abrir(deviceId) {
    const base = { width: { ideal: 1280 }, height: { ideal: 720 } };
    if (deviceId) {
      try { return await navigator.mediaDevices.getUserMedia({ video: { ...base, deviceId: { exact: deviceId } }, audio: false }); }
      catch (e) { if (e.name !== 'OverconstrainedError' && e.name !== 'NotFoundError') throw e; }
    }
    try { return await navigator.mediaDevices.getUserMedia({ video: { ...base, facingMode: { ideal: opciones.preferir || 'environment' } }, audio: false }); }
    catch (e) {
      if (e.name === 'NotAllowedError' || e.name === 'SecurityError') throw e;
      return await navigator.mediaDevices.getUserMedia({ video: true, audio: false });  // cualquier cámara
    }
  }
  async function iniciar(deviceId) {
    detener();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      estado('Este navegador no permite usar la cámara. Usá el PIN o el ingreso manual.', true); return;
    }
    estado('Iniciando cámara…');
    try {
      let guardada = null; try { guardada = localStorage.getItem(CLAVE); } catch (e) {}
      stream = await abrir(deviceId || guardada);
      if (!vivo) { detener(); return; }
      video.srcObject = stream;
      await video.play().catch(() => {});
      const actual = stream.getVideoTracks()[0].getSettings().deviceId;
      try { if (actual) localStorage.setItem(CLAVE, actual); } catch (e) {}
      await listarCamaras(actual);
      await prepararDecodificador();
      pausado = false; btnAlternar.textContent = '⏸ Pausar';
      estado(detector ? 'Apuntá la cámara al código QR.' : 'Apuntá la cámara al código QR (lector compatible).');
      bucle();
    } catch (e) {
      detener();
      estado(mensajeError(e), true);
    }
  }
  function decodificarFrame() {
    if (detector) return detector.detect(video).then(r => (r[0] && r[0].rawValue) || null);
    const escala = Math.min(1, 720 / Math.max(video.videoWidth, 1));
    canvas.width = Math.floor(video.videoWidth * escala); canvas.height = Math.floor(video.videoHeight * escala);
    if (!canvas.width || !canvas.height) return Promise.resolve(null);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const codigo = window.jsQR(img.data, img.width, img.height, { inversionAttempts: 'attemptBoth' });
    return Promise.resolve(codigo ? codigo.data : null);
  }
  async function bucle() {
    if (!stream || pausado || !vivo) return;
    if (video.readyState >= 2) {
      try {
        const texto = await decodificarFrame();
        if (texto) leido(texto);
      } catch (e) { /* frame inválido: se reintenta */ }
    }
    timer = setTimeout(bucle, 150);
  }
  function leido(texto) {
    const ahora = Date.now();
    if (texto === ultimo && ahora - ultimoTs < ESPERA) return;  // misma credencial: no repetir
    ultimo = texto; ultimoTs = ahora; contador += 1;
    raiz.classList.add('leido'); setTimeout(() => raiz.classList.remove('leido'), 600);
    if (navigator.vibrate) navigator.vibrate(60);
    estado('✅ Código leído. Procesando…');
    setTriggerValue('codigo', { texto: texto, n: contador, ts: ahora });
  }

  select.addEventListener('change', () => iniciar(select.value));
  btnReintentar.addEventListener('click', () => iniciar(select.value || null));
  btnAlternar.addEventListener('click', () => {
    if (pausado || !stream) { iniciar(select.value || null); }
    else { pausado = true; detener(); btnAlternar.textContent = '▶ Reanudar'; estado('Cámara en pausa.'); }
  });
  iniciar(null);
  return () => { vivo = false; detener(); };
}
"""

_componente = st.components.v2.component("sia_escaner_qr", html=_HTML, css=_CSS, js=_JS)


def _sin_accion() -> None:
    """El valor leído se procesa en la recarga que dispara el componente."""


def escaner_qr(clave: str, perfil: str = "general", preferir: str = "environment") -> str | None:
    """Muestra el escáner y devuelve el texto de un QR recién leído (una sola vez por lectura)."""
    resultado = _componente(
        key=f"escaner_{clave}",
        data={"perfil": perfil, "preferir": preferir, "espera_ms": 8000},
        on_codigo_change=_sin_accion,
    )
    valor = getattr(resultado, "codigo", None)
    if not isinstance(valor, dict) or not valor.get("texto"):
        return None
    marca = (valor.get("texto"), valor.get("ts"))
    if st.session_state.get(f"_escaner_ultimo_{clave}") == marca:
        return None
    st.session_state[f"_escaner_ultimo_{clave}"] = marca
    return str(valor["texto"])
