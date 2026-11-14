"""Base comun de todas las tareas (controlador, registro, capturas, esperas, Atras)."""
from __future__ import annotations

import time
from collections import deque

import cv2
import numpy as np

from vision import pantallas
from nucleo.rutas import _DIAG_LIMPIO, carpeta_diag
from vision.plantillas import buscar_rotulo, localizar


# ---------------------------------------------------------------- dataset --
# Recolector de capturas para entrenar el detector (ballenas, gemas, flotas,
# piratas): guarda en %LOCALAPPDATA%\NovaBot\dataset\ las vistas del mapa,
# como mucho una cada 20 s por cuenta y hasta 3000 archivos. Solo imagenes del
# juego (nada personal); se usan para mejorar el modelo.
_ULT_RECOGIDA: dict = {}
_ETIQUETAS_DATASET = ("mapa", "sistema", "panel_ballena", "zoom_ballena", "hueco", "menu_hueco",
                      "gemas", "gema", "modo", "radar", "pirata", "objetivo", "dialogo",
                      "antes_de_atacar", "hueco_ballena", "menu_ballena",
                      # escombros (para enseñar al detector a verlos)
                      "restos", "zona_restos", "resto_menu")


def _recolectar(img, etiqueta: str, cuenta: str):
    try:
        if not any(etiqueta.startswith(e) for e in _ETIQUETAS_DATASET):
            return
        import os
        ahora = time.time()
        # las de escombros llevan su propio turno (si no, casi nunca se
        # guardan: llegan justo despues de las del sistema)
        turno = (cuenta, etiqueta.startswith(("restos", "zona_restos", "resto_menu")))
        if ahora - _ULT_RECOGIDA.get(turno, 0) < (5 if turno[1] else 20):
            return
        _ULT_RECOGIDA[turno] = ahora
        base = os.path.join(os.path.dirname(carpeta_diag()), "dataset")
        os.makedirs(base, exist_ok=True)
        if len(os.listdir(base)) >= 3000:
            return
        nombre = f"{etiqueta}_{str(cuenta).split(':')[-1]}_{int(ahora * 1000)}.jpg"
        cv2.imwrite(os.path.join(base, nombre), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    except Exception:                                         # noqa: BLE001
        pass


#  Capturas de diagnostico: cada cuenta guarda solo las ULTIMAS (las de antes
#  se borran), numeradas seguidas aunque la Rutina encadene muchas tareas.
#  Antes cada tarea guardaba 200 y se iban sumando hasta ocupar gigas.
LIMITE_DIAG = 200
_DIAG_RECIENTES: dict = {}        # carpeta -> deque de rutas, de mas vieja a mas nueva
_DIAG_N: dict = {}                # carpeta -> ultimo numero usado


class TareaBase:
    """Lo comun a todas las tareas: controlador, registro, capturas con
    diagnostico, esperas, boton Atras y cierre de menus y avisos."""

    P_ATRAS = (0.054, 0.090)           # flecha Atras, arriba a la izquierda

    def __init__(self, ctrl, log=None, stop=None, atacar=False, diag=True,
                 usar_salto=True):
        self.ctrl = ctrl
        self._log = log
        self.stop = stop
        self.atacar = atacar
        self.usar_salto = usar_salto
        self.status = {"estado": "en espera", "ciclo": 0, "ciclos": 0,
                       "encontrados": 0, "atacados": 0}
        # Diagnostico: guarda lo que ve el bot en %LOCALAPPDATA%\NovaBot\diag\<puerto>\
        # (fuera de la carpeta del bot, para que las capturas de la cuenta no
        # viajen si se pasa el bot a otra persona).
        self.diag_dir = None
        self._n_diag = 0
        if diag:
            import os
            nombre = str(getattr(ctrl, "name", "inst")).replace(":", "_")
            self.diag_dir = os.path.join(carpeta_diag(), nombre)
            try:
                os.makedirs(self.diag_dir, exist_ok=True)
                # empezar limpio, pero solo la primera vez en esta ejecucion:
                # la Rutina y la tarea mixta crean varias tareas seguidas y no
                # deben borrar el registro de las anteriores
                if self.diag_dir not in _DIAG_LIMPIO:
                    _DIAG_LIMPIO.add(self.diag_dir)
                    for f in os.listdir(self.diag_dir):
                        if f.endswith(".png") or f == "registro.txt":
                            os.remove(os.path.join(self.diag_dir, f))
                    _DIAG_RECIENTES[self.diag_dir] = deque()
                    _DIAG_N[self.diag_dir] = 0
            except OSError:
                self.diag_dir = None

    def cap(self, etiqueta: str = "") -> np.ndarray:
        """Captura y, en modo diagnostico, guarda la imagen numerada.
        Si el juego ha sacado un aviso (No / OK) lo cierra con No antes de
        seguir: un aviso de FPS bajo llego a bloquear una instancia una hora."""
        img = self.ctrl.capture()
        for _ in range(3):
            try:
                av = pantallas.dialogo_aviso(img)
            except Exception:                             # noqa: BLE001
                av = None
            if not av:
                if self._aviso_conexion(img):
                    img = self.ctrl.capture()
                    continue
                break
            self.log("Aviso del juego en pantalla: pulso No.")
            self.ctrl.tap(av["no"])
            time.sleep(1.2)
            img = self.ctrl.capture()
        _recolectar(img, etiqueta, getattr(self.ctrl, "name", "inst"))
        if self.diag_dir:
            import os
            self._n_diag += 1
            n = _DIAG_N.get(self.diag_dir, 0) + 1
            _DIAG_N[self.diag_dir] = n
            recientes = _DIAG_RECIENTES.setdefault(self.diag_dir, deque())
            try:
                ruta = os.path.join(self.diag_dir, f"{n:05d}_{etiqueta}.png")
                cv2.imwrite(ruta, img)
                recientes.append(ruta)
                while len(recientes) > LIMITE_DIAG:
                    vieja = recientes.popleft()
                    try:
                        os.remove(vieja)
                    except OSError:
                        pass
            except Exception:                             # noqa: BLE001
                pass
        return img

    def _aviso_conexion(self, img) -> bool:
        """"Error de conexion" (un solo boton OK): se pulsa OK y se espera a
        que el juego vuelva a conectar. Solo si el texto lo confirma."""
        try:
            ok = pantallas.aviso_un_boton(img)
        except Exception:                                 # noqa: BLE001
            ok = None
        if ok is None:
            return False
        try:
            from vision import ocr
            from cerebro.memoria_eventos import sin_acentos
            texto = sin_acentos(ocr.texto(img, (0.25, 0.1, 0.75, 0.9)))
        except Exception:                                 # noqa: BLE001
            texto = ""
        if not any(p in texto for p in ("conexion", "conectar", "red ", "servidor",
                                        "desconect", "network", "connection")):
            return False
        self.log("Aviso del juego: error de conexión. Pulso OK y espero a que reconecte.")
        self.ctrl.tap(ok)
        time.sleep(8.0)
        return True

    def log(self, msg):
        if self._log is not None:
            self._log(getattr(self.ctrl, "name", ""), msg)
        else:
            print(msg, flush=True)
        # copia en programa\diag\<puerto>\registro.txt para revisar despues
        if self.diag_dir:
            try:
                import os
                with open(os.path.join(self.diag_dir, "registro.txt"), "a",
                          encoding="utf-8") as f:
                    f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
            except OSError:
                pass

    def parado(self) -> bool:
        return self.stop is not None and self.stop.is_set()

    def punto(self, img, rel) -> tuple[int, int]:
        h, w = img.shape[:2]
        return int(w * rel[0]), int(h * rel[1])

    def pulsar(self, img, rel):
        self.ctrl.tap(self.punto(img, rel))

    def pulsar_rotulo(self, img, nombre: str, rel_respaldo, umbral=0.60) -> bool:
        """Pulsa un boton localizandolo por su texto. Si no lo reconoce, cae
        a la posicion aproximada. Asi aguanta un cambio de resolucion."""
        parecido, donde = buscar_rotulo(img, nombre)
        if parecido >= umbral:
            self.ctrl.tap(donde)
            return True
        self.pulsar(img, rel_respaldo)
        return False

    def esperar(self, cond, segundos: float, intervalo: float = 0.6,
                etiqueta: str = "espera"):
        """Repite la captura hasta que cond(img) sea cierta. Devuelve la
        imagen que la cumplio, o None si se agoto el tiempo."""
        fin = time.time() + segundos
        while time.time() < fin and not self.parado():
            img = self.cap(etiqueta)
            if cond(img):
                return img
            time.sleep(intervalo)
        return None

    def esperar_hasta(self, cond, max_s: float, paso: float = 0.25,
                      etiqueta: str = "espera"):
        """Sustituye a un time.sleep fijo: captura y sale EN CUANTO cond(img)
        sea cierta (no espera el tiempo entero). Devuelve la imagen que la
        cumplio, o None si pasaron max_s segundos o se pidio parar. La
        captura (~0.3 s) ya marca el ritmo; paso es una pausa extra corta.
        Uso: img = self.esperar_hasta(lambda im: pantallas.menu(im), 4)"""
        fin = time.time() + max_s
        while not self.parado():
            img = self.cap(etiqueta)
            try:
                if cond(img):
                    return img
            except Exception:                             # noqa: BLE001
                pass
            if time.time() + paso >= fin:
                return None
            time.sleep(paso)
        return None

    @staticmethod
    def _miniatura(img):
        return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (160, 90),
                          interpolation=cv2.INTER_AREA).astype(np.int16)

    def esperar_cambio(self, img_ref, max_s: float = 3.0, umbral: float = 2.5,
                       paso: float = 0.15, zona=None, etiqueta: str = "cambio"):
        """Tras un toque: espera a que la pantalla cambie respecto a img_ref
        (la captura de ANTES del toque) y devuelve la nueva captura; si no
        cambia en max_s, devuelve la ultima captura igualmente (nunca None,
        asi el codigo sigue como con un sleep). zona = (x0, y0, x1, y1) en
        fracciones para vigilar solo una parte. umbral = diferencia media
        (0-255) de la miniatura. Para animaciones que aun se mueven al salir
        use despues esperar_quieto()."""
        def recorte(im):
            if not zona:
                return im
            h, w = im.shape[:2]
            return im[int(zona[0 + 1] * h):int(zona[3] * h), int(zona[0] * w):int(zona[2] * w)]
        ref = self._miniatura(recorte(img_ref))
        fin = time.time() + max_s
        img = img_ref
        while not self.parado():
            img = self.cap(etiqueta)
            if float(np.abs(self._miniatura(recorte(img)) - ref).mean()) >= umbral:
                return img
            if time.time() + paso >= fin:
                break
            time.sleep(paso)
        return img

    def esperar_quieto(self, segundos: float = 12.0, etiqueta="carga",
                       intervalo: float = 0.7):
        """Espera a que la pantalla deje de cambiar: el mapa tarda en cargar
        los elementos y no siempre lo hace igual de rapido.
        intervalo: pausa entre capturas (0.7 por defecto, como siempre); con
        0.2 se gana ~1 s por llamada si la animacion es corta."""
        fin, prev, quietas = time.time() + segundos, None, 0
        img = None
        while time.time() < fin and not self.parado():
            img = self.cap(etiqueta)
            peq = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (160, 90))
            if prev is not None and float(np.abs(peq.astype(np.int16)
                                                 - prev.astype(np.int16)).mean()) < 2.5:
                quietas += 1
                if quietas >= 2:
                    return img
            else:
                quietas = 0
            prev = peq
            time.sleep(intervalo)
        return img

    def atras(self, img=None):
        """Cerrar lo que este abierto: tecla Atras de Android, que cierra
        dialogos sin tener que encontrar ningun boton."""
        if hasattr(self.ctrl, "back"):
            self.ctrl.back()
        else:
            if img is None:
                img = self.cap("atras")
            self.pulsar_rotulo(img, "atras", self.P_ATRAS)

    def menu_abierto(self, img) -> bool:
        """Hay un menu de seleccion abierto (todos acaban en 'Marcador').
        Medido: 0.88-1.00 con menu, como mucho 0.57 sin el."""
        return buscar_rotulo(img, "marcador")[0] >= 0.75

    def cerrar_menu(self, img) -> bool:
        """Cierra el menu de seleccion SOLO si hay uno abierto. Con el mapa
        sin menu, la tecla Atras quitaria el zoom y la vista del pirata."""
        if self.menu_abierto(img):
            self.atras(img)
            time.sleep(0.9)
            return True
        return False

    def _alerta(self, img) -> bool:
        """La alerta de furia pirata: titulo ALERTA y boton Continuar, cada
        uno en su sitio (Continuar abajo a la derecha del titulo).
        Medido: 1.00 con la alerta, como mucho 0.46 en el resto."""
        pa, ca, ea = localizar(img, "alerta")
        pc, cc = buscar_rotulo(img, "continuar")
        if pa < 0.75 or pc < 0.75:
            return False
        return 80 * ea < cc[0] - ca[0] < 300 * ea and 300 * ea < cc[1] - ca[1] < 540 * ea
