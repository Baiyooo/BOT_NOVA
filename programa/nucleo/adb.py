"""Conexion con BlueStacks por ADB: capturas, toques y arrastres, y lectura de
las instancias y del ADB desde bluestacks.conf.
"""
from __future__ import annotations

import subprocess
import sys
import time

import cv2
import numpy as np

from tareas.roaming import SIN_VENTANA


class SinConexion(RuntimeError):
    """No se puede capturar la pantalla: la ventana de BlueStacks de esta cuenta
    esta cerrada o su ADB no responde. Es un RuntimeError, como antes."""


class AdbController:
    def __init__(self, device: str, adb: str = "adb", drag_ms: int = 180,
                 style: str = "drag"):
        self.device, self.adb_bin, self.drag_ms = device, adb, drag_ms
        self.name, self.style = device, style
        # «Pausar» de la ventana: antes de cada toque o captura se espera aqui
        # mientras la cuenta este en pausa (y no se haya pedido parar)
        self.pausa = None
        self.parada = None
        subprocess.run([adb, "connect", device], capture_output=True, timeout=20,
                       stdin=subprocess.DEVNULL, **SIN_VENTANA)

    def conectada(self) -> bool:
        """Comprobacion rapida (sin capturar): ADB ve esta instancia."""
        try:
            subprocess.run([self.adb_bin, "connect", self.device], capture_output=True,
                           timeout=10, stdin=subprocess.DEVNULL, **SIN_VENTANA)
            estado = subprocess.run([self.adb_bin, "-s", self.device, "get-state"],
                                    capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
                                    **SIN_VENTANA).stdout
            return estado.strip() == b"device"
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _adb(self, *args, timeout=25):
        return subprocess.run([self.adb_bin, "-s", self.device, *args],
                              capture_output=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, **SIN_VENTANA).stdout

    @staticmethod
    def _decodificar(data, arreglar_saltos=False):
        """Pasa los bytes de screencap a imagen. Con OpenCV 5 un buffer vacio
        lanza una excepcion en vez de devolver None, asi que se mira antes."""
        if not data or len(data) < 100:
            return None
        if arreglar_saltos:
            data = data.replace(b"\r\n", b"\n")
        try:
            return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error:
            return None

    @staticmethod
    def _decodificar_crudo(data):
        """screencap sin -p: cabecera (ancho, alto, formato[, espacio de
        color]) y los pixeles RGBA tal cual. Se ahorra comprimir el PNG en
        Android, que es lo que mas tarda."""
        if not data or len(data) < 16:
            return None
        w, h = int.from_bytes(data[0:4], "little"), int.from_bytes(data[4:8], "little")
        if not (100 < w < 8000 and 100 < h < 8000):
            return None
        n = w * h * 4
        for cab in (16, 12):
            if len(data) >= cab + n:
                px = np.frombuffer(data, np.uint8, n, cab).reshape(h, w, 4)
                return cv2.cvtColor(px, cv2.COLOR_RGBA2BGR)
        return None

    def _captura_modo(self, modo):
        if modo == "crudo":
            return self._decodificar_crudo(self._adb("exec-out", "screencap"))
        return self._decodificar(self._adb("exec-out", "screencap", "-p"))

    def _elegir_modo(self):
        """Prueba las dos formas de capturar y se queda con la mas rapida."""
        tiempos = {}
        for modo in ("crudo", "png"):
            try:
                t = time.time()
                ok = all(self._captura_modo(modo) is not None for _ in range(2))
                if ok:
                    tiempos[modo] = time.time() - t
            except Exception:                             # noqa: BLE001
                pass
        self._modo = min(tiempos, key=tiempos.get) if tiempos else "png"

    def capture(self) -> np.ndarray:
        self.esperar_pausa()
        img = None
        if getattr(self, "_modo", None) is None:
            self._elegir_modo()
        for intento in range(4):
            try:
                img = self._captura_modo(self._modo)
                if img is None and self._modo == "crudo":
                    img = self._captura_modo("png")
                if img is None:
                    # algunas versiones no traen exec-out: por shell, deshaciendo
                    # el cambio de salto de linea que mete Android
                    img = self._decodificar(self._adb("shell", "screencap", "-p"), True)
            except subprocess.TimeoutExpired:
                img = None
            if img is not None:
                return img
            # ADB se ha caido un momento (pasa con varias instancias a la vez):
            # reconectar y volver a probar
            time.sleep(1.0 + intento)
            try:
                subprocess.run([self.adb_bin, "connect", self.device], capture_output=True,
                               timeout=20, stdin=subprocess.DEVNULL, **SIN_VENTANA)
            except subprocess.TimeoutExpired:
                pass
        raise SinConexion(
            f"{self.device}: no se pudo capturar. Comprueba que en BlueStacks "
            "esten activados Ajustes > Avanzado > Android Debug Bridge y que el "
            "puerto sea el correcto.")

    # -- Toques por una consola de Android que se queda abierta ---------------
    #  Abrir un adb nuevo por cada toque cuesta mas que el toque en si. Se
    #  mantiene un "adb shell" abierto y se le escriben las ordenes; cada una
    #  termina con una marca para saber que ya se ha hecho. Si la consola se
    #  cae, se vuelve al metodo de siempre.
    def _consola(self):
        import queue
        import threading
        p = getattr(self, "_shell", None)
        if p is not None and p.poll() is None:
            return p
        p = subprocess.Popen([self.adb_bin, "-s", self.device, "shell"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, **SIN_VENTANA)
        cola = queue.Queue()

        def leer():
            for linea in iter(p.stdout.readline, b""):
                cola.put(linea)
            cola.put(None)
        threading.Thread(target=leer, daemon=True).start()
        self._shell, self._cola = p, cola
        return p

    def esperar_pausa(self):
        """Mientras la cuenta este en pausa, no hace nada (ni toca ni captura)."""
        while self.pausa is not None and self.pausa.is_set() and \
                not (self.parada is not None and self.parada.is_set()):
            time.sleep(0.25)

    def _orden(self, orden: str, espera: float = 6.0):
        self.esperar_pausa()
        import queue
        try:
            p = self._consola()
            p.stdin.write((orden + "; echo __nb_ok\n").encode())
            p.stdin.flush()
            fin = time.time() + espera
            while time.time() < fin:
                linea = self._cola.get(timeout=max(0.05, fin - time.time()))
                if linea is None:
                    break
                if b"__nb_ok" in linea:
                    return
        except (OSError, ValueError, queue.Empty):
            pass
        # la consola no responde: cerrarla y hacerlo a la antigua
        try:
            self._shell.kill()
        except Exception:                                 # noqa: BLE001
            pass
        self._shell = None
        self._adb("shell", *orden.split())

    def drag(self, a, b):
        if self.style == "click":
            self._orden(f"input tap {a[0]} {a[1]}")
            time.sleep(0.12)
            self._orden(f"input tap {b[0]} {b[1]}")
            return
        self._orden(f"input swipe {a[0]} {a[1]} {b[0]} {b[1]} {self.drag_ms}")

    def tap(self, p):
        self._orden(f"input tap {int(p[0])} {int(p[1])}")

    def back(self):
        """Tecla Atras de Android: cierra el dialogo o menu que este abierto."""
        self._orden("input keyevent 4")

    # ------------------------------------------------------------- zoom --
    #  El comando «input» de Android 7 no hace gestos de dos dedos. BlueStacks
    #  tiene un tactil virtual («BlueStacks Virtual Touch», multitactil tipo A)
    #  en el que el usuario de ADB puede escribir: con sendevent se simula el
    #  pellizco (como Ctrl + rueda o las flechas del teclado en BlueStacks).
    _tactil = None

    def _dispositivo_tactil(self):
        if self._tactil is None:
            salida = self._adb("shell", "getevent", "-p", timeout=15).decode("utf-8", "ignore")
            dev = ""
            for linea in salida.splitlines():
                if linea.startswith("add device"):
                    dev = linea.split(":", 1)[1].strip()
                elif "name:" in linea and "Virtual Touch" in linea:
                    self._tactil = dev
                    break
            else:
                self._tactil = ""
        return self._tactil

    def zoom(self, acercar: bool = True, centro=None, fuerza: float = 1.0, pasos: int = 7,
             tam=(1600, 900)) -> bool:
        """Pellizco con dos dedos en horizontal alrededor de 'centro' (por
        defecto el centro de la pantalla). acercar=True separa los dedos
        (amplia); False los junta (aleja). 'fuerza' (0.3-1.5) gradua cuanto.
        Devuelve False si esta instancia no tiene tactil virtual."""
        self.esperar_pausa()
        dev = self._dispositivo_tactil()
        if not dev:
            return False
        w, h = tam
        cx, cy = centro if centro is not None else (w / 2, h / 2)
        corto, largo = 140, 140 + 500 * max(0.2, min(1.5, fuerza))
        d0, d1 = (corto, largo) if acercar else (largo, corto)
        k = 32767
        ordenes = []
        for i in range(pasos + 1):
            d = d0 + (d1 - d0) * i / pasos
            for x in (cx - d / 2, cx + d / 2):
                x = min(max(x, 5), w - 5)
                ordenes += [f"sendevent {dev} 3 53 {int(x * k / w)}",
                            f"sendevent {dev} 3 54 {int(cy * k / h)}", f"sendevent {dev} 0 2 0"]
            ordenes.append(f"sendevent {dev} 0 0 0")
        ordenes += [f"sendevent {dev} 0 2 0", f"sendevent {dev} 0 0 0"]   # levantar los dedos
        self._adb("shell", " ; ".join(ordenes), timeout=30)
        return True


# ============================================================================
# Descubrir BlueStacks (instancias y su ADB)
# ============================================================================
RUTAS_CONF = [
    r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf",
    r"C:\ProgramData\BlueStacks\bluestacks.conf",
]
RUTAS_ADB = [
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\BlueStacks\HD-Adb.exe",
]


def buscar_adb() -> str:
    """Devuelve el ADB de BlueStacks si esta, y si no el 'adb' del sistema."""
    import os
    for r in RUTAS_ADB:
        if os.path.exists(r):
            return r
    return "adb"


def leer_instancias() -> list[tuple[str, int]]:
    """Lee bluestacks.conf y devuelve [(nombre, puerto_adb), ...]."""
    import os
    import re
    texto = None
    for r in RUTAS_CONF:
        if os.path.exists(r):
            try:
                with open(r, encoding="utf-8", errors="replace") as fh:
                    texto = fh.read()
                break
            except OSError:
                pass
    if not texto:
        return []
    datos: dict[str, dict[str, str]] = {}
    patron = (r'bst\.instance\.([A-Za-z0-9_]+)\.(?:status\.)?'
              r'(adb_port|display_name)="([^"]*)"')
    for inst, clave, valor in re.findall(patron, texto):
        datos.setdefault(inst, {})[clave] = valor
    salida = []
    for inst, d in sorted(datos.items()):
        if "adb_port" in d and d["adb_port"].isdigit():
            salida.append((d.get("display_name") or inst, int(d["adb_port"])))
    return salida


def bluestacks_abierto() -> bool:
    """True si hay algun proceso de BlueStacks en marcha."""
    if sys.platform != "win32":
        return False
    try:
        salida = subprocess.run(["tasklist"], capture_output=True, timeout=20,
                                text=True, errors="replace", **SIN_VENTANA).stdout.lower()
    except Exception:                                   # noqa: BLE001
        return False
    return any(p in salida for p in
               ("hd-player.exe", "hd-multiinstancemanager.exe", "bstkvmmgr.exe"))


def activar_adb() -> int:
    """Pone bst.enable_adb_access="1" en bluestacks.conf.

    Devuelve 0 si queda activado, 2 si BlueStacks esta abierto (reescribiria
    el archivo al cerrarse, asi que no se toca), 1 si no se ha podido."""
    import os
    import re
    import shutil

    conf = next((r for r in RUTAS_CONF if os.path.exists(r)), None)
    if not conf:
        print("No encuentro bluestacks.conf. Activalo a mano en BlueStacks:")
        print("  Ajustes > Avanzado > Android Debug Bridge")
        return 1

    try:
        with open(conf, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
    except OSError as e:
        print(f"No puedo leer {conf}: {e}")
        return 1

    if re.search(r'bst\.enable_adb_access="1"', texto):
        print("ADB ya estaba activado.")
        return 0

    if bluestacks_abierto():
        print("BlueStacks esta abierto.")
        return 2        # el .bat pedira cerrarlo y volvera a intentarlo

    nuevo, n = re.subn(r'(bst\.enable_adb_access=")0(")', r"\g<1>1\g<2>", texto)
    if n == 0:          # la clave no existe: anadirla
        nuevo = texto.rstrip("\n") + '\nbst.enable_adb_access="1"\n'
        n = 1
    try:
        shutil.copy2(conf, conf + ".bak")       # copia de seguridad
        with open(conf, "w", encoding="utf-8") as fh:
            fh.write(nuevo)
    except OSError as e:
        print(f"No he podido escribir en {conf}: {e}")
        print("Activalo a mano en BlueStacks:")
        print("  Ajustes > Avanzado > Android Debug Bridge")
        return 1

    with open(conf, encoding="utf-8", errors="replace") as fh:
        comprobacion = fh.read()
    if re.search(r'bst\.enable_adb_access="1"', comprobacion):
        print("ADB activado. (Copia del archivo original en bluestacks.conf.bak)")
        return 0
    print("El cambio no ha quedado guardado. Activalo a mano en BlueStacks.")
    return 1
