"""Preparar la flota antes de las ballenas: reparar y cargar el grupo de batalla.

Antes de matar ninguna ballena, reparar las naves
dañadas y cargar el grupo de batalla 2 (en su cuenta se llama «PvE PirateS»).

Camino (todo con el lector de texto, 1600x900):
  base > icono «Base» de la barra de arriba > pantalla «Base» con pestañas
  Base / POSS1..POSS6.
  1) pestaña «Base»: si hay daños, «Reparar todo» (cuesta recursos normales).
  2) pestaña «POSS1» > «Cargar» (arriba a la derecha) > ventana con los grupos
     guardados a la izquierda (ARAÑAS / PvE PirateS / PVP): el 2º > «Load All».
  3) «Atrás» hasta la base.
Nunca: GEC, acelerar, comprar, «Disolver», «Guardar», ni la casilla del
Sistema de Defensa. Si una confirmacion menciona GEC/acelerar/comprar, se cancela.
"""
from __future__ import annotations

import re
import time

from vision import ocr
from tareas.recompensas import Recompensas

PROHIBIDO = ("gec", "acelerar", "comprar", "disolver", "completar rapidamente", "recargar")


class PrepararGrupo(Recompensas):
    NOMBRE = "Preparar grupo de batalla"

    def __init__(self, ctrl, log=None, stop=None, diag=True, grupo: int = 2):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.grupo = int(grupo)
        self.status = {"estado": "en espera", "reparado": False, "cargado": False}

    # ------------------------------------------------------------ util --
    def _leer(self, etiqueta, zona=None):
        img = self.cap(etiqueta)
        return img, ocr.leer(img, zona)

    def _toca(self, frases, etiqueta, zona=None, espera=2.0, intentos=3):
        for _ in range(intentos):
            if self.parado():
                return None
            img, items = self._leer(etiqueta)
            h, w = img.shape[:2]
            d = ocr.buscar(items, *frases, zona=zona, w=w, h=h)
            if d:
                self.ctrl.tap(d["centro"])
                time.sleep(espera)
                return d
            time.sleep(1.0)
        return None

    @staticmethod
    def _palabra(items, palabra, zona, w, h):
        """Centro de una palabra aunque el lector la junte con otras
        ("Guardar Cargar Disolver"): se reparte el ancho de la caja por letras."""
        x0, y0, x1, y1 = zona
        for d in items:
            cx, cy = d["centro"]
            if not (x0 * w <= cx <= x1 * w and y0 * h <= cy <= y1 * h):
                continue
            t = ocr.normal(d["texto"])
            i = t.find(palabra)
            if i < 0:
                continue
            bx, by, bw, bh = d["caja"]
            return (int(bx + bw * (i + len(palabra) / 2) / max(1, len(t))), int(by + bh / 2))
        return None

    def _confirmar_si_sale(self):
        """Si sale una confirmacion (No / OK), pulsa OK SOLO si no habla de
        GEC/acelerar/comprar. Se captura sin cap(): cap() cierra los avisos con No."""
        from vision import pantallas
        time.sleep(1.2)
        img = self.ctrl.capture()
        try:
            av = pantallas.dialogo_aviso(img)
        except Exception:                                     # noqa: BLE001
            av = None
        h, w = img.shape[:2]
        items = ocr.leer(img, (0.15, 0.15, 0.85, 0.85))
        todo = ocr.normal(" ".join(d["texto"] for d in items))
        if av:
            if any(p in todo for p in PROHIBIDO):
                self.log(f"  La confirmación habla de GEC/acelerar/comprar: cancelo ({todo[:60]}).")
                self.ctrl.tap(av["no"])
            else:
                self.log(f"  Confirmo: «{todo[:70]}».")
                self.ctrl.tap(av["ok"])
            time.sleep(1.5)
            return
        b = ocr.buscar(items, "confirmar", "aceptar", "si", "ok", zona=(0.2, 0.3, 0.8, 0.9), w=w, h=h)
        if b and not any(p in todo for p in PROHIBIDO):
            self.log(f"  Confirmo: «{todo[:70]}».")
            self.ctrl.tap(b["centro"])
            time.sleep(1.5)

    def _abrir_pantalla_base(self) -> bool:
        if not self.ir_a_base():
            return False
        time.sleep(3.0)               # la base recien cargada aun no hace caso a los toques
        img, items = self._leer("barra_base", (0.25, 0, 0.8, 0.16))
        h, w = img.shape[:2]
        z = (0.25, 0, 0.8, 0.16)
        if not (ocr.buscar(items, "base", zona=z, w=w, h=h) or ocr.buscar(items, "alianza", zona=z, w=w, h=h)):
            self.log("  No veo la barra de arriba.")
            return False
        # icono «Base» de la barra, siempre en el mismo sitio (1600x900: (870, 44))
        self.ctrl.tap((int(w * 870 / 1600), int(h * 44 / 900)))
        time.sleep(3.0)
        img, items = self._leer("pantalla_base", (0, 0, 1, 0.25))
        # pantalla de la Base: «Atrás» arriba a la izquierda y la pestaña «Base»
        if not (ocr.buscar(items, "atras", zona=(0, 0, 0.25, 0.15), w=w, h=h)
                and ocr.buscar(items, "base", zona=(0.1, 0.1, 0.45, 0.22), w=w, h=h)):
            self.log("  No se ha abierto la pantalla de la Base (pestañas POSS).")
            return False
        return True

    # ----------------------------------------------------------- pasos --
    def reparar(self) -> bool:
        if not self._toca(("base",), "tab_base", zona=(0.1, 0.1, 0.45, 0.22), espera=2.0):
            return False
        img, items = self._leer("danos")
        h, w = img.shape[:2]
        b = ocr.buscar(items, "reparar todo", zona=(0.3, 0.6, 0.75, 0.85), w=w, h=h)
        if not b:
            if ocr.buscar(items, "acelerar", zona=(0.25, 0.4, 0.8, 0.9), w=w, h=h):
                self.log("  Hay una reparación en curso: la acelero.")
                self.acelerar_reparacion()
            else:
                self.log("  Sin naves dañadas (no sale «Reparar todo»).")
            return True
        todo = ocr.normal(" ".join(d["texto"] for d in items
                                   if d["centro"][1] > h * 0.5 and w * 0.3 < d["centro"][0] < w * 0.75))
        if any(p in todo for p in PROHIBIDO):
            self.log("  La reparación pide GEC: no reparo.")
            return False
        self.log("  Reparo las naves dañadas («Reparar todo», con recursos).")
        self.ctrl.tap(b["centro"])
        self._confirmar_si_sale()
        self.status["reparado"] = True
        self.acelerar_reparacion()
        return True

    def acelerar_reparacion(self, maximo=25):
        """Se permite usar ACELERACIONES DE REPARACION
        (objetos) para terminar la reparacion. Solo se pulsa «Usar» en filas
        que hablan de reparacion; nunca GEC, comprar ni «Completar»."""
        img, items = self._leer("reparando")
        h, w = img.shape[:2]
        gr = ocr.buscar(items, "gratis", zona=(0.25, 0.3, 0.8, 0.9), w=w, h=h)
        if gr:
            # cuando queda poco, el juego deja terminar la reparacion gratis
            self.log("  La reparación se puede terminar «Gratis»: la termino.")
            self.ctrl.tap(gr["centro"])
            time.sleep(1.5)
            return 0
        a = ocr.buscar(items, "acelerar", zona=(0.25, 0.4, 0.8, 0.9), w=w, h=h)
        if not a:
            self.log("  No sale «Acelerar» para la reparación (lee: " +
                     ", ".join(d["texto"] for d in items if d["centro"][1] > h * 0.45)[:120] + ").")
            return 0
        self.ctrl.tap(a["centro"])
        time.sleep(2.0)
        # «Uso rápido»: filas 5 min / 15 min / 1 h / 3 h / 8 h (/ 1 día) con su
        # «Usar X1». Para ir rápido usando las grandes. Se lee
        # el tiempo «Restante» y se usa la MENOR que lo cubre entera (un solo
        # toque); si ninguna lo cubre, la mayor y se repite.
        import re
        DUR = [300, 900, 3600, 3 * 3600, 8 * 3600, 24 * 3600]
        usadas = 0
        for _ in range(8):
            if self.parado():
                break
            img, items = self._leer("aceleraciones", (0.5, 0, 1, 1))
            h, w = img.shape[:2]
            restante = None
            for d in items:
                m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", d["texto"].strip())
                if m and d["centro"][1] < h * 0.3:
                    restante = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
            usar = sorted((d for d in items if ocr.normal(d["texto"]).startswith("usar")
                           and d["centro"][0] > w * 0.88), key=lambda d: d["centro"][1])
            if restante is None or not usar:
                if usadas == 0:
                    self.log("  No veo el tiempo restante o los «Usar» (lee: " +
                             ", ".join(d["texto"] for d in items)[:160] + ").")
                break
            # la primera fila con «Usar» es la de 5 min (si no, no se toca nada)
            primera = " ".join(ocr.normal(d["texto"]) for d in items
                               if abs(d["centro"][1] - usar[0]["centro"][1]) < h * 0.04)
            if "5 min" not in primera and "5min" not in primera.replace(" ", ""):
                self.log(f"  No reconozco la lista de aceleraciones ({primera[:50]}); no uso nada.")
                break
            filas = list(zip(DUR, usar, strict=False))
            elegida = next(((s, u) for s, u in filas if s >= restante), filas[-1])
            fila = " ".join(ocr.normal(d["texto"]) for d in items
                            if abs(d["centro"][1] - elegida[1]["centro"][1]) < h * 0.06)
            if any(p in fila for p in PROHIBIDO) or "gec" in fila:
                self.log("  Esa fila habla de GEC: no la uso.")
                break
            self.log(f"  Quedan {restante // 60} min: uso una aceleración de "
                     f"{elegida[0] // 3600 or elegida[0] // 60}{' h' if elegida[0] >= 3600 else ' min'}.")
            self.ctrl.tap(elegida[1]["centro"])
            time.sleep(1.8)
            usadas += 1
            if elegida[0] >= restante:
                break
        self.atras()
        time.sleep(1.2)
        return usadas

    def cargar_grupo(self) -> bool:
        # la 1ª flota: la pestaña a la derecha de «Base» (en cada cuenta se llama
        # distinto: POSS1, MISS2...)
        img, items = self._leer("tab_poss1", (0, 0.1, 1, 0.22))
        h, w = img.shape[:2]
        b = ocr.buscar(items, "base", zona=(0.1, 0.1, 0.45, 0.22), w=w, h=h)
        if not b:
            self.log("  No veo la pestaña «Base».")
            return False
        der = sorted((d for d in items if d["centro"][0] > b["centro"][0] + w * 0.04
                      and abs(d["centro"][1] - b["centro"][1]) < h * 0.03),
                     key=lambda d: d["centro"][0])
        if not der:
            self.log("  No veo la pestaña de la primera flota.")
            return False
        # se usa la primera flota que este atracada (con una fuera sale «No atrac.»)
        abierta = False
        fuera = 0
        for tab in der[:6]:
            if self.parado():
                return False
            self.ctrl.tap(tab["centro"])
            time.sleep(2.0)
            img, items = self._leer("flota1")
            h, w = img.shape[:2]
            if ocr.buscar(items, "no atrac", "no atracada", "ir", zona=(0.3, 0.3, 0.7, 0.65), w=w, h=h):
                fuera += 1
                continue
            if ocr.buscar(items, "unidad de combate", "guardar", "disolver", w=w, h=h):
                abierta = True
                break
        if not abierta:
            if fuera:
                self.log(f"  {fuera} flota(s) no están atracadas (fuera): no puedo cargar aún.")
                self.status["fuera"] = True
            else:
                self.log("  No se abre la pestaña de ninguna flota.")
            return False
        if fuera:
            # con flotas fuera el grupo se carga mal (se quedan como estaban):
            # esperar a que vuelvan todas
            self.log(f"  {fuera} flota(s) aún fuera: espero a que vuelvan antes de cargar.")
            self.status["fuera"] = True
            return False
        # «Guardar / Cargar / Disolver» arriba a la derecha: Cargar es el del
        # medio, siempre en el mismo sitio (1600x900: icono en (1434, 232))
        img, items = self._leer("cargar")
        h, w = img.shape[:2]
        self.ctrl.tap((int(w * 1434 / 1600), int(h * 232 / 900)))
        time.sleep(2.5)
        img, items = self._leer("grupos")
        h, w = img.shape[:2]
        if not ocr.buscar(items, "resumen del grupo", "guardar informacion", "load all",
                          w=w, h=h):
            self.log("  No se ha abierto la ventana de grupos (lee: " +
                     ", ".join(d["texto"] for d in items)[:150] + ").")
            return False
        # grupos guardados: textos de la columna de la izquierda, de arriba abajo
        # (los textos de detras salen apagados mas a la izquierda: POSS1, Salud...)
        izq = sorted((d for d in items if w * 0.08 < d["centro"][0] < w * 0.27
                      and h * 0.06 < d["centro"][1] < h * 0.45
                      and len(ocr.normal(d["texto"])) >= 3 and not ocr.coincide(d["texto"], "atras")),
                     key=lambda d: d["centro"][1])
        # quitar los que estan en la misma fila (texto partido)
        grupos = []
        for d in izq:
            if not grupos or d["centro"][1] - grupos[-1]["centro"][1] > h * 0.05:
                grupos.append(d)
        # grupo 2 = el de las ballenas (Poseidón), «PvE PirateS»/«PVE»; si no, el 2º.
        # grupo 1 = el de arriba (piratas de sigilo)
        g = None
        if self.grupo == 2:
            g = next((d for d in grupos if "pve" in ocr.normal(d["texto"]).replace(" ", "")), None)
        if g is None and len(grupos) < self.grupo:
            self.log(f"  Solo veo {len(grupos)} grupo(s) guardado(s); no cargo.")
            self.atras(img)
            return False
        g = g or grupos[self.grupo - 1]
        self.log(f"  Cargo el grupo de batalla {self.grupo} («{g['texto']}»).")
        self.ctrl.tap(g["centro"])
        time.sleep(1.5)
        # «Load All» (el lector lo lee mal: "L0od 1", "Lod"): abajo a la derecha
        img, items = self._leer("load_all", (0.6, 0.8, 1, 1))
        h, w = img.shape[:2]
        b = next((d for d in items if 0.62 * w < d["centro"][0] < 0.9 * w and d["centro"][1] > 0.85 * h
                  and re.match(r"^(l[o0]a?d|cargar todo)", ocr.normal(d["texto"]))), None)
        # si el lector no lo lee, su sitio fijo (1600x900: (1301, 830)); la
        # ventana de grupos ya se ha comprobado arriba
        punto = b["centro"] if b else (int(w * 1301 / 1600), int(h * 830 / 900))
        self.ctrl.tap(punto)
        time.sleep(2.0)
        self._confirmar_si_sale()
        self.status["cargado"] = True
        return True

    def run(self, ciclos: int = 1, reparar: bool = True):
        if not ocr.disponible():
            return False
        self.status["estado"] = "preparando el grupo"
        self.status["fuera"] = False
        ok = False
        if self._abrir_pantalla_base():
            if reparar:
                self.reparar()
            ok = self.cargar_grupo()
        # salir con «Atrás» de arriba a la izquierda hasta la base
        for _ in range(4):
            img = self.cap("salir_base")
            if self.en_base(img):
                break
            h, w = img.shape[:2]
            d = ocr.buscar(ocr.leer(img, (0, 0, 0.25, 0.15)), "atras", w=w, h=h)
            if d:
                self.ctrl.tap(d["centro"])
            else:
                self.atras(img)
            time.sleep(1.8)
        self.volver_a_base()
        self.status["estado"] = "terminado"
        return ok


def preparar(ctrl, log=None, stop=None, grupo=2, reparar=True, intentos=6) -> bool:
    """Flotas a casa + (reparar) + cargar el grupo. Si alguna flota aun esta
    fuera (vuelve o combate), espera 30 s y repite."""
    from tareas.flotas import LlamarFlotas
    for i in range(intentos):
        if stop is not None and stop.is_set():
            return False
        LlamarFlotas(ctrl, log=log, stop=stop).run(1)
        g = PrepararGrupo(ctrl, log=log, stop=stop, grupo=grupo)
        if g.run(1, reparar=reparar and i == 0):
            return True
        if not g.status.get("fuera"):
            return False
        if log:
            log(getattr(ctrl, "name", ""), "  Espero 30 s a que vuelvan las flotas.")
        fin = time.time() + 30
        while time.time() < fin and not (stop is not None and stop.is_set()):
            time.sleep(1)
    return False


def solo_reparar(ctrl, log=None, stop=None) -> bool:
    """Al acabar la tanda de ballenas: entrar en la Base y reparar (con
    aceleraciones de reparacion), sin cargar ningun grupo."""
    g = PrepararGrupo(ctrl, log=log, stop=stop)
    ok = False
    if g._abrir_pantalla_base():
        ok = g.reparar()
    for _ in range(4):
        img = g.cap("salir_base")
        if g.en_base(img):
            break
        h, w = img.shape[:2]
        d = ocr.buscar(ocr.leer(img, (0, 0, 0.25, 0.15)), "atras", w=w, h=h)
        if d:
            g.ctrl.tap(d["centro"])
        else:
            g.atras(img)
        time.sleep(1.8)
    g.volver_a_base()
    return ok
