"""Instancias de BlueStacks: deteccion, tarjetas, empezar/parar y capturas."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk

from nucleo import adb
from tareas import roaming
from interfaz.catalogo import SIN_LIMITE, TAREAS, UNIDAD
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tarjeta import FilaInstancia
from interfaz.tema import (AMBAR, BLANCO, COLORES_INST, FONDO, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, titular)
from interfaz.trabajador import trabajo_proceso
from interfaz.widgets import Ayuda


class _Instancias:
    """Instancias de BlueStacks: deteccion, tarjetas, empezar/parar y capturas."""

    def _sondear(self):
        """Cada 15 s mira con `adb devices` que instancias estan conectadas."""
        def trabajo():
            import subprocess
            import sys
            try:
                fl = 0x08000000 if sys.platform == "win32" else 0
                out = subprocess.run([self.adb, "devices"], capture_output=True, text=True,
                                     timeout=8, creationflags=fl).stdout
                self.conectadas = {ln.split()[0] for ln in out.splitlines()[1:] if "\tdevice" in ln}
            except Exception:                           # noqa: BLE001
                pass
        if self.adb:
            threading.Thread(target=trabajo, daemon=True).start()
        self.after(15000, self._sondear)

    def _nombres(self) -> dict:
        return leer_prefs().get("nombres", {})

    def _renombrar(self, f):
        from tkinter import simpledialog
        actual = self._nombres().get(str(f.puerto), f.nombre)
        nuevo = simpledialog.askstring("Nombre de la cuenta", "Nombre para esta cuenta "
                                       "(vacío = el de BlueStacks):", initialvalue=actual, parent=self)
        if nuevo is None:
            return
        d = leer_prefs()
        d.setdefault("nombres", {})
        if nuevo.strip():
            d["nombres"][str(f.puerto)] = nuevo.strip()[:30]
        else:
            d["nombres"].pop(str(f.puerto), None)
        guardar_prefs(d)
        f.lbl_nombre.config(text=d["nombres"].get(str(f.puerto), f.nombre))

    def _instancias(self):
        cont = tk.Frame(self.zona, bg=FONDO, padx=20)
        cont.pack(fill="x")
        cab = tk.Frame(cont, bg=FONDO)
        cab.pack(fill="x", pady=(0, 6))
        tk.Label(cab, text="◆  CUENTAS", bg=FONDO, fg=TEAL,
                 font=titular(10)).pack(side="left")
        b_ = tk.Button(cab, text="↻ Actualizar lista", command=self.refrescar_instancias,
                       bg=FONDO, fg=TEAL, activebackground=FONDO, activeforeground=TEAL,
                       bd=0, relief="flat", font=("Segoe UI", 8), cursor="hand2",
                       padx=0, pady=0)
        b_.pack(side="right")
        Ayuda(b_, "Vuelve a leer las cuentas (instancias) de BlueStacks.")
        self.lista = tk.Frame(cont, bg=FONDO)
        self.lista.pack(fill="x")
        self.filas: list[FilaInstancia] = []
        self._pintar_instancias()

    def _pintar_instancias(self):
        for w in list(self.lista.winfo_children() or []):
            w.destroy()
        self.filas = []
        inst = adb.leer_instancias()
        if not inst:
            tk.Label(self.lista, text="No he encontrado ninguna instancia de BlueStacks.\n"
                                      "Comprueba que BlueStacks 5 esté instalado.",
                     bg=PANEL, fg=ROJO, font=("Segoe UI", 9),
                     padx=14, pady=12, justify="left").pack(fill="x")
            return
        for i, (nombre, puerto) in enumerate(inst):
            color = COLORES_INST[i % len(COLORES_INST)]
            f = FilaInstancia(self.lista, nombre, puerto, color)
            f.al_pulsar = self.pulsar_fila
            f.al_renombrar, f.al_registro, f.al_captura, f.al_ajustes = (
                self._renombrar, self._ver_registro, self._captura_una, self._ajustes_cuenta)
            f.pack(fill="x", pady=4)
            self.filas.append(f)
            self.colores[f"127.0.0.1:{puerto}"] = color
            if "txt" in self.__dict__:
                self.txt_tag(f"127.0.0.1:{puerto}", color)

    def refrescar_instancias(self):
        if any(f.en_marcha() for f in self.filas):
            self.escribir("", "No puedo cambiar la lista mientras haya cuentas en marcha.")
            return
        self._pintar_instancias()
        self.escribir("", f"Lista releída de BlueStacks: {len(self.filas)} {"cuenta" if len(self.filas) == 1 else "cuentas"}.")

    def _seleccionadas(self) -> list[FilaInstancia]:
        return [f for f in self.filas if f.activa.get()]

    def empezar(self):
        sel = [f for f in self._seleccionadas() if not f.en_marcha()]
        if not sel:
            self.escribir("", "No hay ninguna cuenta marcada y parada para empezar.")
            return
        for f in sel:
            self.empezar_fila(f)

    def empezar_fila(self, f):
        partidas = f.n_veces()
        cual = f.tarea()
        f.reset()
        f.estado = None
        opc = {"atacar": self.op_atacar.get(), "salto": self.op_salto.get(),
               "dados": self.op_dados.get(), "defensa": self.op_defensa.get(),
               "parar_mision": self.op_mision.get(), "mult": self.op_mult.get(),
               "ascender": self.op_ascender.get(), "roaming_tickets": self._tickets(),
               "normales": self.op_rutina["normales"].get(),
               "que": {k: v.get() for k, v in self.op_rutina.items()},
               "ballenas_dia": self._ballenas_dia(),
               "ballenas": self._cfg_ballenas().get(str(f.puerto), {})}
        propios = leer_prefs().get("cuentas", {}).get(str(f.puerto), {})
        if propios.get("propios"):                       # ajustes propios de esta cuenta
            opc.update({k: bool(v) for k, v in propios.get("opciones", {}).items()})
            opc["que"].update({k: bool(v) for k, v in propios.get("rutina", {}).items()})
            opc["normales"] = bool(opc["que"].get("normales"))
            opc["roaming_tickets"] = int(propios.get("tickets", 0) or 0)
        f.parada = self.mp.Event()
        f.hilo = self.mp.Process(target=trabajo_proceso, daemon=True,
                                 args=(f.puerto, self.adb, cual, partidas, opc,
                                       self.cola_mp, f.parada))
        f.hilo.start()
        f.marcha(True)
        unidad = UNIDAD.get(cual)
        lim = (f"{partidas} {unidad}" if partidas else "sin límite") if unidad else SIN_LIMITE.get(cual, "")
        self.escribir(f"127.0.0.1:{f.puerto}", f"Empiezo: {TAREAS[cual]} ({lim}).")

    def pulsar_fila(self, f):
        if f.en_marcha():
            f.parada.set()
            f.lbl_estado.config(text="Parando…", fg=AMBAR)
            self.escribir(f"127.0.0.1:{f.puerto}", "Parando… (termina lo que está haciendo)")
        else:
            self.empezar_fila(f)

    def parar(self):
        for f in self.filas:
            if f.en_marcha():
                f.parada.set()
                f.lbl_estado.config(text="Parando…", fg=AMBAR)
        self.escribir("", "Parando todas… (cada una termina lo que está haciendo)")

    def emergencia(self):
        """Corta YA todas las tareas (sin esperar al paso en curso)."""
        n = 0
        for f in self.filas:
            if f.en_marcha():
                n += 1
                try:
                    f.parada.set()
                    f.hilo.terminate()
                except Exception:                    # noqa: BLE001
                    pass
                f.lbl_estado.config(text="Parada de emergencia", fg=ROJO)
        self.escribir("", f"PARADA DE EMERGENCIA: {n} {'tarea cortada' if n == 1 else 'tareas cortadas'}. "
                          "Revisa que el juego no se haya quedado a medias en alguna pantalla.")

    def comprobar(self):
        sel = self._seleccionadas()
        if not sel:
            self.escribir("", "No has marcado ninguna cuenta.")
            return
        self.b_check.config(state="disabled")
        threading.Thread(target=self._comprobar, args=(sel,), daemon=True).start()

    def captura(self):
        """Guarda lo que se ve ahora en cada instancia marcada.
        Va a %LOCALAPPDATA%\\NovaBot\\capturas, fuera de la carpeta del bot."""
        sel = self._seleccionadas()
        if not sel:
            self.escribir("", "No has marcado ninguna cuenta.")
            return
        # una hebra por instancia: una instancia apagada (que tarda en dar
        # error) no retrasa ni bloquea las capturas de las demas
        hora = time.strftime("%Y%m%d_%H%M%S")
        for f in sel:
            threading.Thread(target=self._captura, args=([f], hora), daemon=True).start()

    def _captura(self, sel, hora=None):
        import os
        import cv2
        from nucleo.rutas import carpeta_datos
        carpeta = os.path.join(carpeta_datos(), "capturas")
        os.makedirs(carpeta, exist_ok=True)
        hora = hora or time.strftime("%Y%m%d_%H%M%S")
        for f in sel:
            dev = f"127.0.0.1:{f.puerto}"
            try:
                img = adb.AdbController(dev, self.adb).capture()
                ruta = os.path.join(carpeta, f"{f.puerto}_{hora}.png")
                cv2.imwrite(ruta, img)
                cv2.imwrite(os.path.join(carpeta, f"ultima_{f.puerto}.png"), img)
                self.cola.put((dev, f"Captura guardada: {os.path.basename(ruta)}"))
            except Exception as e:                  # noqa: BLE001
                self.cola.put((dev, f"ERROR: {e}"))

    def _captura_una(self, f):
        threading.Thread(target=self._captura, args=([f], time.strftime("%Y%m%d_%H%M%S")),
                         daemon=True).start()

    def _comprobar(self, sel):
        for f in sel:
            dev = f"127.0.0.1:{f.puerto}"
            try:
                ctrl = adb.AdbController(dev, self.adb)
                img = ctrl.capture()
                g = roaming.detect_grid(img)
                if g is None:
                    self.cola.put((dev, "No veo el tablero: abre el Roaming Test."))
                    continue
                tab = roaming.read_board(img, g)
                n = roaming.unknown_count(tab)
                self.cola.put((dev, f"Tablero de {g.rows}×{g.cols}, casillas de "
                                    f"{g.dx:.0f}×{g.dy:.0f} px, sin identificar: {n}"))
                for linea in roaming.board_str(tab).split("\n"):
                    self.cola.put(("", "   " + linea))
            except Exception as e:                  # noqa: BLE001
                self.cola.put((dev, f"ERROR: {e}"))
        self.cola.put(("__fin_check__", ""))

    # ------------------------------------------------------------ refresco --
    def _refrescar(self):
        while True:
            try:
                inst, msg = self.cola.get_nowait()
            except queue.Empty:
                break
            if inst == "__fin_check__":
                self.b_check.config(state="normal")
                continue
            self.escribir(inst, msg)

        for _ in range(300):
            try:
                tipo, a, b = self.cola_mp.get_nowait()
            except Exception:                       # noqa: BLE001  (vacia)
                break
            if tipo == "log":
                self.escribir(a, b.strip())
            else:
                for f in self.filas:
                    if f.puerto == a:
                        f.estado = b
        en_marcha, ataques = 0, 0
        for f in self.filas:
            if f.estado:
                f.pintar(f.estado)
                if f.tarea() == "mixto":
                    ataques += f.estado.get("normales", 0) + f.estado.get("sigilo", 0)
                elif f.tarea() == "normales":
                    ataques += f.estado.get("ciclo", 0)
                else:
                    ataques += f.estado.get("atacados", 0)
            vivo = f.en_marcha()
            en_marcha += vivo
            if vivo != (f.b_fila.cget("text") == "■  Parar"):
                f.marcha(vivo)
                if not vivo and getattr(f, "actualizar", False) and not self._relanzando:
                    f.actualizar = False
                    self.escribir(f"127.0.0.1:{f.puerto}", "Sigo con la versión nueva.")
                    self.empezar_fila(f)
                    continue
                if not vivo and f.hilo is not None:
                    self.escribir(f"127.0.0.1:{f.puerto}", "Terminado.")
                    if f.estado is None or f.estado.get("estado") not in ("terminado", "parado"):
                        f.lbl_estado.config(text="Terminado", fg=SUAVE)
                    f.punto.config(fg=SUAVE)
        self.b_parar.config(state="normal" if en_marcha else "disabled")
        self.b_parar.color(ROJO if en_marcha else PANEL2, BLANCO if en_marcha else TEXTO)
        self._n_tick = getattr(self, "_n_tick", 0) + 1
        if self._n_tick % 7 == 1:                       # ~ cada 2 s
            self._actualizar_panel()
            self._puente_panel()
        if self._n_tick % 4 == 1:                       # ~ cada 1 s: cuentas atras
            self._pintar_eventos()
        res = f"{en_marcha} de {len(self.filas)} en marcha" if self.filas else ""
        if ataques:
            res += f"  ·  {ataques} {'ataque' if ataques == 1 else 'ataques'}"
        self.lbl_resumen.config(text=res)
        self.after(300, self._refrescar)
