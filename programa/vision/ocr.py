"""Lectura de texto de la pantalla, en el propio PC (sin enviar nada fuera).

Usa RapidOCR: el paquete nuevo "rapidocr" o el antiguo "rapidocr_onnxruntime"
(el que instala BOT.bat). Si no hay ninguno, disponible() es False y las
partes del bot que leen texto se saltan sin romper nada.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

_MOTOR = None
_TIPO = None
_CERROJO = threading.Lock()          # solo protege la carga de motores
# Turnos simultaneos de OCR (en todo el PC): con 8 o mas nucleos caben 2
# lecturas a la vez (1 hilo cada una) sin ahogar el PC; con menos, de una en una.
TURNOS = 2 if (os.cpu_count() or 4) >= 8 else 1
_MOTORES: list = []                  # un motor por turno (se crean al usarlos)
_LIBRES: list[int] = list(range(TURNOS))
_COND = threading.Condition()
_CACHE: dict = {}                    # clave -> (instante, resultado)
_CACHE_S = 1.0


def _cargar(idx: int = 0):
    """Motor del turno idx (se crea la primera vez). None si no hay RapidOCR."""
    with _CERROJO:
        if _TIPO == "ninguno":
            return None
        while len(_MOTORES) <= idx:
            _MOTORES.append(_crear())
            if _TIPO == "ninguno":
                _MOTORES.clear()
                return None
        return _MOTORES[idx]


def _crear():
    global _MOTOR, _TIPO
    # Pocos hilos: con varias cuentas a la vez, el OCR con todos los nucleos
    # llego a dejar el PC sin responder (5 nov, 01:01).
    try:
        from rapidocr import RapidOCR                      # version 2.x / 3.x
        try:
            _MOTOR = RapidOCR(params={
                "EngineConfig.onnxruntime.intra_op_num_threads": HILOS,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                "Global.log_level": "error"})
        except Exception:                                  # noqa: BLE001
            _MOTOR = RapidOCR()
        _TIPO = "nuevo"
    except Exception:                                      # noqa: BLE001
        try:
            from rapidocr_onnxruntime import RapidOCR      # version 1.x
            try:
                _MOTOR = RapidOCR(intra_op_num_threads=HILOS, inter_op_num_threads=1)
            except Exception:                              # noqa: BLE001
                _MOTOR = RapidOCR()
            _TIPO = "viejo"
        except Exception:                                  # noqa: BLE001
            _MOTOR, _TIPO = None, "ninguno"
    return _MOTOR


HILOS = 1


class _TurnoPC:
    """Cerrojo entre procesos (un archivo por turno): solo TURNOS cuentas leen
    texto a la vez, para no ahogar el PC. Si alguien lo deja colgado, caduca en 20 s."""

    def __init__(self, turno: int = 0):
        from nucleo.rutas import carpeta_datos
        base = carpeta_datos()
        # un archivo por turno del PC (ocr.lock, ocr1.lock...): se coge el primero libre
        self.rutas = [os.path.join(base, "ocr.lock" if i == 0 else f"ocr{i}.lock")
                      for i in range(TURNOS)]
        self.ruta = None
        self.fd = None

    def __enter__(self):
        fin = time.time() + 25
        while time.time() < fin:
            for ruta in self.rutas:
                try:
                    self.fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    self.ruta = ruta
                    return self
                except FileExistsError:
                    try:
                        if time.time() - os.path.getmtime(ruta) > 20:
                            os.remove(ruta)
                    except OSError:
                        pass
                except OSError:
                    return self                  # carpeta no disponible: sin cerrojo
            time.sleep(0.05)
        return self

    def __exit__(self, *a):
        if self.fd is not None:
            try:
                os.close(self.fd)
                os.remove(self.ruta)                    # ruta: el turno que cogio
            except OSError:
                pass


def disponible() -> bool:
    return _cargar(0) is not None


def _clave(img, zona, escala, sin_giro):
    return (hashlib.blake2b(img.tobytes(), digest_size=12).digest(), img.shape,
            zona, escala, sin_giro)


def leer(img, zona=None, escala: float | None = None, sin_giro: bool = False) -> list[dict]:
    """Textos de la imagen (BGR). zona = (x0, y0, x1, y1) en fracciones.
    Devuelve [{"texto", "caja": (x, y, w, h), "centro": (x, y), "p"}] en
    coordenadas de la imagen completa, de arriba abajo.
    sin_giro: no dejar que el lector de la vuelta a los textos que cree
    girados (con las cifras cortas de las etiquetas del mapa acierta mas:
    «35.500» en vez de «DOS'SE»)."""
    if img is None:
        return []
    # Misma imagen y mismos parametros en menos de 1 s: se reutiliza el resultado
    # (varias comprobaciones seguidas sobre la misma captura).
    try:
        clave = _clave(img, tuple(zona) if zona else None, escala, sin_giro)
    except Exception:                                      # noqa: BLE001
        clave = None
    ahora = time.time()
    if clave is not None:
        hit = _CACHE.get(clave)
        if hit and ahora - hit[0] < _CACHE_S:
            return [dict(d) for d in hit[1]]
    res = _leer(img, zona, escala, sin_giro)
    if clave is not None:
        for k in [k for k, v in list(_CACHE.items()) if ahora - v[0] >= _CACHE_S]:
            _CACHE.pop(k, None)
        _CACHE[clave] = (time.time(), [dict(d) for d in res])
    return res


def _leer(img, zona, escala, sin_giro) -> list[dict]:
    h, w = img.shape[:2]
    ox = oy = 0
    if zona:
        x0, y0, x1, y1 = (int(zona[0] * w), int(zona[1] * h), int(zona[2] * w), int(zona[3] * h))
        img, ox, oy = img[y0:y1, x0:x1], x0, y0
    if escala is None:
        # ampliar siempre un poco; los trozos pequeños, mas (la letra del juego
        # es estilizada y a tamaño real se pegan palabras y se confunden cifras)
        escala = 2.0 if img.shape[1] < 700 else 1.4
    if escala and escala != 1.0:
        # ampliar ayuda con la letra pequena y estilizada del juego
        import cv2
        img = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
    else:
        escala = 1.0
    with _COND:                          # turno de este proceso (un motor por turno)
        while not _LIBRES:
            _COND.wait()
        idx = _LIBRES.pop(0)
    try:
        motor = _cargar(idx)
        if motor is None:
            return []
        try:
            with _TurnoPC(idx):
                try:
                    r = motor(img, use_cls=False) if sin_giro else motor(img)
                except TypeError:
                    r = motor(img)
        except Exception:                                  # noqa: BLE001
            return []
    finally:
        with _COND:
            _LIBRES.append(idx)
            _COND.notify()
    filas = []
    if _TIPO == "nuevo":
        if r is None or getattr(r, "txts", None) is None:
            return []
        filas = list(zip(r.boxes, r.txts, r.scores, strict=False))
    else:
        res = r[0] if isinstance(r, tuple) else r
        filas = [(b, t, s) for b, t, s in (res or [])]
    out = []
    for caja, texto, p in filas:
        xs = [float(q[0]) / escala for q in caja]
        ys = [float(q[1]) / escala for q in caja]
        x, y = int(min(xs)) + ox, int(min(ys)) + oy
        cw, ch = int(max(xs) - min(xs)), int(max(ys) - min(ys))
        out.append({"texto": limpiar(texto), "caja": (x, y, cw, ch),
                    "centro": (x + cw // 2, y + ch // 2), "p": float(p)})
    out.sort(key=lambda d: (d["caja"][1], d["caja"][0]))
    return out


def texto(img, zona=None, escala=None) -> str:
    return " ".join(d["texto"] for d in leer(img, zona, escala))


# ---------------------------------------------------------------- comparar --
def limpiar(t) -> str:
    """Corrige las confusiones tipicas de la letra del juego."""
    import re
    t = str(t or "").strip()
    t = t.replace("／", "/").replace("⁄", "/").replace("∕", "/").replace("：", ":")
    t = t.replace("Ø", "0").replace("ø", "0")
    # O/o entre cifras o pegada a ellas = 0 ("1o0" -> "100", "2.OO0" -> "2.000")
    for _ in range(3):
        t = re.sub(r"(?<=[\d.,])[oO](?=[\d.,oO]|\b)", "0", t)
        t = re.sub(r"(?<=\b)[oO](?=[\d.,])", "0", t)
    return t


def normal(t) -> str:
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9/:.]+", " ", t).strip()


def coincide(texto, frase, umbral: float = 0.82) -> bool:
    """¿Aparece 'frase' en 'texto'? Sin acentos, sin espacios y aceptando
    alguna letra mal leida. Las palabras cortas (<= 4 letras, p. ej. "No",
    "OK", "Base") tienen que coincidir enteras, para no pulsar lo que no es."""
    import difflib
    a, b = normal(texto), normal(frase)
    if not a or not b:
        return False
    if len(b.replace(" ", "")) <= 4:
        return b in a.split() or a == b
    a2, b2 = a.replace(" ", ""), b.replace(" ", "")
    if b2 in a2:
        return True
    if len(a2) < len(b2) * 0.8:
        return difflib.SequenceMatcher(None, a2, b2).ratio() >= umbral
    n = len(b2)
    for i in range(0, max(1, len(a2) - n + 1)):
        if difflib.SequenceMatcher(None, a2[i:i + n], b2).ratio() >= umbral:
            return True
    return False


def buscar(items, *frases, zona=None, w=1600, h=900, umbral: float = 0.82):
    """El primer texto leido que coincide con alguna frase (en orden de
    frases), opcionalmente dentro de una zona (fracciones de la pantalla)."""
    for fr in frases:
        for d in items:
            if zona:
                x, y = d["centro"]
                if not (zona[0] * w <= x <= zona[2] * w and zona[1] * h <= y <= zona[3] * h):
                    continue
            if coincide(d["texto"], fr, umbral):
                return d
    return None
