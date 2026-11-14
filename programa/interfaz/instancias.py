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
from interfaz import toasts
from interfaz.tema import (AMBAR, BLANCO, COLORES_INST, ESP_L, ESP_S, ESP_XS, FONDO, NIVEL_COLOR, NIVEL_ICONO, PANEL, PANEL2,
                           ROJO, SUAVE, TAM_M, TAM_S, TAM_XS, TEAL, TEXTO, fuente, texto_estado, titular)
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
                self._sondeado = True
            except Exception:                           # noqa: BLE001
                pass
        if self.adb:
            threading.Thread(target=trabajo, daemon=True).start()
        self.after(15000, self._sondear)

    def _nombres(self) -> dict:
        return leer_prefs().get("nombres", {})

    def _nombres_cuentas(self) -> dict:
        """{puerto: nombre mostrado} de todas las cuentas."""
        n = self._nombres()
        return {str(g.puerto): n.get(str(g.puerto), g.nombre) for g in self.filas}

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

    def _instancias(self, pagina=None):
        """Pestana Instancias: una tarjeta por cuenta."""
        pagina = pagina if pagina is not None else self.zona
        cont = tk.Frame(pagina, bg=FONDO, padx=ESP_L, pady=ESP_S)
        cont.pack(fill="x")
        cab = tk.Frame(cont, bg=FONDO)
        cab.pack(fill="x", pady=(0, ESP_S))
        tk.Label(cab, text="◆  CUENTAS", bg=FONDO, fg=TEAL,
                 font=titular(TAM_M)).pack(side="left")
        b_ = tk.Button(cab, text="↻ Actualizar lista", command=self.refrescar_instancias,
                       bg=FONDO, fg=TEAL, activebackground=FONDO, activeforeground=TEAL,
                       bd=0, relief="flat", font=fuente(TAM_XS), cursor="hand2",
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
                     bg=PANEL, fg=ROJO, font=fuente(TAM_S),
                     padx=ESP_L, pady=ESP_L, justify="left").pack(fill="x")
            return
        for i, (nombre, puerto) in enumerate(inst):
            color = COLORES_INST[i % len(COLORES_INST)]
            f = FilaInstancia(self.lista, nombre, puerto, color)
            f.al_pulsar = self.pulsar_fila
            f.al_parar = self.parar_fila
            f.al_renombrar, f.al_registro, f.al_captura, f.al_ajustes = (
                self._renombrar, self._ver_registro, self._captura_una, self._ajustes_cuenta)
            f.al_parar_acabar, f.al_pausar_min = self._parar_al_acabar, self._pausar_minutos
            f.al_gemas, f.al_releer, f.al_probar = self._recoger_gemas, self._releer_eventos, self._probar_ballena
            f.al_horario = self._horario_cuenta
            f.al_exportar, f.al_importar = self._exportar_ajustes, self._importar_ajustes
            f.nombres_cuentas = self._nombres_cuentas      # para el resumen de ballenas
            f.pack(fill="x", pady=ESP_XS + 1)
            self.filas.append(f)
            self.colores[f"127.0.0.1:{puerto}"] = color
            if "txt" in self.__dict__:
                self.txt_tag(f"127.0.0.1:{puerto}", color)

    def refrescar_instancias(self):
        if any(f.en_marcha() for f in self.filas):
            self.escribir("", "No puedo cambiar la lista mientras haya cuentas en marcha.")
            return
        self._pintar_instancias()
        if hasattr(self, "_refrescar_filtro_cuentas"):
            self._refrescar_filtro_cuentas()            # el filtro del registro, con las cuentas nuevas
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

    def _opciones_de(self, f) -> dict:
        """Las opciones con las que trabaja una cuenta (generales + las suyas)."""
        opc = {"atacar": self.op_atacar.get(), "salto": self.op_salto.get(),
               "dados": self.op_dados.get(), "defensa": self.op_defensa.get(),
               "parar_mision": self.op_mision.get(), "mult": self.op_mult.get(),
               "ascender": self.op_ascender.get(), "roaming_tickets": self._tickets(),
               "normales": self.op_rutina["normales"].get(),
               "que": {k: v.get() for k, v in self.op_rutina.items()},
               "ballenas_dia": self._ballenas_dia(),
               "ballenas": self._cfg_ballenas().get(str(f.puerto), {})}
        a = self.ajustes_de(f.puerto)                    # los ajustes de ESTA cuenta
        opc.update({k: bool(v) for k, v in a["opciones"].items()})
        opc["que"].update({k: bool(v) for k, v in a["rutina"].items()})
        opc["normales"] = bool(opc["que"].get("normales"))
        opc["roaming_tickets"] = int(a.get("tickets", 0) or 0)
        opc["horario"] = dict(a.get("horario") or {})      # franjas en las que no se hace cada tarea
        opc["recoleccion"] = dict(a.get("recoleccion") or {})   # casillas de la tarea «Recolección»
        return opc

    def _firma_ajustes(self, f) -> str:
        import json
        return json.dumps([self._opciones_de(f), f.tarea(), f.n_veces()], sort_keys=True, default=str)

    def empezar_fila(self, f, en_pausa: bool = False):
        partidas = f.n_veces()
        cual = f.tarea()
        f.reset()
        f.estado = None
        opc = self._opciones_de(f)
        f.firma_ajustes = self._firma_ajustes(f)      # para ver si cambian estando en pausa
        f.parada = self.mp.Event()
        f.pausa = self.mp.Event()
        if en_pausa:                     # vuelve a arrancar (version nueva) pero sigue en pausa
            f.pausa.set()
        f.hilo = self.mp.Process(target=trabajo_proceso, daemon=True,
                                 args=(f.puerto, self.adb, cual, partidas, opc,
                                       self.cola_mp, f.parada, f.pausa))
        f.hilo.start()
        f._vivo_pintado = True
        f.marcha(True)
        if en_pausa:
            f.pausado(True)
        unidad = UNIDAD.get(cual)
        lim = (f"{partidas} {unidad}" if partidas else "sin límite") if unidad else SIN_LIMITE.get(cual, "")
        self.escribir(f"127.0.0.1:{f.puerto}", f"Empiezo: {TAREAS[cual]} ({lim}).")

    def pulsar_fila(self, f):
        """En marcha: «Pausar» / «Reanudar» (casi al momento: se congela antes
        del siguiente toque o captura). Parada: «Empezar»."""
        if f.en_marcha():
            pausa = getattr(f, "pausa", None)
            if pausa is None:
                return
            if pausa.is_set():
                if getattr(f, "firma_ajustes", None) not in (None, self._firma_ajustes(f)):
                    # se han guardado ajustes nuevos mientras estaba en pausa: se
                    # vuelve a arrancar con ellos (congelada entre dos acciones,
                    # asi que no se corta nada a medias)
                    self._rearrancar_con_ajustes(f)
                    return
                pausa.clear()
                f.pausado(False)
                self.escribir(f"127.0.0.1:{f.puerto}", "Reanudada: sigue donde estaba.")
            else:
                pausa.set()
                f.pausado(True)
                self.escribir(f"127.0.0.1:{f.puerto}", "En pausa (pulsa «Reanudar» para seguir).")
        else:
            self.empezar_fila(f)

    def _rearrancar_con_ajustes(self, f):
        # se cierra mientras sigue congelada (esperando en la pausa, sin tocar
        # nada): si se soltara antes, podria hacer una ultima accion
        try:
            f.hilo.terminate()
            f.hilo.join(5)
        except Exception:                                   # noqa: BLE001
            pass
        f.pausado(False)
        self.escribir(f"127.0.0.1:{f.puerto}", "Reanudo con los ajustes nuevos.")
        self.empezar_fila(f)

    def parar_fila(self, f, avisar: bool = True):
        """Para una cuenta cuando termine lo que esta haciendo."""
        if not f.en_marcha():
            return
        f.parada.set()
        if getattr(f, "pausa", None) is not None:
            f.pausa.clear()                           # una pausada tambien se para
        f.lbl_estado.config(text="⏳ Parando…", fg=AMBAR)
        if avisar:
            self.escribir(f"127.0.0.1:{f.puerto}", "Parando… (termina lo que está haciendo)")

    def parar(self):
        for f in self.filas:
            self.parar_fila(f, avisar=False)
        self.escribir("", "Parando todas… (cada una termina lo que está haciendo)")

    # ------------------------------------------- acciones de la tarjeta --
    def _parar_al_acabar(self, f):
        """«Parar al acabar lo que está haciendo»: igual que Parar, dicho tal
        cual (no corta a medias el paso en curso)."""
        if not f.en_marcha():
            self.escribir(f"127.0.0.1:{f.puerto}", "Ya está parada.")
            return
        self.parar_fila(f, avisar=False)
        self.escribir(f"127.0.0.1:{f.puerto}",
                      "Pararé al acabar lo que está haciendo (no corto ningún paso a medias).")

    def _pausar_minutos(self, f):
        """Pausa la cuenta y la reanuda sola al cabo de N minutos."""
        from tkinter import simpledialog
        if not f.en_marcha():
            self.escribir(f"127.0.0.1:{f.puerto}", "No está en marcha: no hay nada que pausar.")
            return
        pausa = getattr(f, "pausa", None)
        if pausa is None:
            return
        minutos = simpledialog.askinteger("Pausar", "¿Cuántos minutos?", parent=self,
                                          initialvalue=15, minvalue=1, maxvalue=720)
        if not minutos:
            return
        pausa.set()
        f.pausado(True)
        marca = time.time()
        f._pausa_min = marca
        self.escribir(f"127.0.0.1:{f.puerto}", f"En pausa {minutos} min (se reanuda sola).")

        def reanudar():
            if not f.en_marcha() or getattr(f, "_pausa_min", 0) != marca:
                return                          # la han reanudado o parado a mano: nada que hacer
            if pausa.is_set():
                pausa.clear()
                f.pausado(False)
                self.escribir(f"127.0.0.1:{f.puerto}", "Se acabó la pausa: sigo donde estaba.")
        self.after(int(minutos) * 60000, reanudar)

    def _recoger_gemas(self, f):
        """Orden de recoger las gemas del sistema (ballenas/gemas.json)."""
        import os

        from nucleo import config
        from tareas.ballenas.sync import _carpeta_sync
        try:
            ruta = os.path.join(_carpeta_sync(), "gemas.json")
            config.guardar(ruta, {"t": time.time(), "cuentas": [str(f.puerto)]})
        except Exception as e:                          # noqa: BLE001
            self.escribir(f"127.0.0.1:{f.puerto}", f"ERROR: no puedo pedir las gemas: {e}")
            return
        self.escribir(f"127.0.0.1:{f.puerto}", "Pedido: recoger las gemas del sistema."
                      + ("" if f.en_marcha() else " (no está en marcha: se hará al empezar)."))

    def _releer_eventos(self, f):
        """Pide a la Rutina que vuelva a leer los eventos ya."""
        import os

        from nucleo import config
        from nucleo.rutas import carpeta_datos
        try:
            ruta = os.path.join(carpeta_datos(), "releer_eventos.json")
            config.guardar(ruta, {"t": time.time(), "cuentas": [str(f.puerto)]})
        except Exception as e:                          # noqa: BLE001
            self.escribir(f"127.0.0.1:{f.puerto}", f"ERROR: no puedo pedir la relectura: {e}")
            return
        self.escribir(f"127.0.0.1:{f.puerto}", "Pedido: releer los eventos ahora."
                      + ("" if f.en_marcha() else " (no está en marcha: se leerán al empezar)."))

    def _probar_ballena(self, f):
        """Probar 1 ballena: avisa de que gasta 1 señuelo y pide confirmación."""
        import os

        from nucleo import config
        from cerebro import config_ballenas as cb
        from tkinter import messagebox
        from tareas.ballenas.sync import _carpeta_sync
        p = str(f.puerto)
        nombre = self._nombres().get(p, f.nombre)
        cfg = cb.normalizar(self._cfg_ballenas().get(p, {}))
        if cfg["rol"] == "no":
            messagebox.showinfo("Probar 1 ballena",
                                f"{nombre} no tiene las ballenas configuradas.\n"
                                "Actívalas en Ajustes > Ballenas.", parent=self)
            return
        if cfg["rol"] == "sola":
            lider, apoyo = p, ""
        elif cfg["rol"] == "invoca":
            lider, apoyo = p, cfg["con"]
        else:
            lider, apoyo = cfg["con"], p
        pareja = self._nombres().get(apoyo, apoyo) if apoyo else ""
        if not lider:
            messagebox.showinfo("Probar 1 ballena",
                                "Esta cuenta es la que ayuda: la prueba la pide la cuenta que invoca.\n"
                                "Elige su pareja en Ajustes > Ballenas.", parent=self)
            return
        texto = (f"Se gastará 1 Señuelo de éter de {nombre}"
                 + (f" y {pareja} le ayudará a matarla." if pareja else " y la matará ella sola.")
                 + "\n\n¿Probar ahora?")
        if not messagebox.askyesno("Probar 1 ballena", texto, parent=self):
            return
        try:
            ruta = os.path.join(_carpeta_sync(), "prueba.json")
            config.guardar(ruta, {"t": time.time(), "hecho": 0, "fallos": 0,
                                  "turnos": [{"lider": lider, "apoyo": apoyo}]})
        except Exception as e:                          # noqa: BLE001
            self.escribir(f"127.0.0.1:{p}", f"ERROR: no puedo pedir la prueba: {e}")
            return
        self.escribir(f"127.0.0.1:{p}", "Prueba de ballenas pedida: 1 señuelo"
                      + (f" (con {pareja})" if pareja else "") + ".")
        if not f.en_marcha():
            self.empezar_fila(f)                        # la Rutina hará la prueba en cuanto arranque

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
                f.lbl_estado.config(text="✖ Parada de emergencia", fg=ROJO)
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
            if inst == "__aviso__":                 # aviso emergente desde otro hilo: «nivel|texto»
                nivel, _, texto = msg.partition("|")
                toasts.avisar(texto, nivel)
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
            # se compara con lo ultimo pintado (no con el texto del boton, que
            # ahora es «Pausar»/«Reanudar»: repintarlo cada vez quitaba la pausa
            # y nunca se veia que una cuenta se habia cerrado para actualizarse)
            if vivo != getattr(f, "_vivo_pintado", False):
                f._vivo_pintado = vivo
                f.marcha(vivo)
                if not vivo and getattr(f, "actualizar", False) and not self._relanzando:
                    f.actualizar = False
                    en_pausa = getattr(f, "_pausa_antes", False)
                    self.escribir(f"127.0.0.1:{f.puerto}", "Sigo con la versión nueva"
                                  + (" (en pausa, como estaba)." if en_pausa else "."))
                    self.empezar_fila(f, en_pausa=en_pausa)
                    continue
                if not vivo and f.hilo is not None:
                    nombre = self._nombres().get(str(f.puerto), f.nombre)
                    self.escribir(f"127.0.0.1:{f.puerto}", "Terminado.")
                    if f.estado is None or f.estado.get("estado") not in ("terminado", "parado"):
                        f.lbl_estado.config(text="✔ Terminado", fg=SUAVE)
                    toasts.avisar(f"{nombre}: tarea acabada.", "ok")
                    f.punto.config(fg=f.color)
            else:
                f.refrescar_tiempo()
        self.b_parar.config(state="normal" if en_marcha else "disabled")
        self.b_parar.color(ROJO if en_marcha else PANEL2, BLANCO if en_marcha else TEXTO)
        self._n_tick = getattr(self, "_n_tick", 0) + 1
        if self._n_tick % 7 == 1:                       # ~ cada 2 s
            self._actualizar_panel()
            self._puente_panel()
            self._vigilar_avisos()
        if (self._n_tick % 20 == 1 and hasattr(self, "graficas")
                and getattr(getattr(self, "pestanas", None), "actual", "") == "estadisticas"):
            self.graficas.actualizar(self._nombres_cuentas())     # ~ cada 6 s, solo si se esta viendo
        if (self._n_tick % 7 == 1 and hasattr(self, "salud")
                and getattr(getattr(self, "pestanas", None), "actual", "") == "salud"):
            self.salud.actualizar()                              # ~ cada 2 s, solo si se esta viendo
        if (self._n_tick % 7 == 1 and hasattr(self, "guia")
                and getattr(getattr(self, "pestanas", None), "actual", "") == "guia"):
            self.guia.actualizar()                               # ADB e instancias de la guia
        if self._n_tick % 4 == 1:                       # ~ cada 1 s: cuentas atras
            self._pintar_eventos()
        res = f"{en_marcha} de {len(self.filas)} en marcha" if self.filas else ""
        if ataques:
            res += f"  ·  {ataques} {'ataque' if ataques == 1 else 'ataques'}"
        self.lbl_resumen.config(text=res)
        self.after(300, self._refrescar)

    # -------------------------------------------------- avisos y estado general --
    def _vigilar_avisos(self):
        """Cada ~2 s: avisa (toast) de una cuenta que pierde la conexion o se
        atasca, y pone el estado general de la cabecera."""
        avisos = errores = 0
        for f in self.filas:
            dev = f"127.0.0.1:{f.puerto}"
            nombre = self._nombres().get(str(f.puerto), f.nombre)
            estado = (f.estado or {}).get("estado", "")
            f.sin_conexion = bool(f.en_marcha() and (estado == "sin conexión" or (
                getattr(self, "_sondeado", False) and dev not in self.conectadas)))
            if f.sin_conexion:
                if not getattr(f, "_avisado_conn", False):
                    f._avisado_conn = True
                    toasts.avisar(f"{nombre}: sin conexión con BlueStacks.", "error")
            else:
                f._avisado_conn = False
            nivel = f.nivel()
            errores += nivel == "error"
            avisos += nivel == "aviso"
            if nivel == "error" and not f.sin_conexion and estado != getattr(f, "_estado_avisado", ""):
                toasts.avisar(f"{nombre}: {texto_estado(estado)}.", "error")
            f._estado_avisado = estado if nivel == "error" else ""
        if not self.adb:
            errores += 1
        errores += getattr(self, "_errores_repetidos", 0)
        if errores:
            self._estado_general = ("error", f"{errores} {'error' if errores == 1 else 'errores'}")
        elif avisos:
            self._estado_general = ("aviso", f"{avisos} {'aviso' if avisos == 1 else 'avisos'}")
        else:
            self._estado_general = ("ok", "Todo bien")
        nivel, texto = self._estado_general
        self.cielo.lbl_general.config(text=f"{NIVEL_ICONO[nivel]} {texto}", fg=NIVEL_COLOR[nivel])

    def _contar_error(self, inst: str, msg: str):
        """Llamado por el registro con cada mensaje: tres «ERROR» de una misma
        cuenta en dos minutos = error repetido (aviso emergente)."""
        if not msg.startswith("ERROR"):
            return
        ahora = time.time()
        recientes = [t for t in self._errores_t.get(inst, []) if ahora - t < 120] + [ahora]
        self._errores_t[inst] = recientes
        if len(recientes) >= 3:
            nombre = next((self._nombres().get(str(f.puerto), f.nombre) for f in self.filas
                           if f"127.0.0.1:{f.puerto}" == inst), inst or "NovaBot")
            toasts.avisar(f"{nombre}: error repetido ({len(recientes)} en 2 min). Mira el Registro.", "error")
            self._errores_repetidos = 1
            self.after(120000, lambda: setattr(self, "_errores_repetidos", 0))
