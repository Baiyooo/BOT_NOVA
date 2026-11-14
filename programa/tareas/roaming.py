"""
Bot para el minijuego "Roaming Test" (evento Neural Roaming) de Nova Empire.

Calibrado sobre un vídeo real del juego en BlueStacks: tablero 7x7, 5 tipos de
ficha, 30 movimientos por partida. La rejilla se detecta automaticamente en cada
captura, asi que funciona aunque cambie la resolucion o muevas la ventana.

Habla con BlueStacks por ADB: captura la pantalla de Android y envia los
deslizamientos. No toca el raton, asi que puedes seguir usando el PC.

Instalacion:
  pip install opencv-python numpy
  (el ADB lo pone BlueStacks: HD-Adb.exe)

Uso:
  python main.py -d 127.0.0.1:5555 --check     ve el tablero?
  python main.py -d 127.0.0.1:5555 --games 3   juega 3 partidas
  python main.py -d 127.0.0.1:5555 -d 127.0.0.1:5565 --games 3
      (varias cuentas a la vez; 3 partidas CADA UNA)

Pulsa Ctrl+C en cualquier momento para parar.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


# --- Tonos (HSV, 0-360) de los 5 tipos de ficha, medidos del video -----------
REFERENCE_HUES = {
    "naranja": 25.0,
    "verde": 93.5,
    "azul": 214.0,
    "morado": 277.5,
    "rosa": 338.0,
}
HUE_TOLERANCE = 22.0     # grados; mas de esto y la casilla se marca como desconocida
SAT_MIN, VAL_MIN = 90, 110   # umbral para considerar un pixel "parte del icono"

SYMBOLS = {"naranja": "O", "verde": "G", "azul": "B", "morado": "P", "rosa": "R"}


# ============================================================================
# Deteccion de la rejilla
# ============================================================================
@dataclass
class Grid:
    x0: float      # centro de la primera columna
    y0: float      # centro de la primera fila
    dx: float      # separacion entre columnas
    dy: float      # separacion entre filas
    rows: int
    cols: int

    def center(self, r: int, c: int) -> tuple[int, int]:
        return int(round(self.x0 + c * self.dx)), int(round(self.y0 + r * self.dy))


def classify_hue(hue: float) -> str | None:
    name, dist = None, 999.0
    for k, ref in REFERENCE_HUES.items():
        d = abs(hue - ref)
        d = min(d, 360 - d)
        if d < dist:
            name, dist = k, d
    return name if dist <= HUE_TOLERANCE else None


def _mean_hue(hsv_pixels: np.ndarray) -> float | None:
    sel = hsv_pixels[(hsv_pixels[:, 1] > SAT_MIN) & (hsv_pixels[:, 2] > VAL_MIN)]
    if len(sel) < 25:
        return None
    ang = np.deg2rad(sel[:, 0].astype(float) * 2.0)
    return float(np.rad2deg(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360)


def _best_rect(occ: np.ndarray, min_side: int, min_fill: float = 0.7):
    """Mayor rectangulo de la malla con suficientes casillas ocupadas.
    Admite huecos: una ficha en plena animacion puede no detectarse."""
    rows, cols = occ.shape
    integral = np.zeros((rows + 1, cols + 1), dtype=int)
    integral[1:, 1:] = np.cumsum(np.cumsum(occ.astype(int), axis=0), axis=1)

    def total(r0, c0, r1, c1):
        return (integral[r1 + 1, c1 + 1] - integral[r0, c1 + 1]
                - integral[r1 + 1, c0] + integral[r0, c0])

    row_sum = np.cumsum(occ.astype(int), axis=1)
    col_sum = np.cumsum(occ.astype(int), axis=0)

    def rows_ok(r0, c0, r1, c1):
        seg = row_sum[r0:r1 + 1, c1] - (row_sum[r0:r1 + 1, c0 - 1] if c0 else 0)
        return bool((seg >= 0.5 * (c1 - c0 + 1)).all())

    def cols_ok(r0, c0, r1, c1):
        seg = col_sum[r1, c0:c1 + 1] - (col_sum[r0 - 1, c0:c1 + 1] if r0 else 0)
        return bool((seg >= 0.5 * (r1 - r0 + 1)).all())

    best = None
    for r0 in range(rows):
        for r1 in range(r0 + min_side - 1, rows):
            for c0 in range(cols):
                for c1 in range(c0 + min_side - 1, cols):
                    area = (r1 - r0 + 1) * (c1 - c0 + 1)
                    if best and area <= best[0]:
                        continue
                    # cada fila y cada columna del tablero tiene que estar poblada:
                    # asi no se cuela una fila suelta de la interfaz
                    if (total(r0, c0, r1, c1) >= min_fill * area
                            and rows_ok(r0, c0, r1, c1) and cols_ok(r0, c0, r1, c1)):
                        best = (area, r0, c0, r1, c1)
    return best[1:] if best else None


def _phase(values: np.ndarray, step: float) -> float:
    """Desfase de la malla, por media circular de los restos."""
    ang = 2 * np.pi * (values % step) / step
    m = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    return float((m % (2 * np.pi)) / (2 * np.pi) * step)


def detect_grid(img: np.ndarray, min_lines: int = 5) -> Grid | None:
    """Localiza el tablero: iconos del color de las fichas dispuestos en malla."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > SAT_MIN) & (hsv[:, :, 2] > VAL_MIN)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    n_lab, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    h, w = mask.shape
    pts, sizes = [], []
    for i in range(1, n_lab):
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if not (12 < bw < w * 0.12 and 12 < bh < h * 0.2):
            continue
        if area < 200 or not (0.5 < bw / bh < 2.2) or area < 0.18 * bw * bh:
            continue
        x, y = int(cents[i][0]), int(cents[i][1])
        rw, rh = max(4, bw // 4), max(4, bh // 4)
        hue = _mean_hue(hsv[y - rh:y + rh, x - rw:x + rw].reshape(-1, 3))
        if hue is None or classify_hue(hue) is None:
            continue            # descarta iconos de la interfaz
        pts.append((cents[i][0], cents[i][1]))
        sizes.append((bw, bh))
    if len(pts) < min_lines * min_lines // 2:
        return None

    P = np.array(pts)
    # paso de la malla: distancia tipica al vecino mas cercano en cada eje
    def axis_step(vals, others, span):
        steps = []
        for i in range(len(vals)):
            same = np.abs(others - others[i]) < span * 0.5
            d = np.abs(vals[same] - vals[i])
            d = d[d > span * 0.3]
            if len(d):
                steps.append(d.min())
        return float(np.median(steps)) if steps else 0.0

    mw = float(np.median([s[0] for s in sizes]))
    mh = float(np.median([s[1] for s in sizes]))
    dx = axis_step(P[:, 0], P[:, 1], mw)
    dy = axis_step(P[:, 1], P[:, 0], mh)
    if dx <= 0 or dy <= 0:
        return None

    # indices de malla a partir del desfase, y descarte de lo que no encaja
    px, py = _phase(P[:, 0], dx), _phase(P[:, 1], dy)
    fx = (P[:, 0] - px) / dx
    fy = (P[:, 1] - py) / dy
    aligned = (np.abs(fx - np.round(fx)) < 0.25) & (np.abs(fy - np.round(fy)) < 0.25)
    P, fx, fy = P[aligned], fx[aligned], fy[aligned]
    if len(P) < min_lines * min_lines // 2:
        return None

    j = (np.round(fx) - np.round(fx).min()).astype(int)
    i = (np.round(fy) - np.round(fy).min()).astype(int)
    occ = np.zeros((i.max() + 1, j.max() + 1), dtype=bool)
    occ[i, j] = True
    rect = _best_rect(occ, min_lines)
    if rect is None:
        return None
    r0, c0, r1, c1 = rect
    rows, cols = r1 - r0 + 1, c1 - c0 + 1

    # ajuste fino por minimos cuadrados usando solo los puntos del tablero
    inside = (i >= r0) & (i <= r1) & (j >= c0) & (j <= c1)
    A = np.vstack([j[inside] - c0, np.ones(inside.sum())]).T
    dx_f, x0_f = np.linalg.lstsq(A, P[inside, 0], rcond=None)[0]
    B = np.vstack([i[inside] - r0, np.ones(inside.sum())]).T
    dy_f, y0_f = np.linalg.lstsq(B, P[inside, 1], rcond=None)[0]
    return Grid(x0=float(x0_f), dx=float(dx_f), cols=cols,
                y0=float(y0_f), dy=float(dy_f), rows=rows)


# ============================================================================
# Lectura del tablero
# ============================================================================
def read_board(img: np.ndarray, grid: Grid) -> list[list[str | None]]:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    rw, rh = int(grid.dx * 0.30), int(grid.dy * 0.30)
    board = []
    for r in range(grid.rows):
        row = []
        for c in range(grid.cols):
            x, y = grid.center(r, c)
            patch = hsv[max(0, y - rh):y + rh, max(0, x - rw):x + rw].reshape(-1, 3)
            hue = _mean_hue(patch)
            row.append(None if hue is None else classify_hue(hue))
        board.append(row)
    return board


#  El boton Start/Restart del panel izquierdo NO se busca por color: la pantalla
#  de "!Nuevos objetos!" tiene un cartel naranja que se confunde con el. Su sitio
#  es muy estable, asi que se calcula a partir del tablero (o por proporcion de
#  la pantalla si aun no se ha visto ninguno).
BOTON_REL_CELDAS = (-2.85, 6.00)    # respecto al origen del tablero, en celdas
BOTON_REL_PANTALLA = (0.155, 0.873)  # respaldo: proporcion del ancho y el alto


def boton_start(img: np.ndarray, grid: Grid | None) -> tuple[int, int]:
    if grid:
        return (int(grid.x0 + BOTON_REL_CELDAS[0] * grid.dx),
                int(grid.y0 + BOTON_REL_CELDAS[1] * grid.dy))
    h, w = img.shape[:2]
    return (int(w * BOTON_REL_PANTALLA[0]), int(h * BOTON_REL_PANTALLA[1]))


def board_str(board) -> str:
    return "\n".join("".join(SYMBOLS.get(v, ".") for v in row) for row in board)


def unknown_count(board) -> int:
    return sum(v is None for row in board for v in row)


# ============================================================================
# Logica del match-3
# ============================================================================
def find_lines(b) -> list[list[tuple[int, int]]]:
    """Devuelve las lineas de 3 o mas fichas iguales."""
    rows, cols = len(b), len(b[0])
    lines = []
    for r in range(rows):
        c = 0
        while c < cols:
            v = b[r][c]
            n = 1
            while v is not None and c + n < cols and b[r][c + n] == v:
                n += 1
            if v is not None and n >= 3:
                lines.append([(r, c + i) for i in range(n)])
            c += max(1, n)
    for c in range(cols):
        r = 0
        while r < rows:
            v = b[r][c]
            n = 1
            while v is not None and r + n < rows and b[r + n][c] == v:
                n += 1
            if v is not None and n >= 3:
                lines.append([(r + i, c) for i in range(n)])
            r += max(1, n)
    return lines


def evaluate(b) -> float:
    """Puntua un tablero: simula el despeje y la caida, incluidas las cascadas
    deterministas. Las fichas nuevas que entran por arriba son desconocidas y
    cortan la simulacion, asi que la cascada se valora de forma conservadora."""
    board = [row[:] for row in b]
    rows, cols = len(board), len(board[0])
    total, multiplier = 0.0, 1.0
    for _ in range(4):
        lines = find_lines(board)
        if not lines:
            break
        cleared = set()
        for line in lines:
            n = len(line)
            # premia fuerte las lineas de 4 y 5: suelen dar ficha especial
            total += (n * n * (1.6 if n >= 5 else 1.3 if n == 4 else 1.0)) * multiplier
            cleared |= set(line)
        for r, c in cleared:
            board[r][c] = None
        # gravedad
        for c in range(cols):
            col = [board[r][c] for r in range(rows) if board[r][c] is not None]
            col = [None] * (rows - len(col)) + col
            for r in range(rows):
                board[r][c] = col[r]
        multiplier *= 0.6   # las cascadas valen menos porque dependen del relleno
    return total


Move = tuple[tuple[int, int], tuple[int, int]]


def ranked_moves(b) -> list[tuple[float, Move]]:
    rows, cols = len(b), len(b[0])
    out = []
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 >= rows or c2 >= cols:
                    continue
                a, d = b[r][c], b[r2][c2]
                if a is None or d is None or a == d:
                    continue
                b[r][c], b[r2][c2] = d, a
                score = evaluate(b)
                b[r][c], b[r2][c2] = a, d
                if score > 0:
                    # a igualdad, prefiere abajo: genera mas cascada
                    out.append((score + r * 0.02, ((r, c), (r2, c2))))
    out.sort(key=lambda t: -t[0])
    return out


# ============================================================================
# Control por ADB
# ============================================================================
#  En Windows, cada orden de ADB abriria su propia ventana de consola cuando el
#  programa corre sin consola (pythonw). Como se lanzan varias por segundo, la
#  pantalla se llenaria de cmds parpadeando y robando el foco.
if sys.platform == "win32":
    SIN_VENTANA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
else:
    SIN_VENTANA = {}


# ============================================================================
# Bucle de juego
# ============================================================================
class Bot:
    def __init__(self, ctrl, max_moves=30, settle=0.45, max_wait=8.0, verbose=True,
                 on_log=None, stop_event=None):
        self.ctrl, self.max_moves = ctrl, max_moves
        self.settle, self.max_wait, self.verbose = settle, max_wait, verbose
        self.tag = f"[{ctrl.name}] "
        self.grid: Grid | None = None   # la rejilla no se mueve: se detecta una vez
        self.last_grid: Grid | None = None   # para saber donde pulsar sin tablero
        self._misses = 0
        # para la interfaz grafica: aviso de cada linea y bandera de parada
        self.on_log = on_log
        self.stop = stop_event if stop_event is not None else threading.Event()
        self.status = {"estado": "en espera", "partida": 0, "partidas": 0,
                       "mov": 0, "movs": max_moves}

    def log(self, msg):
        if self.on_log is not None:
            self.on_log(self.ctrl.name, msg)
        elif self.verbose:
            print(self.tag + msg, flush=True)

    def _set(self, **kw):
        self.status.update(kw)

    def parado(self) -> bool:
        return self.stop.is_set()

    def look(self):
        """Captura y lee. Reutiliza la rejilla ya detectada mientras funcione."""
        img = self.ctrl.capture()
        if self.grid is not None:
            board = read_board(img, self.grid)
            if unknown_count(board) <= 0.4 * self.grid.rows * self.grid.cols:
                self._misses = 0
                return img, self.grid, board
            self._misses += 1
            if self._misses < 6:        # seguramente es una animacion, no un fallo
                return img, self.grid, board
            self.grid = None            # el juego ha cambiado: volver a detectar
            self._misses = 0
        grid = detect_grid(img)
        if grid is None:
            return img, None, None
        self.grid = self.last_grid = grid
        return img, grid, read_board(img, grid)

    def wait_stable(self):
        """Espera a que el tablero deje de cambiar (animaciones y cascadas)."""
        prev, deadline = None, time.time() + self.max_wait
        while True:
            _, grid, board = self.look()
            if board is not None and board == prev and unknown_count(board) == 0:
                return grid, board
            if time.time() > deadline:
                return grid, board
            prev = board
            time.sleep(self.settle)

    MAX_STALLS = 10     # intentos seguidos sin que el tablero cambie

    def tap_points(self, img) -> list[tuple[int, int]]:
        """Puntos para cerrar la pantalla de "!Nuevos objetos!", en orden:
        primero encima del propio aviso (que suele cerrarse al tocarlo) y
        luego fuera, por si hace falta pulsar al lado.

        Nunca la esquina superior DERECHA: ahi esta la X que cierra el
        Roaming Test entero."""
        g = self.grid or self.last_grid
        if g:
            centro = (int(g.x0 + (g.cols - 1) / 2 * g.dx),
                      int(g.y0 + (g.rows - 1) / 2 * g.dy))
            izq = int(g.x0 - 0.45 * g.dx)
            arr = int(g.y0 - 0.60 * g.dy)
            aba = int(g.y0 + (g.rows - 1 + 0.60) * g.dy)
            return [centro, (izq, arr), (izq, aba)]
        h, w = img.shape[:2]
        return [(int(w * 0.59), int(h * 0.52)),
                (int(w * 0.37), int(h * 0.17)),
                (int(w * 0.37), int(h * 0.88))]

    def board_ready(self, board) -> bool:
        return board is not None and unknown_count(board) <= 2

    MAX_RONDAS = 3      # cada ronda pulsa Start una vez (y gasta un ticket)

    def _wait_board(self, seconds: float) -> bool:
        """Espera a que aparezca un tablero jugable."""
        deadline = time.time() + seconds
        while time.time() < deadline and not self.parado():
            self.grid = None
            _, _, board = self.look()
            if self.board_ready(board):
                return True
            time.sleep(0.8)
        return False

    def ensure_board(self) -> bool:
        """Deja el juego con un tablero jugable: cierra la pantalla de
        recompensa y empieza la siguiente partida. Se prueban varios puntos
        porque la recompensa tapa el centro. No se toca el boton naranja:
        durante la partida es Restart y tiraria la partida y un ticket."""
        self.grid = None
        self._set(estado="reiniciando")
        for ronda in range(1, self.MAX_RONDAS + 1):
            if self.parado():
                return False
            img, _, board = self.look()
            if self.board_ready(board):
                return True

            # 1) cerrar el aviso de "!Nuevos objetos!" (hacen falta 1 o 2 toques)
            for punto in self.tap_points(img):
                if self.parado():
                    return False
                self.ctrl.tap(punto)
                time.sleep(1.3)
                self.grid = None
                _, _, board = self.look()
                if self.board_ready(board):
                    self.log("  Aviso cerrado y tablero de vuelta.")
                    return True

            # 2) pulsar Start y comprobar que vuelve el minijuego
            img, _, _ = self.look()
            btn = boton_start(img, self.last_grid)
            self.log(f"  Pulsando Start en {btn} (intento {ronda}/{self.MAX_RONDAS}).")
            self.ctrl.tap(btn)
            if self._wait_board(12.0):
                self.log("  Partida nueva en marcha.")
                return True
            self.log("  Start no ha devuelto el tablero; lo intento otra vez.")
        return False

    def play_game(self, dry=False) -> str:
        """Juega una partida. Devuelve 'completa', 'atascada' o 'sin_tablero'."""
        done, blocked, stalls = 0, set(), 0
        self._set(estado="jugando", mov=0)
        while done < self.max_moves:
            if self.parado():
                return "parada"
            grid, board = self.wait_stable()
            if not self.board_ready(board):
                return "sin_tablero" if done == 0 else "completa"

            moves = [(s, m) for s, m in ranked_moves(board) if m not in blocked]
            if dry:
                print(board_str(board))
                if moves:
                    s, m = moves[0]
                    print(f"{self.tag}Mejor movimiento: {m[0]} <-> {m[1]}  (valor {s:.1f})")
                    print(f"{self.tag}Pixeles: {grid.center(*m[0])} -> {grid.center(*m[1])}")
                else:
                    print(f"{self.tag}Sin movimientos posibles.")
                return "completa"

            if not moves:
                stalls += 1
                if stalls >= self.MAX_STALLS:
                    return "atascada"
                blocked.clear()
                time.sleep(1.5)
                continue

            score, move = moves[0]
            self.ctrl.drag(grid.center(*move[0]), grid.center(*move[1]))
            time.sleep(self.settle)

            # si el tablero no cambia, el movimiento no vale: probar otro
            _, _, after = self.look()
            if after == board:
                blocked.add(move)
                stalls += 1
                if stalls >= self.MAX_STALLS:
                    return "atascada"
                continue

            done, stalls = done + 1, 0
            blocked.clear()
            self._set(mov=done)
            self.log(f"  {done}/{self.max_moves}: {move[0]} <-> {move[1]} "
                     f"(valor {score:.1f})")
        return "completa"

    def run(self, dry=False, games: int = 1):
        """games = numero de partidas; 0 = seguir hasta que no se pueda empezar."""
        limite = "sin limite" if games == 0 else f"{games}"
        self.log(f"Arrancando. Partidas: {limite}, {self.max_moves} movimientos "
                 f"cada una. Ctrl+C para parar.")
        jugadas, atascadas = 0, 0
        self._set(estado="arrancando", partidas=games, movs=self.max_moves)
        while (games == 0 or jugadas < games) and not self.parado():
            img, grid, board = self.look()
            if not self.board_ready(board):
                if jugadas and not dry:
                    self.log("Partida terminada; cierro el resultado y empiezo otra.")
                if not self.ensure_board():
                    if self.parado():
                        self._set(estado="parado")
                        return
                    if jugadas:
                        self.log(f"No he podido empezar otra partida. Puede que se "
                                 f"hayan acabado los tickets. Partidas jugadas: {jugadas}.")
                        self._set(estado="sin tickets")
                    else:
                        self.log("No veo el tablero ni el boton Start. Abre el "
                                 "Roaming Test en BlueStacks.")
                        self._set(estado="sin tablero")
                    return
                grid = self.grid

            jugadas += 1
            self._set(partida=jugadas)
            self.log(f"--- Partida {jugadas}"
                     f"{'' if games == 0 else f' de {games}'} "
                     f"(tablero {grid.rows}x{grid.cols}) ---")
            estado = self.play_game(dry=dry)
            if dry:
                return
            if estado == "atascada":
                atascadas += 1
                self.log("La partida se ha atascado: ningun movimiento hace efecto.")
                if atascadas >= 2:
                    self.log("Dos partidas atascadas seguidas; lo dejo. Comprueba si "
                             "el tablero sigue en pantalla al acabar, y si pasa, "
                             "mandame una captura de esa pantalla.")
                    self._set(estado="atascado")
                    return
                # el tablero puede haberse quedado puesto: forzar el cierre
                if not self.ensure_board():
                    self.log(f"No he podido continuar. Partidas jugadas: {jugadas}.")
                    return
            else:
                atascadas = 0
            # dejar que salga la pantalla de resultado antes de la siguiente vuelta
            time.sleep(2.0)
        if self.parado():
            self.log(f"Detenido. Partidas jugadas: {jugadas}.")
            self._set(estado="parado")
        else:
            self.log(f"Hecho: {jugadas} partidas jugadas en esta instancia.")
            self._set(estado="terminado")
