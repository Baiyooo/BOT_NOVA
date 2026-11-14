"""Lee en el juego la lista de eventos (con su cuenta atras) y, una sola vez
por evento, sus misiones. Solo lectura: los unicos toques son abrir la lista,
abrir un evento por su nombre, el boton de misiones del evento y la X para
salir. Nunca pulsa Recoger, Comprar, Ir a, Bot estelar ni nada parecido."""
from __future__ import annotations

import difflib
import os
import re
import time

import cv2

from vision import ocr
from tareas.eventos import RecogerEventos
from cerebro.memoria_eventos import (Memoria, clave, nombre_tarjeta, progreso, segundos,
                                     sin_acentos, subtitulos_de, SIN_MISIONES)
from nucleo.rutas import carpeta_diag, podar

ESTADOS = ("abierto", "activo", "proximamente", "finalizado", "terminado", "cerrado")
# Botones que llevan a la lista de misiones de un evento (lo unico que se toca dentro)
BOTON_MISIONES = ("misiones del evento", "misiones de evento", "mision del evento",
                  "event missions", "event mission", "misiones del", "misiones")
# Palabras que delatan una fila de mision (para no confundirla con recompensas)
VERBOS = ("elimin", "destru", "mata", "derrot", "kill", "destroy", "constru", "build",
          "gast", "spend", "abre", "abrir", "open", "explor", "acelera", "speed",
          "produc", "fabric", "complet", "usa ", "use ", "actualiz", "upgrade",
          "simulac", "destacamento", "recolect", "collect", "invoca", "consigue",
          "obten", "alcanza", "reach", "pirat", "ballena", "whale", "gec", "caja")
NO_MISION = ("recoger", "ir a", "en progreso", "completado", "reclamar", "claim", "go",
             "lista de eventos", "edit pin", "recompensa", "puntos actuales")


# ----------------------------------------------------- analisis (puro) --
def es_tiempo(t: str) -> bool:
    t = sin_acentos(t)
    return bool(re.search(r"\d+\s*d?\s*\d{1,2}:\d{2}", t)) or \
        bool(re.fullmatch(r"(\d+\s*[dhm]\s*)+", t))


def tarjetas(items, ancho=1600) -> list[dict]:
    """Del OCR de LISTA DE EVENTOS saca las tarjetas: nombre, subtitulo,
    estado y tiempo. Cada tarjeta tiene el tiempo a la derecha (debajo del
    estado) y el nombre grande en el centro, a su misma altura."""
    k = ancho / 1600.0
    tiempos = [d for d in items if es_tiempo(d["texto"]) and d["centro"][0] > 1150 * k]
    textos = [d for d in items if not es_tiempo(d["texto"])
              and 600 * k < d["centro"][0] < 1290 * k and len(d["texto"]) >= 3
              and not any(e in sin_acentos(d["texto"]) for e in ("lista de eventos", "edit pin"))]
    out = []
    for t in tiempos:
        ty = t["centro"][1]
        cerca = [d for d in textos if -95 * k <= d["centro"][1] - ty <= 70 * k]
        if not cerca:
            continue
        nombre = min(cerca, key=lambda d: (d["centro"][1], -d["caja"][3]))
        resto = [d for d in cerca if d is not nombre and d["centro"][1] > nombre["centro"][1]]
        estado = next((d["texto"] for d in items
                       if d["centro"][0] > 1150 * k and -70 * k < d["centro"][1] - ty < 0
                       and any(e in sin_acentos(d["texto"]) for e in ESTADOS)), "")
        out.append({"nombre": nombre["texto"], "subtitulo": resto[0]["texto"] if resto else "",
                    "estado": estado.rstrip(":"), "tiempo": t["texto"],
                    "centro": nombre["centro"]})
    return out


def filas(items, tol=22) -> list[list[dict]]:
    """Agrupa el OCR en filas por altura."""
    out = []
    for d in sorted(items, key=lambda d: d["centro"][1]):
        if out and abs(d["centro"][1] - out[-1][-1]["centro"][1]) <= tol:
            out[-1].append(d)
        else:
            out.append([d])
    return out


RECOMPENSA = re.compile(r"^[x×]\s*\d+[\d.,]*[km]?$")
NO_TEXTO = ("recoger", "recogido", "ir a", "en progreso", "completado", "reclamar", "claim",
            "tiempo de reinicio", "completa misiones del evento", "obtener objetos del evento",
            "event missions", "misiones", "eventos", "activo", "alianza")


BOTONES_ESTADO = {"recogido": "hecha", "recoger": "hecha", "completado": "hecha",
                  "reclamar": "hecha", "claim": "hecha", "claimed": "hecha",
                  "ir a": "pendiente", "en progreso": "pendiente", "go": "pendiente"}


def _estado_boton(texto):
    t = ocr.normal(texto)
    for k, v in BOTONES_ESTADO.items():
        if t == k or (len(k) > 4 and ocr.coincide(t, k) and len(t) <= len(k) + 3):
            return v
    return None


def misiones(items, alto=900, ancho=1600) -> list[dict]:
    """Del OCR de una pantalla de misiones saca [{"texto", "progreso",
    "hecha"}]. Cada tarjeta lleva a la derecha un boton (Ir a / Recoger /
    Recogido / En progreso): las tarjetas se delimitan por esos botones, y
    dentro de cada una se juntan las lineas de la descripcion y su
    "actual / meta". Recoger o Recogido = mision hecha."""
    k = alto / 900.0
    textos, progs, botones = [], [], []
    for d in items:
        t = sin_acentos(d["texto"])
        cx, cy = d["centro"]
        p = progreso(d["texto"])
        if p and cx > ancho * 0.55:
            progs.append((cy, p))
            continue
        if cx > ancho * 0.62:
            e = _estado_boton(d["texto"])
            if e:
                botones.append((cy, e))
            continue
        if len(t) < 2 or RECOMPENSA.match(t.replace(" ", "")):
            continue
        if any(t == n or t.startswith(n) and len(t) <= len(n) + 3 for n in NO_TEXTO) or "alianza" in t:
            continue
        textos.append(d)
    if not textos:
        return []
    bordes = {}
    for d in textos:
        bk = int(d["caja"][0] // (20 * k))
        bordes[bk] = bordes.get(bk, 0) + 1
    col = max(bordes, key=bordes.get) * 20 * k
    textos = [d for d in textos if abs(d["caja"][0] - col) <= 45 * k]
    textos.sort(key=lambda d: d["caja"][1])
    out = []
    if len(botones) >= 1:
        botones.sort()
        alto_tarjeta = (botones[1][0] - botones[0][0]) if len(botones) > 1 else 150 * k
        for i, (by, estado) in enumerate(botones):
            y0 = (botones[i - 1][0] + by) / 2 if i else by - alto_tarjeta / 2
            y1 = (by + botones[i + 1][0]) / 2 if i + 1 < len(botones) else by + alto_tarjeta / 2
            lineas = [d["texto"] for d in textos if y0 <= d["centro"][1] < y1]
            texto = re.sub(r"\s+", " ", " ".join(lineas)).strip()
            if len(sin_acentos(texto)) < 8:
                continue
            prog = next((p for y, p in progs if y0 <= y < y1), None)
            out.append({"texto": texto, "progreso": prog, "hecha": estado == "hecha"})
        return out
    # sin botones a la vista: por cercania vertical de las lineas
    bloques = []
    for d in textos:
        y0, y1 = d["caja"][1], d["caja"][1] + d["caja"][3]
        if bloques and y0 - bloques[-1]["y1"] <= 16 * k:
            bloques[-1]["lineas"].append(d["texto"])
            bloques[-1]["y1"] = max(bloques[-1]["y1"], y1)
        else:
            bloques.append({"y0": y0, "y1": y1, "lineas": [d["texto"]]})
    for i, bl in enumerate(bloques):
        texto = re.sub(r"\s+", " ", " ".join(bl["lineas"])).strip()
        if len(sin_acentos(texto)) < 8:
            continue
        fin = bloques[i + 1]["y0"] if i + 1 < len(bloques) else bl["y0"] + 170 * k
        prog = next((p for y, p in sorted(progs) if bl["y0"] - 10 * k <= y < fin), None)
        out.append({"texto": texto, "progreso": prog, "hecha": False})
    return out


def boton_misiones(items):
    """El texto-boton que abre las misiones del evento (o None). Nunca
    "Bote estelar", "Mejorar bote" ni nada parecido."""
    for d in items:
        t = ocr.normal(d["texto"])
        if len(t) > 26 or "bote" in t:
            continue
        if ocr.coincide(t, "misiones del evento") or ocr.coincide(t, "event missions") \
                or t.startswith("misiones del") or t.startswith("mision del") \
                or t in ("misiones", "event mission", "misiones de evento"):
            return d
    return None


def parecida(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, sin_acentos(a), sin_acentos(b)).ratio()


# ------------------------------------------------------------ en el juego --
class LectorEventos(RecogerEventos):
    """Lee eventos y misiones con OCR. Hereda de RecogerEventos solo la forma
    de abrir la lista y de salir con la X."""

    NOMBRE = "Lectura de eventos"
    MAX_SCROLL = 6

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.mem = Memoria(getattr(ctrl, "name", "inst"))
        self.status = {"estado": "en espera", "eventos": 0, "leidos": 0}

    def _guardar_muestra(self, img, nombre):
        """Captura para revisar luego como son las pantallas de misiones."""
        try:
            d = os.path.join(os.path.dirname(carpeta_diag()), "misiones_capturas")
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, f"{time.strftime('%Y%m%d_%H%M%S')}_{clave(nombre)}.png"), img)
            podar(d, 300)                                  # solo las 300 mas recientes
        except Exception:                                      # noqa: BLE001
            pass

    def _ocr(self, etiqueta, escala=None):
        img = self.cap(etiqueta)
        items = ocr.leer(img, escala=escala)
        if escala and escala > 1.4:
            # el "actual / meta" se lee mejor a tamaño normal: se añade aparte
            w = img.shape[1]
            items += [d for d in ocr.leer(img, zona=(0.55, 0.1, 1, 1), escala=1.0)
                      if progreso(d["texto"]) and d["centro"][0] > w * 0.55]
        return img, items

    def _lista_abierta(self, items) -> bool:
        t = " ".join(sin_acentos(d["texto"]) for d in items)
        return "lista de eventos" in t or ("edit pin" in t and any(e in t for e in ESTADOS))

    def _arrastrar(self, img, abajo=True):
        h, w = img.shape[:2]
        y0, y1 = (0.78, 0.38) if abajo else (0.38, 0.78)
        self.ctrl.drag((int(w * 0.62), int(h * y0)), (int(w * 0.62), int(h * y1)))
        time.sleep(1.3)

    def leer_lista(self) -> list[dict]:
        """Abre LISTA DE EVENTOS y la recorre entera. Deja la lista arriba."""
        if not self._abrir_lista():
            self.log("  No se ha abierto la lista de eventos.")
            return []
        vistas, todas = set(), []
        img = None
        for _ in range(self.MAX_SCROLL + 1):
            if self.parado():
                break
            img, items = self._ocr("lista_ocr")
            nuevas = 0
            for t in tarjetas(items, img.shape[1]):
                k = clave(t["nombre"])
                if k not in vistas:
                    vistas.add(k)
                    todas.append(t)
                    nuevas += 1
            if nuevas == 0 and todas:
                break
            self._arrastrar(img, abajo=True)
        for _ in range(self.MAX_SCROLL):               # volver arriba
            if img is None or self.parado():
                break
            self._arrastrar(img, abajo=False)
        return todas

    def _abrir_evento(self, nombre):
        """Busca la tarjeta por su nombre (bajando la lista) y la abre."""
        for _ in range(self.MAX_SCROLL + 1):
            if self.parado():
                return None
            img, items = self._ocr("busco_evento")
            if not self._lista_abierta(items):
                if not self._abrir_lista():
                    return None
                continue
            for t in tarjetas(items, img.shape[1]):
                if parecida(t["nombre"], nombre) >= 0.8 or nombre_tarjeta(t, [nombre]) == nombre:
                    self.ctrl.tap(t["centro"])
                    time.sleep(3.0)
                    img2, items2 = self._ocr("evento_ocr")
                    return None if self._lista_abierta(items2) else (img2, items2)
            self._arrastrar(img, abajo=True)
        return None

    def _leer_misiones_abiertas(self, nombre, img, items):
        """Dentro del evento: abre sus misiones (si tiene boton) y las lee
        bajando la lista. Devuelve [{"texto", "progreso"}]."""
        b = boton_misiones(items)
        if b is not None:
            self.log(f"  Abro «{b['texto']}».")
            self.ctrl.tap(b["centro"])
            time.sleep(2.5)
            img, items = self._ocr("misiones_ocr", escala=1.6)
        else:
            img, items = self._ocr("misiones_ocr", escala=1.6)
        self._guardar_muestra(img, nombre)
        todas, firmas = [], set()
        for _ in range(4):
            firma = " ".join(sin_acentos(d["texto"]) for d in items)
            if firma in firmas:
                break
            firmas.add(firma)
            for m in misiones(items, img.shape[0], img.shape[1]):
                a = sin_acentos(m["texto"])
                igual = None
                for x in todas:
                    b = sin_acentos(x["texto"])
                    if parecida(a, b) > 0.9 or a.startswith(b) or b.startswith(a):
                        igual = x
                        break
                if igual is None:
                    todas.append(m)
                elif len(m["texto"]) > len(igual["texto"]):      # la tarjeta entera
                    igual.update(texto=m["texto"], progreso=m["progreso"] or igual["progreso"],
                                 hecha=m.get("hecha") or igual.get("hecha"))
                elif m["progreso"] and not igual["progreso"]:
                    igual["progreso"] = m["progreso"]
            if self.parado():
                break
            self._arrastrar(img, abajo=True)
            img, items = self._ocr("misiones_ocr", escala=1.6)
        return todas

    def _apuntar(self, k, leidas):
        """Guarda el progreso leido de cada mision (busca la mision guardada
        mas parecida)."""
        guardadas = (self.mem.eventos().get(k) or {}).get("misiones") or []
        for m in leidas:
            if not m["progreso"] and not m.get("hecha"):
                continue
            mejor = max(guardadas, key=lambda g: parecida(g["texto"], m["texto"]), default=None)
            if mejor and parecida(mejor["texto"], m["texto"]) >= 0.75:
                actual, meta = m["progreso"] or (None, None)
                self.mem.apuntar_progreso(k, mejor["id"], actual, meta, hecha=m.get("hecha"))

    def leer_evento(self, k, nombre, guardar_requisitos=True, mostrar=None) -> bool:
        """nombre: como se ve en pantalla (para encontrar la tarjeta);
        mostrar: el nombre bueno, para el registro."""
        r = self._abrir_evento(nombre)
        nombre = mostrar or nombre
        if r is None:
            self.log(f"  No he podido abrir «{nombre}».")
            return False
        try:
            leidas = self._leer_misiones_abiertas(nombre, *r)
        finally:
            self._salir_a_lista()
        if guardar_requisitos:
            ms = self.mem.guardar_misiones(k, [m["texto"] for m in leidas])
            bot = sum(1 for m in ms if m["accion"] == "bot")
            self.log(f"  «{nombre}»: {len(ms)} misión(es), {bot} las hace el bot.")
        self._apuntar(k, leidas)
        self.mem.apuntar_lectura(k)
        return True

    def _salir_a_lista(self):
        for _ in range(4):
            img, items = self._ocr("salir_evento")
            if self._lista_abierta(items) or self._fuera(img):
                return
            x = self._boton_cerrar(img)
            if x is None:
                return
            self.ctrl.tap(x)
            time.sleep(1.8)

    # ------------------------------------------------------------- tareas --
    #  al empezar, como mucho se mira el progreso de estos eventos (no tardar mucho)
    MAX_PROGRESO_INICIO = 6
    #  no se vuelve a mirar el progreso de un evento si se miro hace menos de esto
    PROGRESO_RECIENTE = 30 * 60

    def run(self, ciclos: int = 1, solo: str | None = None, progreso_cuenta: bool = False):
        """Lee la lista; lee las misiones de los eventos nuevos (una vez) y,
        si se pide 'solo', vuelve a leer el progreso de ese evento. Con
        progreso_cuenta (al empezar la Rutina), mira tambien el progreso DE
        ESTA CUENTA en los eventos con misiones del bot."""
        if not ocr.disponible():
            self.log("Lectura de eventos: falta el lector de texto (RapidOCR). "
                     "Abre BOT.bat (lo instala).")
            self.status["estado"] = "sin_ocr"
            return
        self.status["estado"] = "leyendo la lista de eventos"
        if not self.ir_a_base():
            self.log("No encuentro la base para abrir los eventos.")
            return
        lista = self.leer_lista()
        if not lista:
            self._salir()
            return
        self.mem.actualizar_lista(lista)
        # el nombre bueno de cada tarjeta (el OCR lee a veces «-tefactos» o
        # la cabecera «EVENTOS»); para abrirla se sigue buscando lo que se ve
        ev = self.mem.eventos()
        sabidos, subs = [e.get("nombre") for e in ev.values()], subtitulos_de(ev)
        for t in lista:
            t["pantalla"] = t["nombre"]
            t["nombre"] = nombre_tarjeta(t, sabidos, subs) or ""
        lista = [t for t in lista if t["nombre"]]
        self.status["eventos"] = len(lista)
        self.log("Eventos: " + ", ".join(f"{t['nombre']} ({t['tiempo']})" for t in lista))
        for t in lista:
            if self.parado():
                break
            k = clave(t["nombre"])
            if k in SIN_MISIONES:
                continue
            if self.mem.necesita_leer(k):
                self.status["estado"] = f"leyendo misiones de {t['nombre']}"
                self.log(f"  Evento nuevo: leo las misiones de «{t['nombre']}».")
                self.mem.marcar_leyendo(k)
                if self.leer_evento(k, t["pantalla"], mostrar=t["nombre"]):
                    self.status["leidos"] += 1
            elif solo and k == solo:
                self.status["estado"] = f"progreso de {t['nombre']}"
                self.leer_evento(k, t["pantalla"], guardar_requisitos=False, mostrar=t["nombre"])
        if progreso_cuenta and not self.parado():
            con_bot = set(self.mem.con_misiones_del_bot())
            vistos = 0
            for t in lista:
                k = clave(t["nombre"])
                if self.parado() or vistos >= self.MAX_PROGRESO_INICIO:
                    break
                if k not in con_bot or time.time() - self.mem.leido_t(k) < self.PROGRESO_RECIENTE:
                    continue
                self.status["estado"] = f"progreso de {t['nombre']}"
                self.log(f"  Miro cómo va esta cuenta en «{t['nombre']}».")
                if self.leer_evento(k, t["pantalla"], guardar_requisitos=False, mostrar=t["nombre"]):
                    vistos += 1
        self._salir()
        self.volver_a_base()
        self.status["estado"] = "terminado"

    def progreso_de(self, k: str):
        """Solo vuelve a leer el progreso de un evento ya conocido."""
        ev = self.mem.eventos().get(k)
        if not ev or not ocr.disponible():
            return
        if not self.ir_a_base() or not self._abrir_lista():
            return
        self.leer_evento(k, ev.get("nombre", k), guardar_requisitos=False)
        self._salir()
        self.volver_a_base()


def segundos_fin(t) -> int | None:            # atajo para pruebas
    return segundos(t)
