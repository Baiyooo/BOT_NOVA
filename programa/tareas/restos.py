"""Recoger los escombros que dejan los piratas normales al morir (mineral,
aleacion o cristal) con los drones, igual que las gemas de las ballenas.

En el mapa, los escombros llevan una etiqueta con el recurso y dos cifras
apiladas («1.375» sobre «28.500»). Al tocarlos sale su menu: el tipo
(«Mineral», «Aleacion», «Cristal»), «Cantidad» y los botones «Recoger» y
«Marcador». Cada «Recoger» manda los drones.

Reglas fijas: solo se pulsa «Recoger» si el menu dice Mineral, Aleacion o
Cristal. Nunca «Marcador», nunca nada que no sea un escombro. Si un toque abre
otra cosa, se cierra y se sigue.
"""
from __future__ import annotations

import re
import time

from nucleo.cerrojo import Cerrojo
from vision import ocr
from tareas import descartes
from tareas.piratas.normales import PiratasNormales, desplazamiento

#  el juego los abrevia en el menu («Aleac.»): se reconocen por el principio
RECURSOS = ("mineral", "aleacion", "aleación", "cristal")
PREFIJOS = ("miner", "aleac", "crist")
_CIFRA = re.compile(r"^\s*\d{1,3}([.,]\d{3})*\s*$")


def etiquetas_restos(items, w, h) -> list[dict]:
    """Etiquetas de escombros en la vista acercada: una cifra («1.700»,
    «250»; si se esta recogiendo, otra debajo). Se dejan fuera la barra de
    recursos de arriba, el menu de la derecha, la «Cantidad» del menu abierto
    y la segunda cifra de cada pareja."""
    k = h / 900.0
    cifras = [d for d in items if _CIFRA.match(d["texto"].replace("'", "."))
              and h * 0.12 < d["centro"][1] < h * 0.97
              and not (d["centro"][0] > w * 0.62 and d["centro"][1] < h * 0.47)]   # el menu
    # el menu abierto (a la izquierda del montón): «Cristales / Cantidad / 1.700»
    #  y el de un pirata o una flota: «Flota pirata / Fuerza / 63.353»
    cantidad = [d for d in items if ocr.normal(d["texto"]).startswith(("cantidad", "fuerza"))
                or ocr.normal(d["texto"]).startswith(PREFIJOS)]
    out = []
    for a in cifras:
        if any(abs(a["centro"][0] - c["centro"][0]) < 110 * k and 0 < a["centro"][1] - c["centro"][1] < 95 * k
               for c in cantidad):
            continue                                       # la «Cantidad» del menu
        if any(abs(b["centro"][0] - a["centro"][0]) < 45 * k
               and 8 * k < a["centro"][1] - b["centro"][1] < 40 * k for b in cifras):
            continue                                       # la de abajo de una pareja
        out.append(a)
    return out


#  Icono de un montón en la VISTA GENERAL del sistema: un cristal lila pequeño
#  (medido: H 135-150, S 25-110, V 170-255 en OpenCV; unos 100 px a 1600x900).
#  Ningun otro icono del mapa es lila (piratas naranja/rojo, estaciones
#  amarillas, aliados verdes/cian).
LILA = ((120, 160), (25, 140), (160, 255))
#  zonas que no son mapa: barra de arriba, recursos de la izquierda,
#  columna de botones de la derecha y botones de abajo
NO_MAPA = ((0, 0, 1, 0.13), (0, 0, 0.2, 0.5), (0.82, 0, 1, 1), (0, 0.84, 1, 1))


def iconos_restos(img) -> list[tuple[int, int]]:
    """Centros de los sitios con montones que se ven en la vista general:
    - el cristal lila (montones libres; si ya hay drones nuestros en uno,
      queda solo un trozo lila, por eso basta con unos 25 px);
    - los corchetes verdes «( )» que pone el juego alrededor del icono
      cuando nuestros drones ya recogen alli (puede haber mas montones debajo)."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    k = (w * h) / (1600 * 900)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    def en_mapa(cx, cy):
        return not any(x0 * w <= cx <= x1 * w and y0 * h <= cy <= y1 * h for x0, y0, x1, y1 in NO_MAPA)

    (h0, h1), (s0, s1), (v0, v1) = LILA
    m = ((hsv[:, :, 0] >= h0) & (hsv[:, :, 0] <= h1) & (hsv[:, :, 1] >= s0) & (hsv[:, :, 1] <= s1)
         & (hsv[:, :, 2] >= v0) & (hsv[:, :, 2] <= v1)).astype(np.uint8)
    n, etiq, st, cen = cv2.connectedComponentsWithStats(m)
    lilas = []
    for i in range(1, n):
        _x, _y, bw, bh, area = st[i]
        cx, cy = float(cen[i][0]), float(cen[i][1])
        if 25 * k <= area <= 600 * k and bw < 0.04 * w and bh < 0.06 * h and en_mapa(cx, cy):
            sat = float(hsv[:, :, 1][etiq == i].mean())
            lilas.append((sat, (int(cx), int(cy))))
    # prioridad: primero los mas lilas (saturacion alta), al final los blanquecinos
    lilas.sort(key=lambda t: -t[0])
    out = [c for _s, c in lilas]
    # corchetes verdes: dos trazos finos y altos, uno a cada lado (15-30 px)
    v = ((hsv[:, :, 0] >= 50) & (hsv[:, :, 0] <= 75) & (hsv[:, :, 1] >= 120)
         & (hsv[:, :, 2] >= 150)).astype(np.uint8)
    n, _, st, cen = cv2.connectedComponentsWithStats(v)
    trazos = [(float(cen[i][0]), float(cen[i][1])) for i in range(1, n)
              if 20 * k <= st[i][4] <= 120 * k and st[i][2] <= 9 * k ** 0.5 and 10 * k ** 0.5 <= st[i][3] <= 24 * k ** 0.5]
    for a in range(len(trazos)):
        for b in range(a + 1, len(trazos)):
            (xa, ya), (xb, yb) = trazos[a], trazos[b]
            if 12 * k ** 0.5 <= abs(xa - xb) <= 32 * k ** 0.5 and abs(ya - yb) <= 6 * k ** 0.5:
                c = (int((xa + xb) / 2), int((ya + yb) / 2) + 3)
                if en_mapa(*c) and not any(abs(c[0] - o[0]) < 20 and abs(c[1] - o[1]) < 20 for o in out):
                    out.append(c)
    return out


#  las gemas (de ballenas) se recogen igual («Gema organica», «Gema sagrada»...)
PREFIJOS_GEMA = ("gema", "ema ")


def menu_recoger(items, w, h, prefijos=PREFIJOS):
    """Si esta abierto el menu de un montón de esos tipos: (tipo, boton «Recoger»)."""
    tipo = next((ocr.normal(d["texto"]) for d in items
                 if ocr.normal(d["texto"]).startswith(prefijos)
                 and d["centro"][0] < w * 0.6), None)
    boton = next((d for d in items if ocr.normal(d["texto"]) == "recoger"
                  and d["centro"][0] > w * 0.55 and d["centro"][1] < h * 0.6), None)
    if tipo and boton:
        return tipo, boton
    return None


#  montones ya pedidos: (tipo, cantidad del menu) -> hora. Mientras los
#  drones van de camino el menu sigue ofreciendo «Recoger»; asi no se pide
#  dos veces el mismo, aunque se vuelva a encontrar desde otra zona.
_PEDIDOS: dict = {}
PEDIDO_SEG = 15 * 60

# ---- un contador por dron -------------------------------------------------
#  Cada «Recoger» manda un dron: ida (el juego enseña el tiempo, «00:00:15»),
#  unos 5 min recogiendo y la vuelta. Se apunta cuando queda libre cada uno
#  (por cuenta, en la carpeta de datos: drones_<cuenta>.json): asi no se
#  mandan mas de los que hay y se vuelve a buscar justo cuando se libera uno.
RECOGIDA_SEG = 5 * 60
VIAJE_POR_DEFECTO = 60


def _ruta_drones(cuenta) -> str:
    import os
    from nucleo.rutas import carpeta_datos
    return os.path.join(carpeta_datos(), f"drones_{str(cuenta).replace(':', '_')}.json")


def drones_ocupados(cuenta) -> list[float]:
    """Hora en que queda libre cada dron que esta fuera (los ya libres no salen)."""
    from nucleo import config as _cfg
    ahora = time.time()
    return sorted(t for t in _cfg.leer(_ruta_drones(cuenta), defecto={}).get("fin", []) if t > ahora)


def drones_libres(cuenta, total: int) -> int:
    return max(0, int(total) - len(drones_ocupados(cuenta)))


def proximo_dron_libre(cuenta) -> float:
    """Cuando vuelve el primero de los que estan fuera (0 si no hay ninguno fuera)."""
    o = drones_ocupados(cuenta)
    return o[0] if o else 0.0


def apuntar_dron(cuenta, viaje: float):
    from nucleo import config as _cfg
    fin = drones_ocupados(cuenta) + [time.time() + 2 * viaje + RECOGIDA_SEG]
    _cfg.guardar(_ruta_drones(cuenta), {"fin": fin})


def tiempo_viaje(items) -> float | None:
    """El contador «00:00:15» que pone el juego al mandar el dron."""
    for d in items:
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2}):(\d{2})\s*", d["texto"])
        if m:
            seg = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if 0 < seg < 3600:
                return float(seg)
    return None


#  la cantidad del menu: «18.500.000», «1.375» o abreviada («18,5M», «950K»)
_CANTIDAD = re.compile(r"^\s*\d[\d.,]*\s*[kKmM]?\s*$")
_ESCALA = {"": 1, "k": 1_000, "m": 1_000_000}


def parse_cantidad(texto) -> int | None:
    """La cifra de un escombro como numero entero, o None si no se entiende.
    Acepta «18.500.000» / «18,500,000» / «18'500'000» (miles con punto, coma o
    apostrofe), «1.375», y abreviados con K / M: «18,5M», «3.2 M», «950K».
    Sin letra, solo se admiten miles bien agrupados (un «3,2» suelto es
    ambiguo y no se interpreta)."""
    if texto is None:
        return None
    t = re.sub(r"\s+", "", str(texto)).lower()
    m = re.fullmatch(r"(\d[\d.,']*)([km]?)", t)
    if not m:
        return None
    num, letra = m.groups()
    num = num.replace("'", ".").rstrip(".,")
    if letra:
        # con letra el ultimo separador es el decimal; los anteriores, de miles
        partes = re.split(r"[.,]", num)
        entero = "".join(partes[:-1]) if len(partes) > 1 else partes[0]
        dec = partes[-1] if len(partes) > 1 else ""
        try:
            return int(round(float(f"{entero or 0}.{dec or 0}") * _ESCALA[letra]))
        except ValueError:
            return None
    if re.fullmatch(r"\d+", num):
        return int(num)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
        return int(re.sub(r"[.,]", "", num))
    return None


def _legible(v: int) -> str:
    """«3,2 M» para millones; la cifra con puntos de miles por debajo («1.375»)."""
    if v >= 1_000_000:
        return f"{v / 1e6:.1f}".replace(".", ",").removesuffix(",0") + " M"
    return f"{v:,}".replace(",", ".")


#  tipo del menu (por su principio) -> clave de los minimos
_TIPO_CLAVE = {"miner": "mineral", "aleac": "aleacion", "crist": "cristal"}


def cantidad_menu(items, h: int = 900) -> str:
    """La «Cantidad» del menu abierto de un escombro (la cifra de debajo).
    h: alto de la captura (las distancias estan medidas a 1600x900)."""
    c = next((d for d in items if ocr.normal(d["texto"]).startswith("cantidad")), None)
    if c is None:
        return ""
    k = h / 900.0
    debajo = [d for d in items if _CANTIDAD.match(d["texto"].replace("'", "."))
              and abs(d["centro"][0] - c["centro"][0]) < 120 * k and 0 < d["centro"][1] - c["centro"][1] < 70 * k]
    return min(debajo, key=lambda d: d["centro"][1])["texto"] if debajo else ""


class RecogerRestos(PiratasNormales):
    NOMBRE = "Recoger escombros"
    #  desde la etiqueta, el escombro queda arriba a la izquierda (linea naranja)
    #  (medido: la cifra de la etiqueta empieza ~83 px a la derecha y ~51 px
    #  por debajo del escombro, a 1600x900)
    TOQUES = ((-0.052, -0.057), (-0.065, -0.062), (-0.040, -0.045), (-0.060, -0.035))

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.status.update({"estado": "en espera", "restos": 0})
        self._ultimo_tipo = ""
        self._pedidos = set()
        # que se recoge (Ajustes > Piratas > Recoger con drones)
        self.prefijos = PREFIJOS
        # minimo por tipo ({"mineral": n, "cristal": n, "aleacion": n}, en unidades):
        # solo se recoge lo que lo supere. None = sin minimo (piratas normales).
        self.minimos: dict | None = None
        self.iconos_vistos = 0
        self.sitios_utiles = self.sitios_poco = 0

    def con_minimos(self, minimos: dict | None):
        """Solo recoger escombros que superen su minimo (ballenas)."""
        self.minimos = dict(minimos) if minimos else None
        return self

    def _por_debajo(self, tipo, cantidad) -> bool:
        """¿Hay que dejar este escombro? Por debajo de su minimo, o sin
        cantidad legible (ante la duda no se manda ningun dron)."""
        if not self.minimos:
            return False
        clave = _TIPO_CLAVE.get(tipo[:5])
        if clave is None or self.minimos.get(clave) is None:
            return False
        valor = parse_cantidad(cantidad)
        nombre = tipo[:1].upper() + tipo[1:]
        if valor is None:
            self.log(f"  {nombre}: no leo su cantidad; no lo recojo.")
            return True
        minimo = int(self.minimos[clave])
        if valor <= minimo:
            self.log(f"  {nombre} {_legible(valor)}: menos de {_legible(minimo)}, lo dejo.")
            return True
        return False

    def que_recoger(self, escombros: bool = True, gemas: bool = False):
        self.prefijos = (PREFIJOS if escombros else ()) + (PREFIJOS_GEMA if gemas else ())
        return self

    def _ocr(self, etiqueta):
        img = self.cap(etiqueta)
        return img, ocr.leer(img, sin_giro=True)

    def _probar_menu(self, punto, evitar=()) -> str | None:
        """Toca un punto. Si sale el menu de un escombro libre, pulsa
        «Recoger» y devuelve "recogido"; si es un escombro que ya se esta
        recogiendo («Recogiendo», boton «Llamar»), lo cierra y devuelve
        "ocupado"; si es un escombro bajo el minimo configurado (o sin cantidad
        legible, solo con minimos), lo cierra y devuelve "poco"; si no es un
        escombro, None."""
        self.ctrl.tap(punto)
        time.sleep(1.3)
        img, items = self._ocr("resto_menu")
        h, w = img.shape[:2]
        r = menu_recoger(items, w, h, self.prefijos)
        if r is None:
            texto = " ".join(ocr.normal(d["texto"]) for d in items)
            ocupado = any(t in texto for t in self.prefijos) and \
                ("recogiendo" in texto or "llamar" in texto)
            if self.menu_abierto(img) or ocupado:
                self.cerrar_menu(img)
            return "ocupado" if ocupado else None
        tipo, boton = r
        ahora = time.time()
        for kk in [kk for kk, t0 in _PEDIDOS.items() if ahora - t0 > PEDIDO_SEG]:
            _PEDIDOS.pop(kk, None)
        cantidad = cantidad_menu(items, h)
        if self._por_debajo(tipo, cantidad):
            self.cerrar_menu(img)                 # no vale la pena: sin dron; se descarta un rato
            return "poco"
        #  la clave lleva la cuenta (_PEDIDOS es global) y solo vale con cantidad
        #  leida: sin ella dos montones distintos del mismo tipo se confundirian
        clave = (self._cuenta(), tipo[:5], cantidad) if cantidad else None
        if (clave is not None and clave in _PEDIDOS) or tipo[:5] in {t[:5] for t in evitar}:
            # ya se le han mandado drones (aun van de camino): no se repite
            self.cerrar_menu(img)
            return "ocupado"
        if descartes.hay_movimiento(self.ctrl, img, punto):
            # una linea de vuelo hacia aqui: otro dron/flota ya va
            self.log(f"  Movimiento en {tipo}: alguien ya va, lo dejo.")
            self.cerrar_menu(img)
            return "ocupado"
        if clave is not None:
            _PEDIDOS[clave] = ahora
        self._ultimo_tipo = tipo
        self.ctrl.tap(boton["centro"])
        time.sleep(1.5)
        # el contador de este dron: ida + recogida + vuelta
        _img2, items2 = self._ocr("dron_enviado")
        viaje = tiempo_viaje(items2) or VIAJE_POR_DEFECTO
        apuntar_dron(getattr(self.ctrl, "name", "inst"), viaje)
        self.status["restos"] += 1
        self.status["recogidas"] = self.status.get("recogidas", 0) + 1
        self.log(f"  Drones a por unos escombros ({tipo}); vuelven en ~{round((2 * viaje + RECOGIDA_SEG) / 60)} min.")
        return "recogido"

    def recoger_cerca(self, cupo: int, primera=None) -> int:
        """En la vista acercada: manda drones a los montones de alrededor, uno
        cada vez y nunca dos veces al mismo (cada montón se reconoce por la
        cifra de su etiqueta)."""
        hechas, probadas = 0, []
        for _ in range(cupo * 3):
            if hechas >= cupo or self.parado():
                break
            if primera is not None:
                img, items = primera
                primera = None
            else:
                img, items = self._ocr("restos")
            h, w = img.shape[:2]
            libres = [e for e in etiquetas_restos(items, w, h)
                      if not any(abs(e["centro"][0] - a) < 40 and abs(e["centro"][1] - b) < 40
                                  for a, b in probadas)]
            if not libres:
                break
            # cuanta mas cantidad, mejor: primero los montones mas grandes
            libres.sort(key=lambda d: -int(re.sub(r"\D", "", d["texto"]) or 0))
            e = libres[0]
            probadas.append(e["centro"])
            x0, y0 = e["caja"][0], e["caja"][1]
            for dx, dy in self.TOQUES:
                r = self._probar_menu((int(x0 + dx * w), int(y0 + dy * h)))
                if r is not None:                   # recogido u ocupado: no volver
                    hechas += r == "recogido"
                    break
        return hechas

    #  dentro de un sitio, donde tocar para ir eligiendo cada montón apilado
    #  (a 1600x900): el centro, arriba, abajo y a los lados
    #  (si ya hay un montón recogiendose, los de debajo salen pinchando un
    #  pelin mas abajo: primero hacia abajo)
    TOQUES_SITIO = ((0, 0), (0, 12), (0, 22), (0, 32), (-12, 0), (12, 0), (0, -12))

    def recoger_iconos(self, cupo: int, cerca=None, fija: bool = False) -> int:
        """Los montones se ven en la vista general (cristal lila, o corchetes
        verdes si ya hay drones nuestros): se localizan TODOS de una captura y
        se va directo a cada sitio. Un icono puede tapar VARIOS montones
        (Aleacion, Mineral y Cristal juntos): se toca el centro, un pelin mas
        arriba, abajo y a los lados, y cada montón nuevo se recoge (los ya
        pedidos se reconocen por su menu y se dejan).

        cerca(c, img) -> bool: solo se miran los iconos que cumplan (por ejemplo
        los cercanos a donde murio una ballena). fija=True: no se pulsa Atras
        para volver a la vista general (se queda con la camara como esta, en 2D
        y centrada). self.iconos_vistos = los que se veian (tras el filtro)."""
        n = 0
        tocados = []                             # sitios ya visitados
        self.iconos_vistos = 0
        self.sitios_utiles = self.sitios_poco = 0   # sitios con montones validos / solo bajo el minimo
        vista = (lambda: self.cap("sistema")) if fija else self.vista_sistema
        lista = descartes.de_cuenta(self._cuenta())
        with self._turno() as cj:
            for _ in range(cupo * 3 + 3):
                if n >= cupo or self.parado():
                    break
                cj.renovar()
                img = vista()
                k = img.shape[1] / 1600.0
                visibles = iconos_restos(img)
                if cerca is not None:
                    visibles = [c for c in visibles if cerca(c, img)]
                self.iconos_vistos = max(self.iconos_vistos, len(visibles))
                libres = [c for c in lista.filtrar(visibles, img)
                          if not any(abs(c[0] - q[0]) < 20 and abs(c[1] - q[1]) < 20 for q in tocados)]
                if not libres:
                    break
                c = libres[0]
                tocados.append(c)
                fallos, util, poco = 0, False, False
                for i, (dx, dy) in enumerate(self.TOQUES_SITIO):
                    if n >= cupo or self.parado() or fallos >= 3:
                        break
                    if i:
                        vista()
                    r = self._probar_menu((int(c[0] + dx * k), int(c[1] + dy * k)))
                    n += r == "recogido"
                    util = util or r not in (None, "poco")   # «poco» (bajo el minimo) se descarta 5 min
                    poco = poco or r == "poco"
                    if r == "recogido":
                        fallos = 0
                    elif r != "poco":              # «poco» no es un fallo: puede haber otro montón debajo
                        fallos += 1
                    cj.renovar()
                # sitio con montones (recogido/ocupado): se deja unos segundos;
                # si no era nada, 5 min
                lista.anotar(c, img, "mando" if util else "malo")
                self.sitios_utiles += bool(util)
                self.sitios_poco += bool(poco and not util)
        return n

    def _cuenta(self) -> str:
        return str(getattr(self.ctrl, "name", "inst"))

    def _turno(self) -> Cerrojo:
        """Turno compartido entre cuentas: solo una elige y manda drones a la vez."""
        return Cerrojo("drones", self._cuenta(), parado=self.parado, log=self.log)

    def run_sistema(self, cupo: int = 3, maximo_zonas: int = 4) -> int:
        with self._turno():
            return self._run_sistema(cupo, maximo_zonas)

    def run_en(self, puntos, cupo: int = 3, img_ref=None) -> int:
        with self._turno():
            return self._run_en(puntos, cupo, img_ref)

    def _run_sistema(self, cupo: int, maximo_zonas: int) -> int:
        """Busca escombros por todo el sistema, aunque no los haya dejado esta
        cuenta (aparecen donde mueren piratas o ballenas). Primero por sus
        iconos en la vista general (todos de una vez); si no se ve ninguno, se
        mira alrededor de los piratas (al tocarlos el juego acerca la camara y
        salen las etiquetas de los escombros cercanos)."""
        self.status["estado"] = "buscando escombros"
        img = self.vista_sistema()
        if iconos_restos(img):
            n = self.recoger_iconos(cupo)
            if n:
                self.log(f"Escombros del sistema: {n} recogida(s) con los drones.")
            self.status["estado"] = "terminado"
            return n
        zonas = self.simbolos_pirata(img)[:maximo_zonas]
        n = 0
        for z in zonas:
            if n >= cupo or self.parado():
                break
            self.ctrl.tap(z)
            img2 = self._esperar_menu(2.0, "zona_restos")
            # las etiquetas se leen YA (al cerrar el menu del pirata la camara
            # se aleja); el primer toque en un escombro cierra ese menu
            n += self.recoger_cerca(cupo - n, primera=(img2, ocr.leer(img2, sin_giro=True)))
            self.vista_sistema()
        if n:
            self.log(f"Escombros del sistema: {n} recogida(s) con los drones.")
        self.status["estado"] = "terminado"
        return n

    def _run_en(self, puntos, cupo: int, img_ref) -> int:
        """Recoge los escombros de los piratas muertos en 'puntos' (posiciones
        en la vista del sistema cuando se tomo img_ref). Devuelve cuantos."""
        self.status["estado"] = "recogiendo escombros"
        img = self.vista_sistema()
        if img_ref is not None and img_ref.shape == img.shape:
            d = desplazamiento(img_ref, img)
            if d:
                puntos = [(x + d[0], y + d[1]) for x, y in puntos]
        h, w = img.shape[:2]
        n = 0
        for p in puntos:
            if n >= cupo or self.parado():
                break
            if not (0 < p[0] < w and 0 < p[1] < h):
                continue
            # tocar donde murio: el juego acerca la camara (o abre ya el menu);
            # luego, los montones de alrededor (cada uno una vez)
            r = self._probar_menu((int(p[0]), int(p[1])))
            if r == "recogido":
                n += 1
            n += self.recoger_cerca(cupo - n)
            self.vista_sistema()
        if n:
            self.log(f"Escombros: {n} recogida(s) con los drones.")
        self.status["estado"] = "terminado"
        return n
