"""Ajustes de cada cuenta (boton «Ajustes» de su tarjeta).

Ya no hay caja de AJUSTES generales en la ventana: cada cuenta tiene los
suyos (Rutina, Piratas, Ballenas, Opciones). Los valores generales que
habia guardados quedan solo como punto de partida de las cuentas que aun
no tienen los suyos (y para el panel remoto).
"""
from __future__ import annotations

import tkinter as tk

from cerebro import config_ballenas as _cb
from cerebro import memoria_eventos
from interfaz import panel
from interfaz.preferencias import guardar_prefs, leer_prefs

#  version de los ajustes: 2 = solo ajustes por cuenta
AJUSTES_V = 2


class _Ajustes:
    """Ajustes de cada cuenta y la configuracion de ballenas."""

    def _ajustes(self):
        """Carga los valores generales (punto de partida de cada cuenta) y pasa
        a cada cuenta los ajustes que estaba usando."""
        prefs = leer_prefs()
        op = prefs.get("opciones", {})
        self.op_atacar = tk.BooleanVar(value=op.get("atacar", True))
        self.op_salto = tk.BooleanVar(value=op.get("salto", True))
        self.op_dados = tk.BooleanVar(value=op.get("dados", True))
        self.op_defensa = tk.BooleanVar(value=op.get("defensa", True))
        self.op_mision = tk.BooleanVar(value=op.get("parar_mision", True))
        self.op_mult = tk.BooleanVar(value=op.get("mult", True))
        self.op_ascender = tk.BooleanVar(value=op.get("ascender", True))
        self.op_ballenas = tk.IntVar(value=int(op.get("ballenas_dia", 2) or 0))
        self.op_tickets = tk.IntVar(value=int(op.get("roaming_tickets", 0) or 0))
        guardadas = prefs.get("rutina", {})
        self.op_rutina = {k: tk.BooleanVar(value=bool(guardadas.get(k, k in panel._POR_DEFECTO)))
                          for k, _ in panel.PASOS_CUENTA}
        self._migrar_ajustes()

    def _migrar_ajustes(self):
        """Antes cada cuenta usaba los ajustes generales salvo que tuviera
        «ajustes propios». Ahora todo es por cuenta: la que no los tenia pasa
        a usar, como suyos, los generales que estaba usando."""
        d = leer_prefs()
        if d.get("ajustes_v") == AJUSTES_V:
            return
        gen = self._generales()
        for p, c in (d.get("cuentas") or {}).items():
            if not isinstance(c, dict):
                continue
            if c.get("propios"):
                c["opciones"] = {**gen["opciones"], **(c.get("opciones") or {})}
                c["rutina"] = {**gen["rutina"], **(c.get("rutina") or {})}
            else:
                c["opciones"] = dict(gen["opciones"])
                c["rutina"] = dict(gen["rutina"])
                c["tickets"] = gen["tickets"]
            c.pop("propios", None)
        d["ajustes_v"] = AJUSTES_V
        d.pop("ajustes_abiertos", None)
        guardar_prefs(d)

    def _generales(self) -> dict:
        """Los valores generales, en el mismo formato que los de cada cuenta."""
        return {"opciones": {"salto": self.op_salto.get(), "defensa": self.op_defensa.get(),
                             "dados": self.op_dados.get(), "mult": self.op_mult.get(),
                             "ascender": self.op_ascender.get()},
                "rutina": {k: v.get() for k, v in self.op_rutina.items()},
                "tickets": self._tickets()}

    def ajustes_de(self, puerto) -> dict:
        """Los ajustes que usa una cuenta: los suyos y, si le falta alguno,
        el valor general."""
        gen = self._generales()
        c = (leer_prefs().get("cuentas") or {}).get(str(puerto), {}) or {}
        return {"opciones": {**gen["opciones"], **(c.get("opciones") or {})},
                "rutina": {**gen["rutina"], **(c.get("rutina") or {})},
                "tickets": int(c.get("tickets", gen["tickets"]) or 0),
                "horario": dict(c.get("horario") or {}),
                "recoleccion": {**panel.RECOLECCION_DEFECTO, **(c.get("recoleccion") or {})}}

    def _guardar_cuenta(self, puerto, campo, valor):
        """Cambia un ajuste de la Rutina de una cuenta (lo usa el panel remoto)."""
        d = leer_prefs()
        c = d.setdefault("cuentas", {}).setdefault(str(puerto), {})
        c.setdefault("rutina", {})[campo] = valor
        guardar_prefs(d)

    def _ajustes_cuenta(self, f):
        p = str(f.puerto)
        nombres = self._nombres()
        nombre = nombres.get(p, f.nombre)
        otras = [(str(g.puerto), nombres.get(str(g.puerto), g.nombre)) for g in self.filas
                 if str(g.puerto) != p]

        def guardar(d):
            prefs = leer_prefs()
            c = prefs.setdefault("cuentas", {}).setdefault(p, {})   # se conserva el horario y lo demas
            c.update({"opciones": d["opciones"], "rutina": d["rutina"], "tickets": d["tickets"]})
            if isinstance(d.get("recoleccion"), dict):
                c["recoleccion"] = d["recoleccion"]
            guardar_prefs(prefs)
            otra = self._guardar_pareja(p, d["ballenas"], d["rutina"].get("ballenas"))
            self.escribir(f"127.0.0.1:{f.puerto}", "Ajustes guardados." +
                          (f" Ballenas: emparejada con {nombres.get(otra, otra)}." if otra else ""))
            f.pintar_ballenas()                # el resumen de la tarjeta, al momento
        try:                                   # progreso de eventos de ESTA cuenta
            eventos = memoria_eventos.Memoria(f"127.0.0.1:{f.puerto}").resumen()
        except Exception:                                   # noqa: BLE001
            eventos = []
        def obtener():                        # la pestaña Eventos se refresca sola
            return memoria_eventos.Memoria(f"127.0.0.1:{f.puerto}").resumen()
        panel.ventana_ajustes_cuenta(self, self.tema, nombre,
                                     {**self.ajustes_de(p), "eventos": eventos, "obtener_eventos": obtener,
                                      "pestana": {"ballenas": "Ballenas", "recoleccion": "Recolección"}.get(f.tarea(), "")},
                                     guardar, cuentas=otras, ballenas=self._cfg_ballenas().get(p, {}))

    # ------------------------------------------------------ ballenas --
    def _cfg_ballenas(self) -> dict:
        """{puerto: {"rol": invoca/apoya/no, "con": puerto, "robots": n, "dia": n}}"""
        cfg = leer_prefs().get("ballenas")
        return cfg if isinstance(cfg, dict) else {}

    def _guardar_cfg_ballenas(self, cfg):
        d = leer_prefs()
        d["ballenas"] = cfg
        guardar_prefs(d)

    def _guardar_pareja(self, p, c, activas) -> str:
        """Guarda las ballenas de la cuenta p y deja coherente la pareja: si p
        invoca con B, B apoya a p (y al reves), y B tiene las ballenas
        activadas. Si p deja la pareja, la otra tambien. Devuelve B."""
        cfg = self._cfg_ballenas()
        con, avisos = _cb.aplicar(cfg, p, c)      # (guarda tambien los minimos de escombros)      # la logica de parejas es comun (tambien el panel remoto)
        self._guardar_cfg_ballenas(cfg)
        if avisos:
            self.escribir("", "Ballenas: " + "; ".join(avisos) + ".")
        if con and activas:
            self._guardar_cuenta(con, "ballenas", True)
        return con

    def _pintar_ballenas(self):
        """(Antes pintaba la caja de AJUSTES; queda por compatibilidad.)"""

    def _ballenas_dia(self) -> int:
        try:
            return max(0, int(self.op_ballenas.get()))
        except (ValueError, tk.TclError, AttributeError):
            return 0

    def _tickets(self) -> int:
        try:
            return max(0, int(self.op_tickets.get()))
        except (ValueError, tk.TclError, AttributeError):
            return 0

    def _guardar_opciones(self):
        d = leer_prefs()
        d["opciones"] = {"atacar": self.op_atacar.get(), "salto": self.op_salto.get(),
                         "dados": self.op_dados.get(), "defensa": self.op_defensa.get(),
                         "parar_mision": self.op_mision.get(),
                         "mult": self.op_mult.get(), "ascender": self.op_ascender.get(),
                         "roaming_tickets": self._tickets(),
                         "ballenas_dia": self._ballenas_dia()}
        guardar_prefs(d)

    def _guardar_rutina(self):
        d = leer_prefs()
        d["rutina"] = {k: v.get() for k, v in self.op_rutina.items()}
        guardar_prefs(d)

    # ------------------------------------------------- horario y archivo --
    def _guardar_horario(self, puerto, horario: dict):
        """Guarda las franjas de no hacer de una cuenta (vacias = borrar)."""
        d = leer_prefs()
        c = d.setdefault("cuentas", {}).setdefault(str(puerto), {})
        if horario:
            c["horario"] = horario
        else:
            c.pop("horario", None)
        guardar_prefs(d)

    def _horario_cuenta(self, f):
        """Dialogo de franjas (p.ej. sin piratas de 2 a 8)."""
        from interfaz.horario import ventana_horario
        p = str(f.puerto)

        def guardar(horario):
            from interfaz.horario import TAREAS_HORARIO
            self._guardar_horario(p, horario)
            nombres_t = dict(TAREAS_HORARIO)
            cola = "; ".join(f"{nombres_t.get(k, k)}: " + ", ".join(f"{a}-{b}" for a, b in fr)
                             for k, fr in horario.items() if fr)
            self.escribir(f"127.0.0.1:{f.puerto}", "Horario guardado: "
                          + (cola or "ninguna tarea limitada")
                          + (" Cambia al volver a empezar esta cuenta." if f.en_marcha()
                             else " Se aplica al empezar."))
        ventana_horario(self, self.tema, self._nombres().get(p, f.nombre),
                        self.ajustes_de(p).get("horario") or {}, guardar)

    def _datos_exportar(self, puerto) -> dict:
        """Los ajustes de una cuenta tal cual, para copiarlos a otra cuenta."""
        a = self.ajustes_de(puerto)
        return {"programa": "NovaBot", "formato": 1,
                "opciones": a["opciones"], "rutina": a["rutina"],
                "tickets": a["tickets"], "horario": a.get("horario") or {},
                "recoleccion": a.get("recoleccion") or {},
                "ballenas": self._cfg_ballenas().get(str(puerto), {})}

    def _exportar_ajustes(self, f):
        """Guardar los ajustes de esta cuenta en un .json."""
        import json
        import os
        from tkinter import filedialog
        p = str(f.puerto)
        ruta = filedialog.asksaveasfilename(
            parent=self, title=f"Exportar ajustes de {self._nombres().get(p, f.nombre)}",
            defaultextension=".json", initialfile=f"novabot_ajustes_{p}.json",
            filetypes=[("Ajustes de NovaBot", "*.json"), ("Todos los archivos", "*.*")])
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump(self._datos_exportar(p), fh, ensure_ascii=False, indent=1)
        except OSError as e:
            self.escribir(f"127.0.0.1:{p}", f"ERROR: no puedo guardar el archivo: {e}")
            return
        self.escribir(f"127.0.0.1:{p}", f"Ajustes exportados: {os.path.basename(ruta)}.")

    def _importar_ajustes(self, f):
        """Poner en esta cuenta los ajustes de un .json exportado."""
        import json
        import os
        from tkinter import filedialog, messagebox
        p = str(f.puerto)
        nombre = self._nombres().get(p, f.nombre)
        ruta = filedialog.askopenfilename(
            parent=self, title=f"Importar ajustes en {nombre}",
            filetypes=[("Ajustes de NovaBot", "*.json"), ("Todos los archivos", "*.*")])
        if not ruta:
            return
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError) as e:
            self.escribir(f"127.0.0.1:{p}", f"ERROR: el archivo no sirve: {e}")
            return
        if not isinstance(d, dict) or not (isinstance(d.get("opciones"), dict)
                                          or isinstance(d.get("rutina"), dict)):
            self.escribir(f"127.0.0.1:{p}", "ERROR: el archivo no tiene ajustes de NovaBot.")
            return
        if not messagebox.askyesno("Importar ajustes",
                                   f"¿Cambiar los ajustes de {nombre} por los de\n"
                                   f"{os.path.basename(ruta)}?\n\nLos de ahora se pierden.",
                                   parent=self):
            return
        prefs = leer_prefs()
        c = prefs.setdefault("cuentas", {}).setdefault(p, {})
        if isinstance(d.get("opciones"), dict):
            c["opciones"] = dict(d["opciones"])
        if isinstance(d.get("rutina"), dict):
            c["rutina"] = dict(d["rutina"])
        if "tickets" in d:
            try:
                c["tickets"] = max(0, int(d["tickets"]))
            except (TypeError, ValueError):
                pass
        if isinstance(d.get("recoleccion"), dict):
            c["recoleccion"] = dict(d["recoleccion"])
        if isinstance(d.get("horario"), dict):
            if d["horario"]:
                c["horario"] = dict(d["horario"])
            else:
                c.pop("horario", None)
        guardar_prefs(prefs)
        if isinstance(d.get("ballenas"), dict) and d["ballenas"]:
            activas = (d.get("rutina") or {}).get("ballenas") if isinstance(d.get("rutina"), dict) else None
            self._guardar_pareja(p, d["ballenas"], activas)
        f.pintar_ballenas()
        self.escribir(f"127.0.0.1:{p}", f"Ajustes importados: {os.path.basename(ruta)}."
                      + ("" if f.en_marcha() else " Se aplican al empezar."))
