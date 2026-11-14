"""Recoger las recompensas de los eventos activos."""
from __future__ import annotations

from nucleo import config as _cfg
import cv2
import numpy as np
import time
from tareas.recompensas import Recompensas
from vision.detectores import _diferencia, buscar_cerrar_x, puntos_rojos
from nucleo.rutas import carpeta_diag
from vision.plantillas import localizar, localizar_todos


class RecogerEventos(Recompensas):
    """Recoge las recompensas de los eventos, sin gastar nada.

    Abre la lista de eventos y entra solo en los que llevan la etiqueta verde
    "¡RECOMPENSA!". Dentro pulsa unicamente:
      - los botones verdes "Recoger";
      - las pestanas con "¡RECOMPENSA!" y los puntos rojos de aviso (abren
        la pestana o la lista de misiones donde esta lo pendiente);
      - las cajas de las barras de progreso ("Puntos actuales"): si no estan
        listas solo muestran lo que dan, y se cierra.
    Nunca pulsa Comprar, Cambiar, Rellenar, Ir a ni nada que gaste GEC.
    Sale con la X de cada ventana (nunca Atras en la base)."""

    NOMBRE = "Recompensas de eventos"
    U_RECOGER = 0.78
    U_ETIQUETA = 0.80
    MAX_EVENTOS = 14
    MAX_PASOS = 40
    # cajas de la barra de progreso, respecto a "Puntos actuales" (ADB, 1600)
    CAJAS_DX = (291, 509, 727, 945, 1164)
    CAJAS_DY = -26

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.status = {"estado": "en espera", "recogidas": 0, "eventos": 0}
        self.vistos = []          # miniaturas de las filas de eventos ya visitadas
        self._firmas = []         # cabeceras de las ventanas ya vistas

    # -------------------------------------------------------- utilidades --
    @staticmethod
    def _mini(img, x0, y0, x1, y1):
        h, w = img.shape[:2]
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(w, int(x1)), min(h, int(y1))
        if x1 - x0 < 10 or y1 - y0 < 5:
            return None
        g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, (48, 12)).astype(np.int16)

    def _ya_visto(self, mini) -> bool:
        if mini is None or any(float(np.abs(mini - v).mean()) < 9.0 for v in self.vistos):
            return True
        # eventos en los que ya se entro sin poder recoger nada (Artefactos sin
        # potencia, eventos terminados...): no volver hasta pasadas 20 h
        return any(float(np.abs(mini - np.array(v, np.int16)).mean()) < 9.0
                   for v, t in self._sin_nada() if time.time() - t < 20 * 3600)

    def _ruta_memoria(self):
        import os
        nombre = str(getattr(self.ctrl, "name", "inst")).replace(":", "_")
        return os.path.join(os.path.dirname(carpeta_diag()), f"eventos_{nombre}.json")

    def _sin_nada(self):
        try:
            return [(v, t) for v, t in _cfg.leer(self._ruta_memoria(), defecto=[])]
        except (ValueError, TypeError):
            return []

    def _apuntar_sin_nada(self, mini):
        datos = [(v, t) for v, t in self._sin_nada() if time.time() - t < 20 * 3600]
        datos.append((mini.astype(int).tolist(), time.time()))
        _cfg.guardar(self._ruta_memoria(), datos)

    def _cerrar_aviso(self):
        """"¡Nuevos objetos!" o la vista previa de una caja: toque arriba,
        fuera de la ventanita."""
        time.sleep(1.5)
        img = self.cap("aviso")
        h, w = img.shape[:2]
        self.ctrl.tap((int(w * 0.30), int(h * 0.04)))
        time.sleep(1.0)

    def _fuera(self, img) -> bool:
        """Base o vista del sistema: ya no estamos dentro de un evento."""
        return self.en_base(img) or self._ve(img, "estacion") is not None \
            or localizar(img, "eventos")[0] >= 0.80

    def _abrir_lista(self) -> bool:
        img = self.cap("base")
        p, c, _ = localizar(img, "eventos")
        if p < 0.80:
            if not self.ir_a_base():
                return False
            img = self.cap("base")
            p, c, _ = localizar(img, "eventos")
            if p < 0.80:
                self.log("  No veo el boton Eventos.")
                return False
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.06)))
        time.sleep(2.5)
        return not self._fuera(self.cap("lista"))

    def _salir(self, maximo=5):
        """Cierra ventanas con su X hasta volver a la base o al sistema."""
        for _ in range(maximo):
            img = self.cap("salir")
            if self._fuera(img):
                return True
            x = self._boton_cerrar(img)
            if x is None:
                self.volver_a_base()
                return True
            self.ctrl.tap(x)
            time.sleep(1.8)
        return self._fuera(self.cap("salir"))

    # ---------------------------------------------------------- un evento --
    def _siguiente_evento(self):
        """En la lista abierta, busca (bajando) la primera fila con
        "¡RECOMPENSA!" que no se haya visitado. Devuelve el punto a tocar."""
        for _ in range(5):
            img = self.cap("lista")
            h, w = img.shape[:2]
            k = w / 1600.0
            for _, (x, y) in localizar_todos(img, "recompensa_ev", self.U_ETIQUETA):
                mini = self._mini(img, x - 700 * k, y + 15 * k, x + 120 * k, y + 95 * k)
                if self._ya_visto(mini):
                    continue
                self.vistos.append(mini)
                self._mini_actual = mini
                return (int(x - 330 * k), int(y + 45 * k))
            antes = img
            self.ctrl.drag((int(w * 0.55), int(h * 0.78)), (int(w * 0.55), int(h * 0.38)))
            time.sleep(1.2)
            if _diferencia(antes, self.cap("lista")) < 2.0:
                break                    # fin de la lista
        return None

    def _cajas(self, img, c_puntos) -> int:
        """Toca cada caja de la barra de progreso (las listas se abren)."""
        h, w = img.shape[:2]
        k = w / 1600.0
        for dx in self.CAJAS_DX:
            x, y = int(c_puntos[0] + dx * k), int(c_puntos[1] + self.CAJAS_DY * k)
            if x >= w - 10:
                break
            if self.parado():
                break
            self.ctrl.tap((x, y))
            self._cerrar_aviso()
        return 0

    def _dentro(self):
        """Recoge todo lo posible en el evento abierto."""
        tocados = set()          # (firma de pantalla, x//25, y//25)
        cajas_hechas = set()
        agotados = set()          # botones Recoger que no hacen nada
        bajadas = {}
        n = 0
        for _ in range(self.MAX_PASOS):
            if self.parado():
                break
            img = self.cap("evento")
            if self._fuera(img):
                break
            h, w = img.shape[:2]
            k = w / 1600.0
            firma = self._mini(img, 0, 0, w, h * 0.12)
            fid = next((i for i, v in enumerate(self._firmas)
                        if float(np.abs(firma - v).mean()) < 10.0), None)
            if fid is None:
                self._firmas.append(firma)
                fid = len(self._firmas) - 1
            # 1) botones "Recoger"
            rec = (localizar_todos(img, "recoger_ev", self.U_RECOGER)
                   or localizar_todos(img, "recoger_todo", 0.75)
                   or localizar_todos(img, "recoger_amb", 0.78))
            rec = [r_ for r_ in rec if (fid, r_[1][0] // 30, r_[1][1] // 30) not in agotados]
            if rec:
                c_rec = rec[0][1]
                self.ctrl.tap(c_rec)
                self._cerrar_aviso()
                despues = self.cap("evento")
                if self._sin_cambio(img, despues, c_rec):
                    # no ha pasado nada (p. ej. "Recoger todo" sin nada que dar)
                    agotados.add((fid, c_rec[0] // 30, c_rec[1] // 30))
                    continue
                n += 1
                self.log("  Recogido.")
                continue
            # 2) cajas de la barra de progreso (una vez por pantalla)
            pp, cp, _ = localizar(img, "puntos")
            if pp >= 0.85 and fid not in cajas_hechas:
                cajas_hechas.add(fid)
                self.log("  Miro las cajas de la barra de progreso.")
                self._cajas(img, cp)
                continue
            # 3) pestanas con "¡RECOMPENSA!" y puntos rojos aun no tocados
            sitio = None
            for _, c in localizar_todos(img, "recompensa_ev", self.U_ETIQUETA):
                clave = (fid, c[0] // 25, c[1] // 25)
                if clave not in tocados:
                    tocados.add(clave)
                    sitio = (c[0], int(c[1] + 20 * k))      # la pestana, debajo
                    break
            if sitio is None:
                # (Buscar de Artefactos y Roaming Test llevan un numero o
                # un punto distinto y no salen aqui)
                # botones que no se tocan aunque lleven aviso: Roaming Test
                # (minijuego, tiene su propia tarea)
                prohibidos = [c for p, c in [localizar(img, "roaming_test")[:2]] if p >= 0.80]
                for c in puntos_rojos(img, (0.0, 0.10, 1.0, 0.97)):
                    if any(abs(c[0] - q[0]) < 260 * k and abs(c[1] - q[1]) < 80 * k for q in prohibidos):
                        continue
                    clave = (fid, c[0] // 25, c[1] // 25)
                    if clave not in tocados:
                        tocados.add(clave)
                        sitio = (c[0], int(c[1] + 4 * k))
                        break
            if sitio is not None:
                self.ctrl.tap(sitio)
                time.sleep(1.8)
                continue
            # 4) bajar la lista por si hay mas "Recoger" (2 veces por pantalla)
            if bajadas.get(fid, 0) < 2:
                bajadas[fid] = bajadas.get(fid, 0) + 1
                antes = img
                self.ctrl.drag((int(w * 0.62), int(h * 0.78)), (int(w * 0.62), int(h * 0.42)))
                time.sleep(1.2)
                if _diferencia(antes, self.cap("evento")) >= 2.0:
                    continue
                bajadas[fid] = 2
            # 5) nada mas aqui: cerrar esta ventana y seguir en la de debajo
            x = self._boton_cerrar(img)
            if x is None:
                break
            self.ctrl.tap(x)
            time.sleep(1.8)
        return n

    @staticmethod
    def _sin_cambio(antes, despues, c) -> bool:
        """El boton pulsado y su fila siguen exactamente igual."""
        h, w = antes.shape[:2]
        k = w / 1600.0
        y0, y1 = max(0, int(c[1] - 40 * k)), min(h, int(c[1] + 40 * k))
        x0, x1 = max(0, int(c[0] - 110 * k)), min(w, int(c[0] + 110 * k))
        a = cv2.cvtColor(antes, cv2.COLOR_BGR2GRAY).astype(np.int16)
        b = cv2.cvtColor(despues, cv2.COLOR_BGR2GRAY).astype(np.int16)
        boton = float(np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).mean())
        fila = float(np.abs(a[y0:y1, :] - b[y0:y1, :]).mean())
        return boton < 4.0 and fila < 4.0

    @staticmethod
    def _boton_cerrar(img):
        """La X de arriba a la derecha o, si la ventana no tiene, su boton
        "Atras" de arriba a la izquierda."""
        x = buscar_cerrar_x(img)
        if x is not None:
            return x
        p, c, _ = localizar(img, "atras")
        h, w = img.shape[:2]
        if p >= 0.72 and c[0] < w * 0.2 and c[1] < h * 0.15:
            return c
        return None

    # iconos de la columna derecha con recompensas propias (no As del
    # Espacio: es de clasificacion y su punto rojo es la configuracion)
    ICONOS_BASE = (("promotion", "Promotion Contract"),
                   ("crecimiento", "Recompensas de crecimiento"),
                   ("pase_nova", "Pase Nova"))

    def _icono_con_aviso(self, img, nombre):
        """Centro del icono si su rotulo esta y tiene punto rojo encima."""
        p, c, _ = localizar(img, nombre)
        if p < 0.80:
            return None
        h, w = img.shape[:2]
        k = w / 1600.0
        zona = ((c[0] - 75 * k) / w, (c[1] - 125 * k) / h, (c[0] + 75 * k) / w, (c[1] - 15 * k) / h)
        if not puntos_rojos(img, zona):
            return None
        return (c[0], int(c[1] - 55 * k))

    def recompensas_base(self) -> int:
        """Promotion Contract, Recompensas de crecimiento y Pase Nova, solo si
        llevan punto rojo."""
        n = 0
        hechos = set()
        for _ in range(len(self.ICONOS_BASE) + 1):
            if self.parado() or not self.ir_a_base():
                break
            img = self.cap("base")
            if localizar(img, "pase_nova")[0] < 0.80:
                p2, c2, _ = localizar(img, "mas_lado")
                if p2 >= 0.85:                       # desplegar la columna "Mas"
                    self.ctrl.tap((c2[0], c2[1] - int(img.shape[0] * 0.055)))
                    time.sleep(1.5)
                    img = self.cap("base")
            sitio = None
            for clave, texto in self.ICONOS_BASE:
                if clave in hechos:
                    continue
                c = self._icono_con_aviso(img, clave)
                if c is not None:
                    sitio = (clave, texto, c)
                    break
            if sitio is None:
                break
            clave, texto, c = sitio
            hechos.add(clave)
            self.log(f"  {texto}: tiene aviso, entro.")
            self.ctrl.tap(c)
            time.sleep(2.8)
            try:
                r = self._dentro()
            except Exception as e:                       # noqa: BLE001
                self.log(f"  Error en {texto}: {e}")
                r = 0
            self.log(f"  {texto}: {r} recompensa(s).")
            n += r
            self._salir()
        return n

    def run(self, ciclos: int = 1):
        self.log("Recompensas de eventos: entro en los que tienen ¡RECOMPENSA!.")
        self._firmas = []
        self.status["estado"] = "yendo a la base"
        if not self.ir_a_base():
            self.log("No encuentro la vista de la base. Dejala abierta y repite.")
            self.status["estado"] = "sin_base"
            return
        for _ in range(self.MAX_EVENTOS):
            if self.parado():
                break
            self.status["estado"] = "lista de eventos"
            if not self._abrir_lista():
                self.log("  No se ha abierto la lista de eventos.")
                break
            punto = self._siguiente_evento()
            if punto is None:
                self.log("  No quedan eventos con ¡RECOMPENSA! por revisar.")
                self._salir()
                break
            self.ctrl.tap(punto)
            time.sleep(2.8)
            self.status["eventos"] += 1
            self.status["estado"] = f"evento {self.status['eventos']}"
            try:
                n = self._dentro()
            except Exception as e:                       # noqa: BLE001
                self.log(f"  Error dentro del evento: {e}")
                n = 0
            self.status["recogidas"] += n
            self.log(f"  Evento {self.status['eventos']}: {n} recompensa(s).")
            if n == 0 and getattr(self, "_mini_actual", None) is not None:
                self._apuntar_sin_nada(self._mini_actual)   # no volver hoy
            self._salir()
        if not self.parado():
            self.status["estado"] = "recompensas de la base"
            self.status["recogidas"] += self.recompensas_base()
        self.volver_a_base()
        self.status["estado"] = "parado" if self.parado() else "terminado"
        self.log(f"Hecho: {self.status['recogidas']} recompensa(s) en "
                 f"{self.status['eventos']} evento(s) y la base.")
