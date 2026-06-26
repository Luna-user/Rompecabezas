# -*- coding: utf-8 -*-
"""
=============================================================================
ROMPECABEZAS FOTOGRAFICO ACTIVADO POR GESTOS
=============================================================================
Juego de visión artificial que usa la webcam para:

1. Detectar la MANO ABIERTA (5 dedos) e iniciar una cuenta regresiva.
2. Mostrar el contador (3, 2, 1) y CONGELAR la foto al llegar a 0.
3. Armar DIRECTAMENTE un rompecabezas de nivel FÁCIL (3x3 = 9 piezas) con la
    foto capturada, con forma de ROMPECABEZAS REAL (pestañas y huecos que
    encajan entre piezas vecinas). Las piezas se desordenan y se abre una
    ventana donde se resuelve intercambiándolas con el mouse (clic en dos
    piezas). Ayudas limitadas: máx. 3 PISTAS y la VISTA previa es de un
    solo uso.

La interfaz es RESPONSIVE: la foto y la ventana del rompecabezas se escalan
automáticamente para caber en cualquier pantalla, y el HUD (barra superior con
estadísticas y botones) se ajusta de forma proporcional.

Tecnologías: OpenCV + MediaPipe Hands + NumPy
Autor: (Feria de Ingeniería)
=============================================================================
"""

import os

# Reduce algunos mensajes informativos de TensorFlow Lite / glog en la consola.
# NOTA: MediaPipe igualmente imprime 2-3 avisos de arranque (XNNPACK, absl,
# "inference_feedback_manager"). Son NORMALES, no son errores, y aparecen una
# sola vez al cargar el modelo. Se pueden ignorar con tranquilidad.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import time
import random
from collections import deque

import cv2
import numpy as np
import mediapipe as mp


# =============================================================================
#  CONFIGURACIÓN GLOBAL
# =============================================================================
class Config:
    """Parámetros ajustables del juego en un solo lugar."""
    INDICE_CAMARA = 0          # 0 = webcam por defecto
    ANCHO_CAMARA = 1280        # resolución de captura solicitada
    ALTO_CAMARA = 720

    SEG_POR_NUMERO = 1.0       # duración de cada número de la cuenta regresiva
    HISTORIAL_DEDOS = 7        # nº de lecturas para suavizar el conteo de dedos

    # Único nivel disponible: FÁCIL = rompecabezas de 3x3 (9 piezas).
    NOMBRE_NIVEL = "FACIL"
    TAMANO_NIVEL = 3           # cuadrícula 3x3

    # Límites de ayudas durante el juego
    MAX_PISTAS = 3             # como máximo 3 pistas
    VISTA_UN_SOLO_USO = True   # la vista previa solo se puede usar una vez


# =============================================================================
#  UTILIDADES DE PANTALLA (para que todo sea RESPONSIVE)
# =============================================================================
def obtener_tamano_pantalla():
    """
    Devuelve (ancho, alto) de la pantalla en píxeles reales.
    Intenta varios métodos y cae en un valor seguro si ninguno funciona.
    """
    # 1) Windows nativo (rápido y sin dependencias gráficas)
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass

    # 2) Tkinter (multiplataforma)
    try:
        import tkinter as tk
        raiz = tk.Tk()
        raiz.withdraw()
        w, h = raiz.winfo_screenwidth(), raiz.winfo_screenheight()
        raiz.destroy()
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass

    # 3) Valor por defecto razonable
    return 1280, 720


def preparar_ventana_pantalla_completa(nombre):
    """Crea/configura una ventana en PANTALLA COMPLETA (cubre todo el monitor)."""
    cv2.namedWindow(nombre, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(nombre, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def componer_pantalla(frame, sw, sh, fondo=(0, 0, 0)):
    """
    Centra y escala 'frame' dentro de un lienzo del tamaño EXACTO de la pantalla
    (sh x sw), conservando la proporción (rellena con 'fondo' las barras que
    sobren). Así cada vista llena toda la pantalla sin deformarse, en cualquier
    monitor.
    """
    h, w = frame.shape[:2]
    escala = min(sw / w, sh / h)
    nw, nh = max(1, int(w * escala)), max(1, int(h * escala))
    interp = cv2.INTER_AREA if escala < 1 else cv2.INTER_LINEAR
    redim = cv2.resize(frame, (nw, nh), interpolation=interp)
    lienzo = np.full((sh, sw, 3), fondo, np.uint8)
    x0, y0 = (sw - nw) // 2, (sh - nh) // 2
    lienzo[y0:y0 + nh, x0:x0 + nw] = redim
    return lienzo


# =============================================================================
#  MÓDULO 1: DETECCIÓN DE MANOS Y CONTEO DE DEDOS (MediaPipe)
# =============================================================================
class DetectorManos:
    """
    Envuelve MediaPipe Hands. Se encarga de:
    - Procesar cada fotograma (convirtiendo BGR -> RGB para MediaPipe).
    - Contar cuántos dedos están levantados.
    - Dibujar las marcas (landmarks) de la mano sobre el fotograma.
    """

    # IDs de las puntas de cada dedo según el modelo de MediaPipe
    PUNTAS = [4, 8, 12, 16, 20]  # pulgar, índice, medio, anular, meñique

    def __init__(self, max_manos=1, confianza_deteccion=0.7, confianza_seguimiento=0.5):
        self.mp_manos = mp.solutions.hands
        self.mp_dibujo = mp.solutions.drawing_utils
        self.mp_estilos = mp.solutions.drawing_styles
        self.manos = self.mp_manos.Hands(
            static_image_mode=False,
            max_num_hands=max_manos,
            min_detection_confidence=confianza_deteccion,
            min_tracking_confidence=confianza_seguimiento,
        )
        self.resultados = None

    def procesar(self, frame_bgr):
        """
        Procesa un fotograma BGR (el formato nativo de OpenCV).
        IMPORTANTE: MediaPipe trabaja en RGB, por eso convertimos el color.
        Se marca la imagen como no editable para acelerar el procesamiento.
        """
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False          # optimización de rendimiento
        self.resultados = self.manos.process(frame_rgb)
        return self.resultados

    def hay_mano(self):
        """Devuelve True si se detectó al menos una mano en el último frame."""
        return bool(self.resultados and self.resultados.multi_hand_landmarks)

    def dibujar(self, frame_bgr):
        """Dibuja el esqueleto de la mano detectada sobre el fotograma."""
        if not self.hay_mano():
            return frame_bgr
        for landmarks in self.resultados.multi_hand_landmarks:
            self.mp_dibujo.draw_landmarks(
                frame_bgr,
                landmarks,
                self.mp_manos.HAND_CONNECTIONS,
                self.mp_estilos.get_default_hand_landmarks_style(),
                self.mp_estilos.get_default_hand_connections_style(),
            )
        return frame_bgr

    def contar_dedos(self):
        """
        Cuenta los dedos levantados de la PRIMERA mano detectada.

        Lógica:
        - Dedos índice, medio, anular y meñique: están "arriba" si la punta
            tiene una coordenada Y menor (más arriba en la imagen) que su
            articulación intermedia (PIP).
        - Pulgar: se compara en el eje X. Como volteamos el frame en modo
            espejo, invertimos la etiqueta de mano que entrega MediaPipe para
            que coincida con la mano real del usuario.

        Devuelve la cantidad de dedos levantados (0 a 5), o None si no hay mano.
        """
        if not self.hay_mano():
            return None

        landmarks = self.resultados.multi_hand_landmarks[0].landmark
        etiqueta_mp = self.resultados.multi_handedness[0].classification[0].label
        # El frame se muestra en espejo -> invertimos la etiqueta detectada
        mano = "Left" if etiqueta_mp == "Right" else "Right"

        dedos_arriba = 0

        # --- Pulgar (eje X, depende de la mano) ---
        if mano == "Right":
            if landmarks[4].x < landmarks[3].x:
                dedos_arriba += 1
        else:  # Left
            if landmarks[4].x > landmarks[3].x:
                dedos_arriba += 1

        # --- Cuatro dedos restantes (eje Y) ---
        for punta in self.PUNTAS[1:]:
            # La punta (id) está arriba si su Y < Y de la articulación PIP (id-2)
            if landmarks[punta].y < landmarks[punta - 2].y:
                dedos_arriba += 1

        return dedos_arriba

    def cerrar(self):
        """Libera los recursos de MediaPipe."""
        self.manos.close()


# =============================================================================
#  MÓDULO 2: SUAVIZADO DE LECTURAS (evita parpadeos en el conteo)
# =============================================================================
class SuavizadorDedos:
    """
    Mantiene un historial corto de lecturas y devuelve un valor estable
    sólo cuando todas las lecturas recientes coinciden. Así se elimina el
    "ruido" típico de la detección cuadro a cuadro.
    """

    def __init__(self, tamano=Config.HISTORIAL_DEDOS):
        self.historial = deque(maxlen=tamano)

    def actualizar(self, valor):
        self.historial.append(valor)

    def valor_estable(self):
        """Devuelve el conteo si TODAS las lecturas del historial coinciden."""
        if len(self.historial) < self.historial.maxlen:
            return None
        primero = self.historial[0]
        if all(v == primero for v in self.historial):
            return primero
        return None

    def reiniciar(self):
        self.historial.clear()


# =============================================================================
#  MÓDULO 3: EL ROMPECABEZAS (piezas reales + juego con mouse, RESPONSIVE)
# =============================================================================
class Rompecabezas:
    """
    Convierte una imagen en un rompecabezas n x n con piezas de forma REAL:
    cada borde interior tiene una PESTAÑA (saliente) o un HUECO (entrante)
    complementario con su pieza vecina, igual que un rompecabezas físico.

    Características:
    - Bordes sorteados al azar pero complementarios entre vecinas (encajan).
    - Piezas con anti-aliasing y sombra (relieve).
    - HUD superior con dificultad, movimientos, cronómetro, pistas, barra de
      progreso (% de piezas en su lugar) y botones cliqueables.
    - Pista, vista previa de referencia y reinicio.
    - RESPONSIVE: la foto se reescala para caber en la pantalla y la interfaz
      (fuentes, botones, márgenes) se ajusta de forma proporcional.
    """

    def __init__(self, imagen, n, nombre_dificultad="", pantalla=None):
        self.n = n
        self.nombre = nombre_dificultad

        # ------------------------------------------------------------------
        # 1) PANTALLA COMPLETA + RESPONSIVE: el lienzo final es del tamaño
        #    EXACTO de la pantalla. La foto se reescala para ocupar el área
        #    bajo el HUD conservando su proporción, y se CENTRA (el resto se
        #    rellena de fondo oscuro). Así cubre cualquier monitor sin deformar.
        # ------------------------------------------------------------------
        sw, sh = pantalla if pantalla else obtener_tamano_pantalla()
        self.pantalla_w, self.pantalla_h = sw, sh

        orig_h, orig_w = imagen.shape[:2]
        # Altura del HUD proporcional al ancho de la pantalla
        u0 = max(0.6, min(1.8, sw / 1280.0))
        self.hud_h = int(84 * u0)

        # La foto se ajusta al área disponible (toda la pantalla menos el HUD)
        area_w, area_h = sw, sh - self.hud_h
        escala = min(area_w / orig_w, area_h / orig_h)
        nuevo_w = max(n * 40, int(orig_w * escala))
        nuevo_h = max(n * 40, int(orig_h * escala))
        if (nuevo_w, nuevo_h) != (orig_w, orig_h):
            interp = cv2.INTER_AREA if escala < 1 else cv2.INTER_LINEAR
            imagen = cv2.resize(imagen, (nuevo_w, nuevo_h), interpolation=interp)

        # Recortamos para que las dimensiones sean divisibles por n
        alto, ancho = imagen.shape[:2]
        self.alto = alto - (alto % n)
        self.ancho = ancho - (ancho % n)
        self.imagen = imagen[:self.alto, :self.ancho].copy()

        # Posición del tablero, centrado dentro del lienzo de pantalla completa
        self.off_x = (sw - self.ancho) // 2
        self.off_y = self.hud_h + (sh - self.hud_h - self.alto) // 2

        # Factor de escala de la INTERFAZ (fuentes/botones) respecto a 1280 px
        self.u = max(0.6, min(1.8, self.ancho / 1280.0))

        # Tamaño de cada celda de la cuadrícula
        self.alto_pieza = self.alto // n
        self.ancho_pieza = self.ancho // n

        # Radio de las pestañas/huecos y margen extra alrededor de cada pieza
        self.radio = max(8, int(0.22 * min(self.alto_pieza, self.ancho_pieza)))
        self.margen = self.radio + 3

        # Recursos visuales reutilizables
        # Fondo: la foto resuelta muy oscurecida (se ve mejor que un gris plano
        # y sirve de guía MUY sutil al colocar las piezas).
        self.fondo = (self.imagen.astype(np.float32) * 0.16).astype(np.uint8)
        # Miniatura de referencia (se muestra/oculta con el botón VISTA)
        self.miniatura = cv2.resize(self.imagen, (self.ancho // 4, self.alto // 4))

        # 2) Sorteamos los bordes y construimos las piezas (parche + alfa + sombra)
        self._generar_bordes()
        self._construir_piezas()

        # 3) 'orden' guarda qué pieza ocupa cada celda. Lo desordenamos.
        self.orden = list(range(n * n))
        self._desordenar()

        # 4) Barra superior (HUD) a lo ANCHO de toda la pantalla
        u = self.u
        bw, bh = int(176 * u), int(50 * u)
        by = (self.hud_h - bh) // 2
        gap = int(12 * u)
        x_rein = self.pantalla_w - gap - bw
        x_vista = x_rein - gap - bw
        x_pista = x_vista - gap - bw
        self.btn_pista = (x_pista, by, bw, bh)
        self.btn_vista = (x_vista, by, bw, bh)
        self.btn_reiniciar = (x_rein, by, bw, bh)

        # Estado del juego
        self.seleccionada = None        # primera pieza elegida para intercambiar
        self.resuelto = False
        self.movimientos = 0            # contador de intercambios
        self.pistas_usadas = 0          # cuántas pistas pidió el jugador
        self.max_pistas = Config.MAX_PISTAS         # límite de pistas (3)
        self.t_inicio = None            # el cronómetro arranca con el 1er clic
        self.t_fin = None
        self.mostrar_preview = False    # vista previa de la referencia
        self.vista_disponible = True    # la vista previa es de UN SOLO uso
        self.pista_par = None           # (origen, destino) a resaltar
        self.pista_hasta = 0.0          # instante hasta el que se ve la pista
        self.nombre_ventana = "Rompecabezas - resuelvelo!"

    # ----- Sorteo de pestañas/huecos -----
    def _generar_bordes(self):
        """
        Asigna a cada pieza el tipo de sus 4 bordes:
            0 = recto (borde exterior del tablero)
           +1 = pestaña (saliente hacia afuera)
           -1 = hueco   (entrante hacia adentro)
        Los bordes interiores se sortean en pareja y SIEMPRE son complementarios
        (si una pieza saca pestaña, la vecina pone hueco).
        """
        n = self.n
        self.borde_top = [[0] * n for _ in range(n)]
        self.borde_bottom = [[0] * n for _ in range(n)]
        self.borde_left = [[0] * n for _ in range(n)]
        self.borde_right = [[0] * n for _ in range(n)]

        # Bordes verticales: derecha de (i,j) <-> izquierda de (i,j+1)
        for i in range(n):
            for j in range(n - 1):
                s = random.choice((1, -1))
                self.borde_right[i][j] = s
                self.borde_left[i][j + 1] = -s

        # Bordes horizontales: abajo de (i,j) <-> arriba de (i+1,j)
        for i in range(n - 1):
            for j in range(n):
                s = random.choice((1, -1))
                self.borde_bottom[i][j] = s
                self.borde_top[i + 1][j] = -s

    def _alpha_pieza(self, i, j, ss=3):
        """
        Silueta de la pieza (i, j) como ALFA suave (0..1).

        Se dibuja a mayor resolución (factor ss) y luego se reduce con
        INTER_AREA: así los bordes de las pestañas quedan ANTI-ALIASING
        (suaves) en vez de dentados.
        """
        m, cw, ch, r = self.margen, self.ancho_pieza, self.alto_pieza, self.radio
        H, W = ch + 2 * m, cw + 2 * m
        M, CW, CH, R = m * ss, cw * ss, ch * ss, r * ss
        big = np.zeros((H * ss, W * ss), np.uint8)

        # Cuerpo rectangular de la celda dentro del parche
        cv2.rectangle(big, (M, M), (M + CW - 1, M + CH - 1), 255, -1)

        # Puntos medios de cada borde (sobre la línea del borde)
        bordes = (
            ((M + CW // 2, M),        self.borde_top[i][j]),     # arriba
            ((M + CW // 2, M + CH),   self.borde_bottom[i][j]),  # abajo
            ((M, M + CH // 2),        self.borde_left[i][j]),    # izquierda
            ((M + CW, M + CH // 2),   self.borde_right[i][j]),   # derecha
        )
        # Primero las pestañas (suman) y luego los huecos (restan)
        for (cx, cy), tipo in bordes:
            if tipo == 1:
                cv2.circle(big, (cx, cy), R, 255, -1)
        for (cx, cy), tipo in bordes:
            if tipo == -1:
                cv2.circle(big, (cx, cy), R, 0, -1)

        alpha = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
        return alpha.astype(np.float32) / 255.0

    def _construir_piezas(self):
        """Genera, por pieza: parche de imagen, alfa suave, sombra y contorno."""
        m, cw, ch = self.margen, self.ancho_pieza, self.alto_pieza
        H, W = ch + 2 * m, cw + 2 * m

        self.parches = []     # imagen BGR (con margen) de cada pieza
        self.alphas = []      # alfa suave HxWx1 (para pegar con anti-aliasing)
        self.sombras = []     # alfa difuminado HxWx1 (para dibujar la sombra)
        self.contornos = []   # contorno de la silueta (para dibujar el borde)

        sigma = max(2.0, self.radio * 0.30)
        for celda in range(self.n * self.n):
            i, j = divmod(celda, self.n)
            alpha = self._alpha_pieza(i, j)

            # Recortamos de la imagen la zona de la pieza + el margen para las
            # pestañas. Lo que cae fuera de la imagen queda en negro (esos
            # bordes son rectos, así que el alfa igual los descarta).
            parche = np.zeros((H, W, 3), np.uint8)
            sx0, sy0 = j * cw - m, i * ch - m
            rx0, ry0 = max(0, sx0), max(0, sy0)
            rx1, ry1 = min(self.ancho, sx0 + W), min(self.alto, sy0 + H)
            dx0, dy0 = rx0 - sx0, ry0 - sy0
            parche[dy0:dy0 + (ry1 - ry0), dx0:dx0 + (rx1 - rx0)] = \
                self.imagen[ry0:ry1, rx0:rx1]

            self.parches.append(parche)
            self.alphas.append(alpha[..., None])
            self.sombras.append(cv2.GaussianBlur(alpha, (0, 0), sigma)[..., None])

            binm = (alpha > 0.5).astype(np.uint8) * 255
            contornos, _ = cv2.findContours(
                binm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            self.contornos.append(max(contornos, key=cv2.contourArea))

    # ----- Desordenar -----
    def _desordenar(self):
        """Baraja el orden de las piezas hasta que NO quede resuelto."""
        while True:
            random.shuffle(self.orden)
            if self.orden != list(range(self.n * self.n)):
                break

    # ----- Pegado de una pieza sobre el tablero -----
    @staticmethod
    def _recorte(x0, y0, W, H, tablero):
        """Intersección del parche con el tablero. None si no hay solapamiento."""
        bx0, by0 = max(0, x0), max(0, y0)
        bx1 = min(tablero.shape[1], x0 + W)
        by1 = min(tablero.shape[0], y0 + H)
        if bx1 <= bx0 or by1 <= by0:
            return None
        return bx0, by0, bx1, by1, bx0 - x0, by0 - y0

    def _pegar(self, tablero, parche, alpha, x0, y0):
        """Mezcla el parche sobre el tablero usando alfa (bordes suaves)."""
        H, W = alpha.shape[:2]
        rec = self._recorte(x0, y0, W, H, tablero)
        if rec is None:
            return
        bx0, by0, bx1, by1, px0, py0 = rec
        a = alpha[py0:py0 + (by1 - by0), px0:px0 + (bx1 - bx0)]
        p = parche[py0:py0 + (by1 - by0), px0:px0 + (bx1 - bx0)].astype(np.float32)
        region = tablero[by0:by1, bx0:bx1].astype(np.float32)
        tablero[by0:by1, bx0:bx1] = (a * p + (1.0 - a) * region).astype(np.uint8)

    def _sombrear(self, tablero, sombra, x0, y0, fuerza=0.40):
        """Oscurece el tablero según el alfa de sombra (da sensación de relieve)."""
        H, W = sombra.shape[:2]
        rec = self._recorte(x0, y0, W, H, tablero)
        if rec is None:
            return
        bx0, by0, bx1, by1, px0, py0 = rec
        s = sombra[py0:py0 + (by1 - by0), px0:px0 + (bx1 - bx0)]
        region = tablero[by0:by1, bx0:bx1].astype(np.float32)
        tablero[by0:by1, bx0:bx1] = (region * (1.0 - fuerza * s)).astype(np.uint8)

    # ----- Progreso -----
    def progreso(self):
        """Fracción de piezas (0..1) que ya están en su posición correcta."""
        correctas = sum(1 for c, idp in enumerate(self.orden) if c == idp)
        return correctas / (self.n * self.n)

    # ----- Dibujado del tablero -----
    def render(self):
        """Construye el fotograma completo: barra superior (HUD) + tablero."""
        m = self.margen
        # Lienzo del tamaño EXACTO de la pantalla (fondo oscuro en los bordes)
        canvas = np.full((self.pantalla_h, self.pantalla_w, 3), 18, np.uint8)
        # Vista del tablero, centrado dentro del lienzo
        tablero = canvas[self.off_y:self.off_y + self.alto,
                         self.off_x:self.off_x + self.ancho]
        tablero[:] = self.fondo                   # fondo ambiental

        desfase = max(3, int(6 * self.u))         # desplazamiento de la sombra

        # 1) Sombras (desplazadas) -> dan relieve a las piezas
        for celda, id_pieza in enumerate(self.orden):
            i, j = divmod(celda, self.n)
            x0, y0 = j * self.ancho_pieza - m, i * self.alto_pieza - m
            self._sombrear(tablero, self.sombras[id_pieza],
                           x0 + desfase, y0 + desfase)

        # 2) Piezas con bordes suaves (alpha-blending)
        for celda, id_pieza in enumerate(self.orden):
            i, j = divmod(celda, self.n)
            x0, y0 = j * self.ancho_pieza - m, i * self.alto_pieza - m
            self._pegar(tablero, self.parches[id_pieza],
                        self.alphas[id_pieza], x0, y0)

        # 3) Contorno de cada pieza (y resaltado de la seleccionada)
        for celda, id_pieza in enumerate(self.orden):
            i, j = divmod(celda, self.n)
            x0, y0 = j * self.ancho_pieza - m, i * self.alto_pieza - m
            seleccion = (celda == self.seleccionada)
            color = (0, 255, 255) if seleccion else (20, 20, 20)
            grosor = max(2, int(3 * self.u)) if seleccion else 1
            cv2.drawContours(tablero, [self.contornos[id_pieza]], -1, color,
                             grosor, cv2.LINE_AA, offset=(x0, y0))

        # 4) Pista activa (de dónde a dónde mover)
        self._dibujar_pista(tablero)

        # 5) Vista previa de la referencia
        if self.mostrar_preview:
            self._dibujar_miniatura(tablero)

        # 6) Pantalla de victoria
        if self.resuelto:
            self._dibujar_victoria(tablero)

        # 7) Barra superior con estadísticas y botones
        self._dibujar_hud(canvas)
        return canvas

    # ----- Tiempo -----
    @staticmethod
    def _fmt_tiempo(seg):
        """Formatea segundos como m:ss."""
        seg = max(0, int(seg))
        return f"{seg // 60}:{seg % 60:02d}"

    def _tiempo_actual(self):
        """Segundos transcurridos (0 si aún no empezó; congelado al resolver)."""
        if self.t_inicio is None:
            return 0.0
        fin = self.t_fin if self.t_fin is not None else time.time()
        return fin - self.t_inicio

    # ----- Barra superior (HUD) -----
    @staticmethod
    def _en_rect(x, y, rect):
        rx, ry, rw, rh = rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def _dibujar_boton(self, canvas, rect, texto, color):
        x, y, w, h = rect
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 255, 255), 1)
        fuente = cv2.FONT_HERSHEY_SIMPLEX
        escala = max(0.4, 0.55 * self.u)
        (tw, th), _ = cv2.getTextSize(texto, fuente, escala, 1)
        if tw > w - 8:                       # ajusta el texto para que no se corte
            escala *= (w - 8) / tw
            (tw, th), _ = cv2.getTextSize(texto, fuente, escala, 1)
        cv2.putText(canvas, texto, (x + (w - tw) // 2, y + (h + th) // 2),
                    fuente, escala, (255, 255, 255), 1, cv2.LINE_AA)

    def _dibujar_hud(self, canvas):
        """Dibuja la barra superior: dificultad, stats, progreso y botones."""
        fuente = cv2.FONT_HERSHEY_SIMPLEX
        u, H = self.u, self.hud_h
        cv2.rectangle(canvas, (0, 0), (self.pantalla_w, H), (38, 38, 44), -1)
        cv2.line(canvas, (0, H), (self.pantalla_w, H), (0, 0, 0), 2)

        # Izquierda: dificultad + contadores
        cv2.putText(canvas, f"{self.nombre}  {self.n}x{self.n}",
                    (int(16 * u), int(H * 0.42)), fuente, 0.8 * u,
                    (0, 255, 255), max(1, int(2 * u)), cv2.LINE_AA)
        info = (f"Mov: {self.movimientos}    "
                f"Tiempo: {self._fmt_tiempo(self._tiempo_actual())}    "
                f"Pistas: {self.pistas_usadas}/{self.max_pistas}")
        cv2.putText(canvas, info, (int(16 * u), int(H * 0.82)), fuente,
                    0.58 * u, (230, 230, 230), 1, cv2.LINE_AA)

        # Centro: barra de progreso (% de piezas en su lugar)
        prog = self.progreso()
        bx0 = int(self.pantalla_w * 0.40)
        bx1 = self.btn_pista[0] - int(20 * u)
        if bx1 > bx0 + 40:
            byc = int(H * 0.46)
            bh2 = int(H * 0.26)
            cv2.putText(canvas, f"Progreso  {int(round(prog * 100))}%",
                        (bx0, int(H * 0.34)), fuente, 0.55 * u,
                        (255, 255, 255), 1, cv2.LINE_AA)
            cv2.rectangle(canvas, (bx0, byc), (bx1, byc + bh2), (80, 80, 80), -1)
            relleno = bx0 + int((bx1 - bx0) * prog)
            color = (0, 220, 0) if prog >= 0.999 else (0, 200, 255)
            cv2.rectangle(canvas, (bx0, byc), (relleno, byc + bh2), color, -1)
            cv2.rectangle(canvas, (bx0, byc), (bx1, byc + bh2), (200, 200, 200), 1)

        # Derecha: botones cliqueables
        # PISTA: muestra cuántas quedan; se apaga (gris) al agotarse.
        pistas_rest = self.max_pistas - self.pistas_usadas
        col_pista = (60, 140, 240) if pistas_rest > 0 else (70, 70, 70)
        self._dibujar_boton(canvas, self.btn_pista, f"PISTA ({pistas_rest})", col_pista)
        # VISTA: de un solo uso. Verde si está activa, gris si disponible,
        # apagada si ya se gastó.
        if self.mostrar_preview:
            col_vista = (60, 175, 60)
        elif self.vista_disponible:
            col_vista = (95, 95, 95)
        else:
            col_vista = (70, 70, 70)
        self._dibujar_boton(canvas, self.btn_vista, "VISTA (P)", col_vista)
        self._dibujar_boton(canvas, self.btn_reiniciar, "REINICIAR (R)", (70, 70, 205))

    # ----- Pista -----
    def _dibujar_pista(self, tablero):
        """Resalta la pieza a mover (naranja) y su lugar correcto (verde)."""
        if not self.pista_par or time.time() > self.pista_hasta:
            self.pista_par = None
            return
        origen, destino = self.pista_par
        cw, ch = self.ancho_pieza, self.alto_pieza
        grosor = max(2, int(4 * self.u))

        def centro(celda):
            i, j = divmod(celda, self.n)
            return (j * cw + cw // 2, i * ch + ch // 2)

        def recuadro(celda, color):
            i, j = divmod(celda, self.n)
            cv2.rectangle(tablero, (j * cw + 3, i * ch + 3),
                          ((j + 1) * cw - 3, (i + 1) * ch - 3), color, grosor)

        recuadro(origen, (0, 165, 255))     # naranja: pieza a mover
        recuadro(destino, (0, 255, 0))      # verde: a dónde llevarla
        cv2.arrowedLine(tablero, centro(origen), centro(destino),
                        (255, 255, 255), max(2, int(3 * self.u)),
                        cv2.LINE_AA, 0, 0.18)

    # ----- Vista previa -----
    def _dibujar_miniatura(self, tablero):
        """Muestra la foto original (referencia) en la esquina inferior derecha."""
        mh, mw = self.miniatura.shape[:2]
        x1, y1 = self.ancho - 12, self.alto - 12
        x0, y0 = x1 - mw, y1 - mh
        alto_etiqueta = int(22 * self.u) + 4
        cv2.rectangle(tablero, (x0 - 3, y0 - alto_etiqueta),
                      (x1 + 3, y1 + 3), (0, 0, 0), -1)
        tablero[y0:y1, x0:x1] = self.miniatura
        cv2.rectangle(tablero, (x0, y0), (x1, y1), (255, 255, 255), 2)
        cv2.putText(tablero, "Referencia", (x0, y0 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5 * self.u, (255, 255, 255), 1,
                    cv2.LINE_AA)

    # ----- Victoria -----
    def _dibujar_victoria(self, tablero):
        """Confeti animado + panel con el resumen de la partida."""
        for _ in range(70):
            x = random.randint(0, self.ancho - 1)
            y = random.randint(0, self.alto - 1)
            col = (random.randint(0, 255), random.randint(0, 255),
                   random.randint(0, 255))
            cv2.circle(tablero, (x, y), random.randint(2, 5), col, -1)

        u = self.u
        seg = self._tiempo_actual()
        lineas = [
            ("RESUELTO!", 1.8 * u, max(2, int(4 * u)), (0, 255, 0)),
            (f"Tiempo: {self._fmt_tiempo(seg)}", 0.9 * u, max(1, int(2 * u)),
             (255, 255, 255)),
            (f"Movimientos: {self.movimientos}    Pistas: {self.pistas_usadas}",
             0.9 * u, max(1, int(2 * u)), (255, 255, 255)),
        ]
        fuente = cv2.FONT_HERSHEY_SIMPLEX
        tamanos = [cv2.getTextSize(t, fuente, e, g)[0] for t, e, g, _ in lineas]
        ancho_panel = max(w for w, _ in tamanos) + int(80 * u)
        alto_panel = sum(h for _, h in tamanos) + int(40 * u) + int(22 * u) * (len(lineas) - 1)
        cx, cy = self.ancho // 2, self.alto // 2
        px0, py0 = cx - ancho_panel // 2, cy - alto_panel // 2

        overlay = tablero.copy()
        cv2.rectangle(overlay, (px0, py0), (px0 + ancho_panel, py0 + alto_panel),
                      (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, tablero, 0.45, 0, tablero)
        cv2.rectangle(tablero, (px0, py0), (px0 + ancho_panel, py0 + alto_panel),
                      (0, 255, 0), max(2, int(3 * u)))

        y = py0 + int(28 * u)
        for (texto, esc, gro, col), (tw, th) in zip(lineas, tamanos):
            y += th
            cv2.putText(tablero, texto, (cx - tw // 2, y), fuente, esc, col,
                        gro, cv2.LINE_AA)
            y += int(22 * u)

    # ----- Interacción con el mouse -----
    def on_mouse(self, evento, x, y, flags, params):
        """Callback de OpenCV: botones del HUD e intercambio de piezas."""
        if evento != cv2.EVENT_LBUTTONDOWN:
            return

        # Clic en la barra superior -> botones
        if y < self.hud_h:
            if self._en_rect(x, y, self.btn_pista):
                self.pedir_pista()
            elif self._en_rect(x, y, self.btn_vista):
                self.alternar_vista()
            elif self._en_rect(x, y, self.btn_reiniciar):
                self.reiniciar()
            return

        if self.resuelto:
            return

        # Coordenadas dentro del tablero (descontando el desfase de centrado)
        xb, yb = x - self.off_x, y - self.off_y
        if xb < 0 or yb < 0:
            return
        col = xb // self.ancho_pieza
        fila = yb // self.alto_pieza
        if col < 0 or fila < 0 or col >= self.n or fila >= self.n:
            return
        celda = fila * self.n + col

        if self.t_inicio is None:           # arranca el cronómetro al 1er clic
            self.t_inicio = time.time()

        if self.seleccionada is None:
            self.seleccionada = celda        # primer clic: marcar
        elif self.seleccionada == celda:
            self.seleccionada = None         # clic en la misma: deseleccionar
        else:
            a, b = self.seleccionada, celda  # segundo clic: intercambiar
            self.orden[a], self.orden[b] = self.orden[b], self.orden[a]
            self.seleccionada = None
            self.movimientos += 1
            self._verificar()

    def _verificar(self):
        """Comprueba si las piezas están en su posición original."""
        if self.orden == list(range(self.n * self.n)):
            self.resuelto = True
            self.seleccionada = None
            if self.t_fin is None:
                self.t_fin = time.time()

    # ----- Pista (máximo Config.MAX_PISTAS) -----
    def pedir_pista(self):
        """Elige una pieza mal colocada y marca de dónde a dónde moverla.

        Está LIMITADA: si ya se usaron todas las pistas permitidas, no hace nada.
        """
        if self.resuelto or self.pistas_usadas >= self.max_pistas:
            return
        mal = [c for c, idp in enumerate(self.orden) if c != idp]
        if not mal:
            return
        destino = random.choice(mal)            # celda que falta completar
        origen = self.orden.index(destino)      # dónde está ahora esa pieza
        self.pista_par = (origen, destino)
        self.pista_hasta = time.time() + 3.0
        self.pistas_usadas += 1
        if self.t_inicio is None:
            self.t_inicio = time.time()

    # ----- Vista previa (UN SOLO uso) -----
    def alternar_vista(self):
        """Muestra/oculta la referencia. Es de un solo uso: una vez que se
        oculta (o se agota), ya no se puede volver a mostrar."""
        if self.mostrar_preview:
            self.mostrar_preview = False        # ocultar -> se acaba el uso
        elif self.vista_disponible:
            self.mostrar_preview = True
            self.vista_disponible = False       # se consume el único uso

    # ----- Reinicio -----
    def reiniciar(self):
        """Vuelve a desordenar y pone los contadores y las ayudas a cero."""
        self.resuelto = False
        self.seleccionada = None
        self.movimientos = 0
        self.pistas_usadas = 0
        self.t_inicio = None
        self.t_fin = None
        self.pista_par = None
        self.mostrar_preview = False
        self.vista_disponible = True
        self._desordenar()

    # ----- Bucle del juego -----
    def jugar(self):
        """Abre la ventana del rompecabezas (PANTALLA COMPLETA) y gestiona el juego."""
        preparar_ventana_pantalla_completa(self.nombre_ventana)
        cv2.setMouseCallback(self.nombre_ventana, self.on_mouse)

        print(f"\n[JUEGO] Dificultad {self.nombre} ({self.n}x{self.n} = "
              f"{self.n * self.n} piezas).")
        print("[JUEGO] Clic en dos piezas para intercambiarlas.")
        print("[JUEGO]  H = pista   P = vista previa   R = reiniciar   "
              "ESC/Q = salir")

        while True:
            cv2.imshow(self.nombre_ventana, self.render())
            tecla = cv2.waitKey(20) & 0xFF
            if tecla in (27, ord('q')):           # ESC o Q -> salir
                break
            elif tecla == ord('r'):               # R -> reiniciar partida
                self.reiniciar()
            elif tecla == ord('h'):               # H -> pista (máx. 3)
                self.pedir_pista()
            elif tecla == ord('p'):               # P -> vista previa (un solo uso)
                self.alternar_vista()

        cv2.destroyWindow(self.nombre_ventana)


# =============================================================================
#  MÓDULO 4: UTILIDADES DE DIBUJO SOBRE EL VIDEO
# =============================================================================
def texto_centrado_horizontal(frame, texto, y, escala, color, grosor=2, fondo=True):
    """Dibuja un texto centrado horizontalmente; opcionalmente con fondo."""
    fuente = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(texto, fuente, escala, grosor)
    x = (frame.shape[1] - tw) // 2
    if fondo:
        cv2.rectangle(frame, (x - 15, y - th - 15), (x + tw + 15, y + 15), (0, 0, 0), -1)
    cv2.putText(frame, texto, (x, y), fuente, escala, color, grosor, cv2.LINE_AA)


def dibujar_barra_progreso(frame, fraccion, color=(0, 200, 255)):
    """Dibuja una barra de progreso en la parte inferior (0.0 a 1.0)."""
    h, w = frame.shape[:2]
    margen = 60
    y0, y1 = h - 50, h - 30
    cv2.rectangle(frame, (margen, y0), (w - margen, y1), (80, 80, 80), 2)
    ancho = int((w - 2 * margen) * max(0.0, min(1.0, fraccion)))
    cv2.rectangle(frame, (margen, y0), (margen + ancho, y1), color, -1)


# =============================================================================
#  MÓDULO 5: MÁQUINA DE ESTADOS PRINCIPAL
# =============================================================================
# Estados posibles del juego
ESTADO_DETECCION = "DETECCION"          # esperando la mano abierta
ESTADO_CUENTA = "CUENTA_REGRESIVA"      # mostrando 3, 2, 1 y luego a jugar


def main():
    print("=" * 60)
    print(" ROMPECABEZAS FOTOGRAFICO POR GESTOS")
    print("=" * 60)
    print(" - Muestra la MANO ABIERTA (5 dedos) para tomar la foto.")
    print(" - Se arma directamente un rompecabezas FACIL de 3x3.")
    print(" - Pulsa ESC o Q en cualquier momento para salir.")
    print("=" * 60)

    # Tamaño de pantalla (para que las ventanas sean responsive)
    pantalla = obtener_tamano_pantalla()
    print(f"[INFO] Pantalla detectada: {pantalla[0]}x{pantalla[1]}")

    # --- Inicialización de la cámara ---
    captura = cv2.VideoCapture(Config.INDICE_CAMARA)
    captura.set(cv2.CAP_PROP_FRAME_WIDTH, Config.ANCHO_CAMARA)
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.ALTO_CAMARA)
    if not captura.isOpened():
        print("[ERROR] No se pudo abrir la cámara. Revisa el índice/permisos.")
        return

    detector = DetectorManos(max_manos=1)
    suavizador = SuavizadorDedos()

    # Variables de estado
    estado = ESTADO_DETECCION
    t_inicio_cuenta = 0.0      # marca de tiempo del inicio de la cuenta regresiva
    foto_congelada = None      # fotograma capturado para el rompecabezas
    ventana_video = "Camara - Rompecabezas por gestos"

    # Ventana de cámara en PANTALLA COMPLETA
    preparar_ventana_pantalla_completa(ventana_video)

    while True:
        ok, frame = captura.read()
        if not ok:
            print("[ERROR] No se pudo leer el fotograma de la cámara.")
            break

        # Espejo: más natural para el usuario (como un espejo real)
        frame = cv2.flip(frame, 1)

        # MediaPipe procesa SIEMPRE el frame en vivo (aunque se muestre la foto)
        detector.procesar(frame)
        n_dedos = detector.contar_dedos()
        suavizador.actualizar(n_dedos if n_dedos is not None else -1)
        dedos_estable = suavizador.valor_estable()

        # =================================================================
        #  ESTADO 1: DETECCIÓN (esperar mano abierta)
        # =================================================================
        if estado == ESTADO_DETECCION:
            detector.dibujar(frame)
            texto_centrado_horizontal(
                frame, "Muestra la MANO ABIERTA para tomar la foto", 60,
                0.9, (0, 255, 0))
            if n_dedos is not None:
                texto_centrado_horizontal(
                    frame, f"Dedos detectados: {n_dedos}", 110, 0.7, (255, 255, 255))

            # Mano abierta estable (5 dedos) -> iniciar cuenta regresiva
            if dedos_estable == 5:
                estado = ESTADO_CUENTA
                t_inicio_cuenta = time.time()
                suavizador.reiniciar()

        # =================================================================
        #  ESTADO 2: CUENTA REGRESIVA (3, 2, 1) y captura
        # =================================================================
        elif estado == ESTADO_CUENTA:
            transcurrido = time.time() - t_inicio_cuenta
            total = 3 * Config.SEG_POR_NUMERO
            restante = total - transcurrido
            numero = int(restante // Config.SEG_POR_NUMERO) + 1  # 3 -> 2 -> 1

            if restante > 0:
                # Mostramos el número gigante centrado
                texto_centrado_horizontal(
                    frame, str(numero), int(frame.shape[0] * 0.6),
                    6.0, (0, 200, 255), grosor=12, fondo=False)
                texto_centrado_horizontal(
                    frame, "Preparate para la foto...", 60, 1.0, (0, 255, 0))
            else:
                # ¡Tiempo! Congelamos el fotograma y armamos DIRECTAMENTE el
                # rompecabezas FÁCIL (3x3): ya no hay menú de dificultad.
                foto_congelada = frame.copy()
                suavizador.reiniciar()
                print(f"[FOTO] Imagen capturada. Iniciando rompecabezas "
                      f"{Config.NOMBRE_NIVEL} ({Config.TAMANO_NIVEL}x"
                      f"{Config.TAMANO_NIVEL}).")

                # Cerramos la ventana de video y lanzamos el rompecabezas
                cv2.destroyWindow(ventana_video)
                puzzle = Rompecabezas(foto_congelada, Config.TAMANO_NIVEL,
                                      Config.NOMBRE_NIVEL, pantalla)
                puzzle.jugar()

                # Al terminar, reiniciamos el flujo para una nueva partida
                estado = ESTADO_DETECCION
                foto_congelada = None
                suavizador.reiniciar()
                # Recreamos la ventana de cámara (pantalla completa) para seguir
                preparar_ventana_pantalla_completa(ventana_video)
                continue

        # --- Mostrar la ventana de video (compuesta a pantalla completa) ---
        cv2.imshow(ventana_video, componer_pantalla(frame, pantalla[0], pantalla[1]))
        tecla = cv2.waitKey(5) & 0xFF
        if tecla in (27, ord('q')):
            break
        if tecla == ord('r'):
            # Reiniciar manualmente el flujo en cualquier momento
            estado = ESTADO_DETECCION
            foto_congelada = None
            suavizador.reiniciar()

    # --- Limpieza de recursos ---
    captura.release()
    detector.cerrar()
    cv2.destroyAllWindows()
    print("\n[FIN] Programa finalizado. ¡Gracias por jugar!")


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    main()
