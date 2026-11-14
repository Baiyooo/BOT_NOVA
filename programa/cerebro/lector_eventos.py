"""Lee en el juego la lista de eventos (con su cuenta atras) y, una sola vez
por evento, sus misiones. Los unicos toques son abrir la lista, abrir un
evento por su nombre, el boton de misiones del evento, la X para salir y,
al mirar las misiones, los botones verdes «Recoger» de las misiones ya
cumplidas (dan la recompensa; no gastan nada). Nunca pulsa Comprar, Ir a,
Bot estelar ni nada parecido."""
from __future__ import annotations

import difflib
import os
import re
import time

import cv2

from vision import ocr
from tareas.eventos import RecogerEventos
from cerebro import textos_mision as tm
from cerebro.memoria_eventos import (Memoria, clasificar, clave, nombre_tarjeta, progreso,
                                     segundos, sin_acentos, subtitulos_de, ignorado,
                                     SIN_MISIONES)
from nucleo.rutas import carpeta_diag, podar
from vision.plantillas import localizar, localizar_todos

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
    # la columna donde empiezan los textos de las tarjetas: la x con mas
    # textos cerca (sin contar la cabecera ni el pie de la pantalla)
    cuerpo = [d for d in textos if alto * 0.17 < d["centro"][1] < alto * 0.86] or textos
    col = max((d["caja"][0] for d in cuerpo),
              key=lambda x: sum(1 for e in cuerpo if abs(e["caja"][0] - x) <= 20 * k))
    textos = [d for d in textos if abs(d["caja"][0] - col) <= 45 * k]
    textos.sort(key=lambda d: d["caja"][1])
    out = []
    # cuando el lector no lee bien los botones («Ir a» sale «eJI», o una
    # pestaña de arriba parece un boton) pero cada tarjeta lleva su
    # «Progreso: x / y» debajo, las tarjetas se separan por esa linea
    progs.sort()
    if len(progs) >= 2 and len(progs) > len([b for b in botones if b[0] > alto * 0.2]):
        previo = 0.0
        for py, p in progs:
            lineas = [d["texto"] for d in textos
                      if previo < d["centro"][1] <= py + 12 * k and d["centro"][1] > alto * 0.18]
            texto = re.sub(r"\s+", " ", " ".join(lineas)).strip()
            hecha = any(e == "hecha" for by, e in botones if previo < by <= py + 12 * k
                        and by > alto * 0.2)
            if len(sin_acentos(texto)) >= 8:
                out.append({"texto": texto, "progreso": p, "hecha": hecha or p[0] >= p[1]})
            previo = py + 12 * k
        return out
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
    """El texto-boton que abre las misiones del evento (o None): «Misiones
    del evento», «Mision de Cosmomante» o, en Artefactos, «Añadir potencia».
    Nunca "Bote estelar", "Mejorar bote" ni nada parecido."""
    for d in items:
        t = ocr.normal(d["texto"])
        if len(t) > 26 or "bote" in t:
            continue
        if ocr.coincide(t, "misiones del evento") or ocr.coincide(t, "event missions") \
                or t.startswith("misiones del") or t.startswith("mision del") \
                or t in ("misiones", "event mission", "misiones de evento") \
                or ocr.coincide(t, "mision de cosmomante") or t in ("mision de", "misiones de")                 or ocr.coincide(t, "anadir potencia") or t.startswith("anadir pot"):   # Artefactos
            return d
    return None


def parecida(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, sin_acentos(a), sin_acentos(b)).ratio()


# ------------------------------------------------------------ en el juego --
class LectorEventos(RecogerEventos):
    """Lee eventos y misiones con OCR. Hereda de RecogerEventos solo la forma
    de abrir la lista y de salir con la X."""

    NOMBRE = "Lectura de eventos"
    MAX_SCROLL = 10

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.mem = Memoria(getattr(ctrl, "name", "inst"))
        self.status = {"estado": "en espera", "eventos": 0, "leidos": 0, "recogidas": 0}

    MAX_RECOGER = 12          # como mucho, botones Recoger por pantalla de misiones

    def _recoger_visibles(self, nombre) -> int:
        """Pulsa los botones verdes «Recoger» de la lista de misiones abierta
        (misiones cumplidas con la recompensa sin recoger), de arriba abajo.
        Un boton que no cambia nada al pulsarlo no se vuelve a pulsar."""
        n, agotados = 0, set()
        for _ in range(self.MAX_RECOGER):
            if self.parado():
                break
            img = self.cap("misiones_recoger")
            botones = [c for _, c in localizar_todos(img, "recoger_ev", self.U_RECOGER)
                       if (c[0] // 30, c[1] // 30) not in agotados]
            if not botones:
                break
            c = min(botones, key=lambda c: c[1])
            self.ctrl.tap(c)
            self._cerrar_aviso()                     # «¡Nuevos objetos!»
            if self._sin_cambio(img, self.cap("misiones_recoger"), c):
                agotados.add((c[0] // 30, c[1] // 30))
                continue
            n += 1
        if n:
            self.log(f"  «{nombre}»: {n} recompensa(s) de misiones recogida(s).")
            self.status["recogidas"] += n
        return n

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
        """Mueve la lista algo mas de una tarjeta, despacio: un arrastre rapido
        le da inercia y se salta tarjetas (Artefactos, Bingo Estelar...)."""
        h, w = img.shape[:2]
        y0, y1 = (0.72, 0.45) if abajo else (0.45, 0.72)
        ms = getattr(self.ctrl, "drag_ms", None)
        try:
            if ms is not None:
                self.ctrl.drag_ms = 900
            self.ctrl.drag((int(w * 0.62), int(h * y0)), (int(w * 0.62), int(h * y1)))
        finally:
            if ms is not None:
                self.ctrl.drag_ms = ms
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

    def _entrar_tarjeta(self, centro, nombre, segundos=12.0):
        """Toca la tarjeta y espera a que cargue el evento. Al entrar sale una
        animacion de rayas sin texto, y algunos eventos tardan en abrir: se
        espera a ver texto que no sea la lista. Si la lista sigue ahi pasados
        unos segundos, el toque no ha entrado: se vuelve a buscar la tarjeta
        por su nombre (la lista puede haberse movido) y se toca otra vez (una
        sola). Sin texto al acabar el tiempo no se da por abierto."""
        self.ctrl.tap(centro)
        time.sleep(2.0)
        fin, retocado, lista_desde = time.time() + segundos, False, None
        img2 = items2 = None
        while time.time() < fin and not self.parado():
            img2, items2 = self._ocr("evento_ocr")
            if self._lista_abierta(items2):
                lista_desde = lista_desde or time.time()
                if not retocado and time.time() - lista_desde >= 2.5:
                    retocado, lista_desde = True, None
                    t = next((t for t in tarjetas(items2, img2.shape[1])
                              if parecida(t["nombre"], nombre) >= 0.8
                              or nombre_tarjeta(t, [nombre]) == nombre), None)
                    if t is None:
                        return None                  # la tarjeta ya no esta a la vista
                    self.ctrl.tap(t["centro"])
            elif len([d for d in items2 if len(d["texto"].strip()) >= 3]) >= 3:
                return img2, items2                  # pantalla del evento con su texto
            time.sleep(1.0)
        return None

    def _abrir_evento(self, nombre):
        """Busca la tarjeta por su nombre y la abre. La lista recuerda donde se
        quedo: se busca bajando y, si se llega al final sin verla, subiendo."""
        from vision.detectores import _diferencia
        abajo, cambios = True, 0
        for _ in range(2 * self.MAX_SCROLL + 2):
            if self.parado():
                return None
            img, items = self._ocr("busco_evento")
            if not self._lista_abierta(items):
                if not self._abrir_lista():
                    return None
                continue
            for t in tarjetas(items, img.shape[1]):
                if parecida(t["nombre"], nombre) >= 0.8 or nombre_tarjeta(t, [nombre]) == nombre:
                    return self._entrar_tarjeta(t["centro"], nombre)
            self._arrastrar(img, abajo=abajo)
            if _diferencia(img, self.cap("busco_evento")) < 2.0:     # final de la lista
                cambios += 1
                if cambios >= 2:
                    break
                abajo = not abajo
        return None

    def _leer_misiones_abiertas(self, nombre, img, items):
        """Dentro del evento: abre sus misiones (si tiene boton) y las lee
        bajando la lista. Devuelve [{"texto", "progreso"}]."""
        # Artefactos: antes de nada, «Buscar» con el encendido que haya
        if self.buscar_artefactos(img, items):
            img, items = self._ocr("evento_ocr")
        # misiones que ya se conocen y no hace falta volver a mirar
        if getattr(self, "sin_misiones", False):
            return []
        b = boton_misiones(items)
        if b is None:
            # Cosmomante: el boton «Mision de Cosmomante» (copa) del tablero
            p, c, _ = localizar(img, "mision_cosmo")
            if p >= 0.85:
                b = {"texto": "Misión de Cosmomante", "centro": c}
        if b is not None:
            self.log(f"  Abro «{b['texto']}».")
            self.ctrl.tap(b["centro"])
            time.sleep(2.5)
            img, items = self._ocr("misiones_ocr", escala=1.6)
        else:
            img, items = self._ocr("misiones_ocr", escala=1.6)
        self._guardar_muestra(img, nombre)
        todas, firmas = [], set()
        relecturas = 0
        for _ in range(6):
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
            # recoger lo cumplido de esta pantalla y volver a mirarla (las
            # misiones recogidas pueden bajar al final de la lista)
            if self._recoger_visibles(nombre) and relecturas < 2:
                relecturas += 1
                img, items = self._ocr("misiones_ocr", escala=1.6)
                continue
            self._arrastrar(img, abajo=True)
            img, items = self._ocr("misiones_ocr", escala=1.6)
        return todas

    def _apuntar(self, k, leidas):
        """Guarda el progreso leido de cada mision (busca la mision guardada
        mas parecida)."""
        ev = self.mem.eventos().get(k) or {}
        guardadas = ev.get("misiones") or []
        # lo leido, puesto en limpio igual que lo guardado (una tarjeta leida
        # junto con otra se reparte: el progreso va a la que tiene esa meta)
        limpias, _ = tm.ordenar([m["texto"] for m in leidas], ev.get("nombre", ""),
                                ev.get("subtitulo", ""))

        def misma(g, x):
            """Mision guardada g y leida x: mismo titulo (y lo guardado es un
            trozo de lo leido) o textos muy parecidos."""
            tg, tx = sin_acentos(g.get("titulo") or ""), sin_acentos(x.get("titulo") or "")
            if tg and tg == tx and not g.get("texto"):
                return True                       # guardada solo con el titulo
            # con cifras distintas no es la misma («Gasta 2.000» / «Gasta 10.000 GEC»)
            if clasificar(tm.completo(g))["meta"] != clasificar(tm.completo(x))["meta"]:
                return False
            return parecida(tm.completo(g), tm.completo(x)) >= 0.75

        # completar las misiones que se guardaron a medias
        for x in limpias:
            g = next((g for g in guardadas if misma(g, x)), None)
            if g is not None and self.mem.mejorar_mision(k, g["id"], x["titulo"], x["texto"]):
                self.log(f"  Misión completada en la memoria: «{tm.completo(x)}».")
        guardadas = (self.mem.eventos().get(k) or {}).get("misiones") or []
        for i, m in enumerate(leidas):
            if not m["progreso"] and not m.get("hecha"):
                continue
            trozos = [tm.completo(x) for x in limpias if x["origen"] == i] or [m["texto"]]
            if m["progreso"] and len(trozos) > 1:
                meta = m["progreso"][1]
                trozos = [t for t in trozos if clasificar(t)["meta"] == meta] or trozos[:1]
            texto = trozos[0]
            pieza = next((x for x in limpias if x["origen"] == i and tm.completo(x) == texto),
                         {"titulo": "", "texto": texto})
            mejor = next((g for g in guardadas if misma(g, pieza)), None) or \
                max(guardadas, key=lambda g: parecida(tm.completo(g), texto), default=None)
            if mejor and (misma(mejor, pieza) or parecida(tm.completo(mejor), texto) >= 0.75):
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
        from cerebro.memoria_eventos import LEER_UNA_VEZ
        una_vez = k in LEER_UNA_VEZ
        if guardar_requisitos or (una_vez and leidas):
            ms = self.mem.guardar_misiones(k, [m["texto"] for m in leidas], sumar=una_vez)
            bot = sum(1 for m in ms if m["accion"] == "bot")
            self.log(f"  «{nombre}»: {len(ms)} misión(es), {bot} las hace el bot.")
        self._apuntar(k, leidas)
        if una_vez and leidas:
            self.mem.marcar_misiones_leidas(k)       # esta cuenta ya no las vuelve a leer
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
    #  no se vuelve a mirar el progreso de un evento si se miro hace menos de
    #  esto: 1 h si le falta algo; 6 h si ya esta todo completado
    PROGRESO_RECIENTE = 3600
    PROGRESO_COMPLETO = 6 * 3600

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
        lista = [t for t in lista if t["nombre"] and not ignorado(clave(t["nombre"]))]
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
            # todos los eventos con misiones (para recoger lo cumplido); los
            # que tienen misiones del bot, primero
            con_bot = set(self.mem.con_misiones_del_bot())
            con_mis = set(self.mem.con_misiones())
            pendientes = {p["evento"] for p in self.mem.pendientes()}
            vistos = 0
            for t in sorted(lista, key=lambda t: clave(t["nombre"]) not in con_bot):
                k = clave(t["nombre"])
                if self.parado() or vistos >= self.MAX_PROGRESO_INICIO:
                    break
                espera = self.PROGRESO_RECIENTE if k in pendientes else self.PROGRESO_COMPLETO
                if k not in con_mis or time.time() - self.mem.leido_t(k) < espera:
                    continue
                self.status["estado"] = f"progreso de {t['nombre']}"
                self.log(f"  Miro cómo va esta cuenta en «{t['nombre']}».")
                if self.leer_evento(k, t["pantalla"], guardar_requisitos=False, mostrar=t["nombre"]):
                    vistos += 1
        self._salir()
        self.volver_a_base()
        self.status["estado"] = "terminado"

    def jugar_evento(self, k: str, nombre: str) -> bool:
        """Paso de la Rutina para un evento (Artefactos, Bingo Estelar...):
        entra, hace lo suyo (en Artefactos, «Buscar» con todo el encendido),
        lee las misiones (la primera vez las guarda), recoge las cumplidas y
        vuelve a la base."""
        if not ocr.disponible():
            return False
        ev = self.mem.eventos().get(k) or {}
        if not self.ir_a_base() or not self._abrir_lista():
            return False
        from cerebro.memoria_eventos import LEER_UNA_VEZ
        # cada cuenta lee una vez SUS misiones (cada una ve las que le quedan)
        self.sin_misiones = k in LEER_UNA_VEZ and self.mem.misiones_leidas(k)
        hecho = self.leer_evento(k, ev.get("nombre") or nombre,
                                 guardar_requisitos=self.mem.necesita_leer(k) or not ev.get("misiones"),
                                 mostrar=nombre)
        self._salir()
        self.volver_a_base()
        return hecho

    def progreso_de(self, k: str) -> bool:
        """Solo vuelve a leer el progreso de un evento ya conocido. Devuelve
        si se ha podido leer."""
        ev = self.mem.eventos().get(k)
        if not ev or not ocr.disponible():
            return False
        if not self.ir_a_base() or not self._abrir_lista():
            return False
        ok = self.leer_evento(k, ev.get("nombre", k), guardar_requisitos=False)
        self._salir()
        self.volver_a_base()
        return bool(ok)


def segundos_fin(t) -> int | None:            # atajo para pruebas
    return segundos(t)
