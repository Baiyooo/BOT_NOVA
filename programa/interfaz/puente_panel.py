"""Puente con el panel web: estado y ordenes por archivo."""
from __future__ import annotations

import time

from cerebro import config_ballenas
from nucleo import config
from nucleo import estadisticas
from interfaz.catalogo import NOMBRE_TAREA, TAREA_FILA


class _PuentePanel:
    """Puente con el panel web: estado y ordenes por archivo."""

    def _actualizar_panel(self):
        try:
            hoy = estadisticas.resumen(1)["total"]
            self.panel.actualizar({
                "detectadas": len(self.filas),
                "conectadas": sum(1 for f in self.filas if f"127.0.0.1:{f.puerto}" in self.conectadas),
                "activas": sum(1 for f in self.filas if f.en_marcha()),
                "ataques": int(hoy.get("sigilo", 0) + hoy.get("normales", 0)),
                "recompensas": int(hoy.get("recompensas", 0)),
                "segundos": hoy.get("segundos", 0), "errores": int(hoy.get("errores", 0))},
                self._nombres())
            self.panel_est.actualizar(self._nombres())
            filas = estadisticas.resumen(1)["cuentas"]
            for f in self.filas:
                dev = f"127.0.0.1:{f.puerto}"
                d = filas.get(dev, {})
                try:
                    extra = {"ballenas": config_ballenas.hechas_hoy(dev),
                             "senuelos": int(d.get("senuelos", 0) or 0)}
                except Exception:                           # noqa: BLE001
                    extra = {}
                f.pintar_hoy(d, extra)
        except Exception:                               # noqa: BLE001
            pass

    # ------------------------------------------------- panel remoto --
    #  Puente con un panel externo (si el usuario tiene uno): NovaBot solo
    #  escribe su estado en un archivo y lee ordenes de otro. No abre nada a
    #  la red; sin panel, no hace nada.
    def _rutas_panel(self):
        import os
        from nucleo.rutas import carpeta_datos
        base = carpeta_datos()
        return os.path.join(base, "panel_estado.json"), os.path.join(base, "panel_ordenes.json")

    def _puente_panel(self):
        import os
        r_est, r_ord = self._rutas_panel()
        try:
            if os.path.exists(r_ord):
                datos = config.leer(r_ord, defecto={})
                try:
                    os.remove(r_ord)
                except OSError:
                    pass
                for o in (datos.get("ordenes") or [])[:20]:
                    if time.time() - float(o.get("t", 0)) < 120:
                        self._orden_panel(o)
            filas = []
            for f in self.filas:
                st = f.estado or {}
                filas.append({"puerto": f.puerto, "nombre": self._nombres().get(str(f.puerto), f.nombre),
                              "tarea": f.tarea(), "tarea_n": NOMBRE_TAREA.get(f.tarea(), f.tarea()),
                              "en_marcha": bool(f.en_marcha()),
                              "estado": st.get("estado", "en espera"),
                              "ahora": st.get("rutina_texto", ""),
                              "siguiente": f.ahora_siguiente(st)[1],
                              "normales": st.get("normales", 0), "sigilo": st.get("sigilo", 0)})
            est = {"t": time.time(), "version": getattr(__import__("version"), "VERSION", "?"),
                   "estado_general": list(getattr(self, "_estado_general", ("ok", "Todo bien"))),
                   "filas": filas, "log": list(getattr(self, "_log_panel", []))[-80:],
                   "rutina": {k: bool(v.get()) for k, v in self.op_rutina.items()},
                   "ballenas_dia": max([int(c.get("dia", 0)) for c in self._cfg_ballenas().values()
                                        if c.get("rol") in ("invoca", "sola")] or [0]),
                   "ballenas": self._cfg_ballenas(),
                   "tareas": [[k, v] for k, v in NOMBRE_TAREA.items() if k in TAREA_FILA.values()]}
            config.guardar(r_est, est)
        except Exception:                                   # noqa: BLE001
            pass

    def _orden_panel(self, o):
        acc = o.get("accion")
        fila = next((f for f in self.filas if str(f.puerto) == str(o.get("puerto"))), None)
        quien = "Panel remoto"
        if acc == "empezar" and fila and not fila.en_marcha():
            self.escribir("", f"{quien}: empezar {fila.nombre}.")
            self.empezar_fila(fila)
        elif acc in ("pausar", "reanudar") and fila and fila.en_marcha() \
                and getattr(fila, "pausa", None) is not None \
                and fila.pausa.is_set() != (acc == "pausar"):
            self.escribir("", f"{quien}: {acc} {fila.nombre}.")
            self.pulsar_fila(fila)                     # alterna pausa / reanudar
        elif acc == "parar" and fila and fila.en_marcha():
            self.escribir("", f"{quien}: parar {fila.nombre}.")
            self.pulsar_fila(fila)
        elif acc == "empezar_todas":
            self.escribir("", f"{quien}: empezar todas.")
            self.empezar()
        elif acc == "parar_todas":
            self.escribir("", f"{quien}: parar todas.")
            self.parar()
        elif acc == "emergencia":
            self.escribir("", f"{quien}: parada de emergencia.")
            self.emergencia()
        elif acc == "tarea" and fila and not fila.en_marcha() and o.get("tarea") in NOMBRE_TAREA:
            fila.tarea_propia.set(NOMBRE_TAREA[o["tarea"]])
            self.escribir("", f"{quien}: {fila.nombre} → {NOMBRE_TAREA[o['tarea']]}.")
        elif acc == "rutina" and o.get("clave") in self.op_rutina:
            # ahora los ajustes son de cada cuenta: se cambia en todas
            self.op_rutina[o["clave"]].set(bool(o.get("valor")))
            self._guardar_rutina()
            for g in self.filas:
                self._guardar_cuenta(g.puerto, o["clave"], bool(o.get("valor")))
            self.escribir("", f"{quien}: rutina {o['clave']} = {'sí' if o.get('valor') else 'no'}.")
        elif acc == "ballenas_dia":
            try:
                v = max(0, min(40, int(o.get("valor", 0))))
                cfg = self._cfg_ballenas()
                for c in cfg.values():
                    if c.get("rol") in ("invoca", "sola"):
                        c["dia"] = v
                self._guardar_cfg_ballenas(cfg)
                self.escribir("", f"{quien}: ballenas al día = {v} (se aplica al empezar).")
            except (ValueError, TypeError):
                pass
        elif acc == "ballenas_cuenta" and fila:
            cfg = self._cfg_ballenas()
            valor = o.get("valor")
            nuevo = dict(cfg.get(str(fila.puerto)) or {})
            nuevo.update({k: v for k, v in (valor if isinstance(valor, dict) else {}).items()
                          if k in ("rol", "con", "robots", "dia", "grupo", "reparar", "gemas", "escombros",
                                       "min_mineral", "min_cristal", "min_aleacion")})
            _con, avisos = config_ballenas.aplicar(cfg, fila.puerto, nuevo)   # robusto y con parejas
            self._guardar_cfg_ballenas(cfg)
            self.escribir("", f"{quien}: ballenas de {fila.nombre} actualizadas."
                          + (" " + "; ".join(avisos) + "." if avisos else ""))
