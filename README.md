# Rompecabezas Fotografico Activado por Gestos

Juego de Vision Artificial que usa la webcam para tomar una foto activada por
gestos y convertirla en un rompecabezas. Construido con OpenCV, MediaPipe Hands
y NumPy.

> **Tambien hay una version WEB** (navegador) en la carpeta [`web/`](web/),
> lista para desplegar como sitio estatico en Vercel. La camara y los gestos
> corren en el navegador del visitante (MediaPipe Tasks for Web + canvas), ideal
> para abrir desde el celular escaneando un QR. Ver [`web/README.md`](web/README.md).

## Flujo del juego

1. Deteccion: muestra la MANO ABIERTA (5 dedos) frente a la camara.
2. Cuenta regresiva: aparece 3, 2, 1. Al llegar a 0 se congela y captura la foto.
3. Rompecabezas FACIL automatico: al capturar la foto se arma DIRECTAMENTE un
   rompecabezas de 3x3 (9 piezas). Ya no hay menu de dificultad.
4. La foto se corta en piezas con forma REAL de rompecabezas (pestanas y huecos
   que encajan entre piezas vecinas), se desordenan y se abre una ventana nueva
   para resolverlo. La ventana incluye una barra superior con: nivel, contador
   de movimientos, cronometro, pistas usadas (max 3), barra de progreso (% de
   piezas en su lugar) y botones cliqueables.

La interfaz es RESPONSIVE: detecta el tamano de la pantalla y reescala la foto
y la ventana del rompecabezas para que siempre quepan, ajustando de forma
proporcional las fuentes, los botones y los margenes del HUD. La ventana de la
camara tambien se puede redimensionar.

## Controles (ventana del rompecabezas)

| Accion                   | Tecla / Boton / Gesto     |
|--------------------------|---------------------------|
| Tomar foto (nivel 3x3)   | Mano abierta (5 dedos)    |
| Seleccionar/Intercambiar | Clic en dos piezas        |
| Pista (max 3)            | Boton PISTA  o tecla H    |
| Vista previa (1 solo uso)| Boton VISTA  o tecla P    |
| Reiniciar la partida     | Boton REINICIAR o tecla R |
| Salir                    | ESC o Q                   |

La PISTA resalta en naranja la pieza a mover y en verde su lugar correcto, con
una flecha entre ambas. Esta LIMITADA a 3 usos (el boton muestra cuantas
quedan). La VISTA muestra una miniatura de la foto original como referencia y es
de UN SOLO uso (una vez que la ocultas, ya no se puede volver a mostrar). Al
Reiniciar la partida, las ayudas se restablecen.

## Como ejecutar

El entorno virtual (.venv) con Python 3.12 y las dependencias YA estan
instalados. Tienes dos formas de ejecutarlo:

### Opcion 1 (mas simple): doble clic en run.bat

Solo haz doble clic en `run.bat`. Usa el Python del entorno virtual
directamente, sin necesidad de activar nada.

### Opcion 2: desde PowerShell

```powershell
cd "C:\Users\Usuario\Desktop\7mo semestre\FeriaING"
.\.venv\Scripts\python.exe rompecabezas_gestos.py
```

O activando el entorno (la politica de ejecucion ya quedo configurada):

```powershell
.\.venv\Scripts\Activate.ps1
python rompecabezas_gestos.py
```

## Notas importantes

- Mensajes de arranque normales: al iniciar veras 2-3 lineas como
  `INFO: Created TensorFlow Lite XNNPACK delegate...` y
  `W0000 ... inference_feedback_manager.cc`. NO son errores: son avisos
  internos de MediaPipe que aparecen una sola vez. Se pueden ignorar.

- Version de Python: el proyecto usa Python 3.12 (dentro de .venv) porque
  MediaPipe todavia no es compatible con Python 3.14. Tu Python 3.14 del
  sistema sigue intacto; el 3.12 solo se usa para este proyecto.

- Version de MediaPipe: se fija a 0.10.14 en requirements.txt. Las versiones
  recientes (0.10.35) eliminaron el API `mediapipe.solutions` que usa este
  juego, por eso se usa una version que si lo incluye.

## Reinstalar el entorno desde cero (si hiciera falta)

```powershell
cd "C:\Users\Usuario\Desktop\7mo semestre\FeriaING"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Detalles tecnicos

- BGR -> RGB: OpenCV entrega los fotogramas en BGR; MediaPipe requiere RGB.
  La conversion se hace en `DetectorManos.procesar()`, y el frame se marca como
  no editable (`writeable = False`) para acelerar el procesamiento.
- Conteo de dedos: se compara la punta de cada dedo con su articulacion
  intermedia (eje Y); el pulgar se evalua en el eje X segun la mano (corregida
  por el efecto espejo).
- Suavizado: un historial corto exige que varias lecturas coincidan antes de
  aceptar un gesto, eliminando parpadeos.
- Piezas tipo rompecabezas: se recorta la imagen a dimensiones divisibles por
  n y se arma una cuadricula n x n. Cada borde interior se sortea como pestana
  (+) o hueco (-) usando la MISMA circunferencia centrada en la linea del borde
  (una pieza la suma y la vecina la resta), de modo que siempre encajan. Cada
  pieza se guarda como un parche de imagen con su silueta (alfa) y se pega
  sobre el tablero respetando ese alfa.
- Calidad visual: las siluetas se generan a 3x y se reducen con INTER_AREA
  (anti-aliasing), cada pieza lleva una sombra difuminada (relieve) y el fondo
  es la foto muy oscurecida en vez de un gris plano.
- Responsive: `obtener_tamano_pantalla()` consulta la resolucion (ctypes en
  Windows, con respaldo en tkinter) y la clase `Rompecabezas` reescala la foto
  para caber, derivando un factor `u` que escala fuentes y botones del HUD.

## Estructura

```
FeriaING/
├── .venv/                   # Entorno virtual con Python 3.12 (no se sube a git)
├── rompecabezas_gestos.py   # App de ESCRITORIO (OpenCV/MediaPipe/NumPy)
├── run.bat                  # Lanzador rapido (doble clic)
├── requirements.txt         # Dependencias de Python
├── web/                     # Version WEB (HTML/JS/canvas) desplegable en Vercel
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── vercel.json
│   └── README.md
├── .gitignore               # Ignora .venv y __pycache__
└── README.md                # Este archivo
```
