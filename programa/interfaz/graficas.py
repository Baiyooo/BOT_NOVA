"""Graficas sencillas de las estadisticas, dibujadas en Canvas (sin librerias
nuevas): por dia y por cuenta, con los datos de estadisticas.json.

Se pueden ver piratas (sigilo + normales), gemas, ballenas, errores y horas en
marcha, en los ultimos 7, 14 o 30 dias. Se redibuja solo al cambiar de tamano
o al pulsar «Actualizar» (la ventana tambien lo refresca cada pocos segundos)."""
from __future__ import annotations

import time
import tkinter as tk

from nucleo import estadisticas
from interfaz.tema import (AMBAR, BORDE, ESP_L, ESP_M, ESP_S, ESP_XS, PANEL2, SUAVE, TAM_M, TAM_S,
                           TAM_XS, TEAL, TEXTO, VIOLETA, fuente, titular)
from interfaz.widgets import Ayuda

#  clave de la metrica -> como se llama
METRICAS = (("piratas", "Piratas (sigilo + normales)"), ("gemas", "Gemas recogidas"),
            ("ballenas", "Ballenas"), ("errores", "Errores"), ("segundos", "Horas en marcha"))
RANGOS = (7, 14, 30)


def valor_metrica(fila: dict, metrica: str) -> float:
    """El numero de una metrica en una fila de estadisticas (horas, si toca)."""
    if metrica == "piratas":
        return float(fila.get("sigilo", 0)) + float(fila.get("normales", 0))
    if metrica == "segundos":
        return float(fila.get("segundos", 0)) / 3600.0
    return float(fila.get(metrica, 0) or 0)


def _texto_valor(v: float, metrica: str) -> str:
    if metrica == "segundos":
        return f"{v:.1f} h".replace(".", ",")
    return str(int(round(v)))


class Graficas(tk.Frame):
    """Dos lienzos: una metrica por dia y la misma metrica por cuenta."""

    ALTO_DIA, ALTO_CUENTA = 132, 118

    def __init__(self, master, tema):
        super().__init__(master, bg=tema["FONDO"], padx=ESP_L)
        self.t = tema
        self.rango = tk.StringVar(value="14 días")
        self.metrica = tk.StringVar(value="piratas")
        self._dias: list[tuple[str, float]] = []
        self._cuentas: list[tuple[str, float]] = []
        self._ultimo = 0.0

        cab = tk.Frame(self, bg=tema["FONDO"])
        cab.pack(fill="x", pady=(0, ESP_S))
        tk.Label(cab, text="◆  GRÁFICAS", bg=tema["FONDO"], fg=tema["TEAL"],
                 font=titular(TAM_M)).pack(side="left")
        b = tk.Button(cab, text="↻ Actualizar", bg=tema["FONDO"], fg=TEAL, activebackground=tema["FONDO"],
                      activeforeground=TEXTO, bd=0, relief="flat", cursor="hand2",
                      font=fuente(TAM_S), command=lambda: self.actualizar(self._nombres, forzar=True))
        b.pack(side="right")
        Ayuda(b, "Vuelve a leer estadisticas.json y redibuja las gráficas.")
        self._nombres: dict = {}
        self.om_met = tk.OptionMenu(cab, self.metrica, *(m for m, _ in METRICAS))
        self._menu(self.om_met, {m: t for m, t in METRICAS})
        self.om_met.config(bg=PANEL2, fg=TEXTO, activebackground=BORDE, activeforeground=TEXTO, bd=0,
                           highlightthickness=0, relief="flat", cursor="hand2", font=fuente(TAM_S),
                           padx=ESP_S, pady=1)
        self.om_met.pack(side="right", padx=(0, ESP_L))
        Ayuda(self.om_met, "Qué se dibuja: piratas, gemas, ballenas, errores u horas en marcha.")
        self.om_rango = tk.OptionMenu(cab, self.rango, *(f"{d} días" for d in RANGOS))
        self._menu(self.om_rango, {f"{d} días": f"Últimos {d} días" for d in RANGOS})
        self.om_rango.config(bg=PANEL2, fg=TEXTO, activebackground=BORDE, activeforeground=TEXTO, bd=0,
                             highlightthickness=0, relief="flat", cursor="hand2", font=fuente(TAM_S),
                             padx=ESP_S, pady=1)
        self.om_rango.pack(side="right", padx=(0, ESP_L))
        Ayuda(self.om_rango, "Cuántos días se miran hacia atrás.")
        for v in (self.rango, self.metrica):
            v.trace_add("write", lambda *a: self.actualizar(self._nombres, forzar=True))

        self.cv_dia = tk.Canvas(self, height=self.ALTO_DIA, bg=tema["PANEL"], highlightthickness=1,
                                highlightbackground=BORDE, bd=0)
        self.cv_dia.pack(fill="x", pady=ESP_XS)
        self.cv_dia.bind("<Configure>", lambda e: self._pintar_dia())
        self.cv_cuenta = tk.Canvas(self, height=self.ALTO_CUENTA, bg=tema["PANEL"], highlightthickness=1,
                                   highlightbackground=BORDE, bd=0)
        self.cv_cuenta.pack(fill="x", pady=ESP_XS)
        self.cv_cuenta.bind("<Configure>", lambda e: self._pintar_cuenta())
        self.lbl_resumen = tk.Label(self, text="", bg=tema["FONDO"], fg=SUAVE, font=fuente(TAM_XS),
                                    anchor="w", justify="left")
        self.lbl_resumen.pack(fill="x", pady=(ESP_XS, ESP_M))

    def _menu(self, om, nombres):
        om["menu"].config(bg=PANEL2, fg=TEXTO, activebackground=AMBAR, activeforeground=TEXTO,
                          bd=0, font=fuente(TAM_S))
        return nombres

    # ------------------------------------------------------------ datos -----
    def _dias_rango(self) -> int:
        try:
            return int(self.rango.get().split()[0])
        except (ValueError, IndexError):
            return 14

    def actualizar(self, nombres: dict | None = None, archivo=None, forzar: bool = False):
        """Lee las estadisticas y redibuja. No lanza excepciones."""
        nombres = nombres or {}
        self._nombres = nombres
        if not forzar and time.time() - self._ultimo < 5:
            return
        self._ultimo = time.time()
        n = self._dias_rango()
        try:
            res = estadisticas.resumen(n, archivo=archivo)
        except Exception:                                     # noqa: BLE001
            return
        met = self.metrica.get()
        hoy = time.time()
        self._dias = [(time.strftime("%Y-%m-%d", time.localtime(hoy - i * 86400)),
                       valor_metrica(res["por_dia"].get(time.strftime(
                           "%Y-%m-%d", time.localtime(hoy - i * 86400)), {}), met))
                      for i in range(n - 1, -1, -1)]
        self._cuentas = sorted([(nombres.get(c) or nombres.get(c.split(":")[-1]) or c.split(":")[-1],
                                 valor_metrica(v, met))
                                for c, v in (res.get("cuentas") or {}).items()],
                               key=lambda x: -x[1])[:8]
        self._pintar_dia()
        self._pintar_cuenta()
        total = sum(v for _, v in self._dias)
        nombre_met = dict(METRICAS).get(met, met)
        self.lbl_resumen.config(text=f"{nombre_met}: {_texto_valor(total, met)} en los últimos "
                                     f"{n} días · {len(res.get('cuentas') or {})} "
                                     f"{'cuenta' if len(res.get('cuentas') or {}) == 1 else 'cuentas'}")

    # ----------------------------------------------------------- dibujo -----
    def _pintar_dia(self):
        c = self.cv_dia
        c.delete("all")
        w, h = max(120, c.winfo_width()), max(60, c.winfo_height())
        met = self.metrica.get()
        c.create_text(ESP_S, ESP_XS, text=dict(METRICAS).get(met, met) + " por día", anchor="nw",
                      fill=SUAVE, font=fuente(TAM_XS))
        if not self._dias:
            c.create_text(w / 2, h / 2, text="Sin datos todavía", fill=SUAVE, font=fuente(TAM_S))
            return
        top = max(v for _, v in self._dias) or 1
        n = len(self._dias)
        ancho = (w - 2 * ESP_M) / n
        base = h - 16
        for i, (dia, v) in enumerate(self._dias):
            x0 = ESP_M + i * ancho + 2
            x1 = x0 + max(2, ancho - 4)
            alto = int((base - 22) * v / top)
            ultimo = i == n - 1
            c.create_rectangle(x0, base - alto, x1, base, fill=AMBAR if ultimo else VIOLETA, width=0)
            if v:
                c.create_text((x0 + x1) / 2, base - alto - 6, text=_texto_valor(v, met),
                              fill=TEXTO, font=fuente(TAM_XS))
            c.create_text((x0 + x1) / 2, base + 6, text=dia[8:], fill=SUAVE, font=fuente(TAM_XS))

    def _pintar_cuenta(self):
        c = self.cv_cuenta
        c.delete("all")
        w, h = max(160, c.winfo_width()), max(60, c.winfo_height())
        met = self.metrica.get()
        c.create_text(ESP_S, ESP_XS, text=dict(METRICAS).get(met, met) + " por cuenta", anchor="nw",
                      fill=SUAVE, font=fuente(TAM_XS))
        if not self._cuentas:
            c.create_text(w / 2, h / 2, text="Sin datos todavía", fill=SUAVE, font=fuente(TAM_S))
            return
        top = max((v for _, v in self._cuentas), default=0) or 1
        filas = len(self._cuentas)
        alto = max(12, min(20, (h - 24) / filas))
        etiqueta = min(140, int(w * 0.3))
        for i, (nombre, v) in enumerate(self._cuentas):
            y = 18 + i * alto
            c.create_text(ESP_S, y + alto / 2 - 1, text=nombre[:18], anchor="w", fill=TEXTO,
                          font=fuente(TAM_XS))
            x0 = ESP_S + etiqueta
            largo = (w - x0 - 56) * v / top
            c.create_rectangle(x0, y + 2, x0 + max(1, largo), y + alto - 2, fill=TEAL, width=0)
            c.create_text(w - ESP_S, y + alto / 2 - 1, text=_texto_valor(v, met), anchor="e",
                          fill=SUAVE, font=fuente(TAM_XS))
