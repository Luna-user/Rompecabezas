# Rompecabezas por Gestos — versión Web

Versión para navegador del juego: la cámara y la detección de la mano corren en
el dispositivo del visitante (no en un servidor), así que se puede desplegar
como **sitio estático** en Vercel y abrirlo desde cualquier celular o laptop.

- **Cámara:** `getUserMedia` (navegador).
- **Gestos:** MediaPipe Tasks for Web (Hand Landmarker, vía CDN).
- **Rompecabezas:** dibujado en `<canvas>` con piezas reales (pestañas/huecos),
  HUD, contador de movimientos, % de progreso, pista, vista previa y responsive.

> Requiere **HTTPS** (Vercel lo da automáticamente). En local también funciona
> con `http://localhost` (ver más abajo).

## Archivos

```
web/
├── index.html     # estructura + HUD + botones
├── style.css      # estilos responsive (tema oscuro)
├── app.js         # gestos (MediaPipe), estados y motor del rompecabezas
├── vercel.json    # cleanUrls + permiso de cámara
└── README.md      # este archivo
```

## Desplegar en Vercel (desde GitHub)

1. Entra a https://vercel.com y haz **Add New… → Project**.
2. Importa el repositorio `Luna-user/Rompecabezas`.
3. En la configuración del proyecto:
   - **Framework Preset:** `Other`
   - **Root Directory:** `web`  ← importante (el código web está en esta carpeta)
   - Build Command / Output: deja en blanco (es estático).
4. **Deploy.** Al terminar tendrás una URL pública (HTTPS) lista para un QR.

### Alternativa: Vercel CLI

```bash
npm i -g vercel
cd web
vercel        # sigue las preguntas; deja Root Directory en "."
```

## Probar en local

Como usa cámara y módulos ES, ábrelo con un servidor local (no con `file://`):

```bash
cd web
python -m http.server 8000
# luego abre http://localhost:8000
```

## Notas

- La primera carga descarga el modelo de manos (~varios MB) desde el CDN de
  MediaPipe; con buena conexión tarda 1–3 s.
- Si los gestos cuestan por la luz o la cámara, hay botones de respaldo
  (**Tomar foto** y los de dificultad), así el stand nunca se queda trabado.
- Controles dentro del juego: tocar dos piezas para intercambiarlas; botones
  **Pista / Vista / Reiniciar / Nueva foto**; teclas **H / P / R**.
