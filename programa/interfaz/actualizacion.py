"""Versiones nuevas: preparar el equipo, vigilar cambios y relanzar la ventana."""
from __future__ import annotations

import threading
import time

from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import AMBAR


class _Actualizacion:
    """Versiones nuevas: preparar el equipo, vigilar cambios y relanzar la ventana."""

    def _preparar_equipo(self):
        """Al arrancar, en segundo plano y sin ventanas: todo lo que antes
        eran .bat aparte.
          1. si hay un paquete NovaBot*.zip mas nuevo (Descargas o junto a
             BOT.bat), lo instala (y la ventana se relanza sola);
          2. si falta, instala el lector de texto (RapidOCR);
          3. hace el diagnostico del equipo y avisa solo si algo falla
             (el informe queda en %LOCALAPPDATA%\\NovaBot\\diagnostico.txt)."""
        def trabajo():
            import importlib.util
            import os
            import subprocess
            import sys
            avisa = lambda m: self.cola.put(("", m))      # noqa: E731
            # 1) la ultima actualizacion
            try:
                from nucleo import actualizar
                r = actualizar.automatica(self._carpeta(), log=lambda m: None)
                if r == "codigo":
                    avisa("He instalado la versión nueva que había en Descargas; "
                          "la ventana se reinicia sola.")
                    self.cola.put(("__aviso__", "ok|Versión nueva instalada: la ventana se reinicia sola."))
                elif r == "conocimiento":
                    avisa("He añadido lo aprendido que traía el paquete (no empieza de cero).")
            except Exception as e:                       # noqa: BLE001
                avisa(f"No he podido instalar la versión nueva: {e}")
            # 2) el lector de texto
            if not any(importlib.util.find_spec(m) for m in ("rapidocr", "rapidocr_onnxruntime")):
                py = sys.executable
                consola = os.path.join(os.path.dirname(py), "python.exe")
                if os.path.exists(consola):
                    py = consola
                avisa("Instalando el lector de texto (RapidOCR) para leer los eventos. "
                      "Tarda unos minutos y solo pasa una vez...")
                try:
                    req = os.path.join(self._carpeta(), "requirements.txt")   # version probada
                    r = subprocess.run([py, "-m", "pip", "install", "rapidocr_onnxruntime"]
                                       + (["-c", req] if os.path.exists(req) else []),
                                       capture_output=True, text=True, timeout=1500,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    avisa("Lector de texto instalado." if r.returncode == 0 else
                          "No se pudo instalar el lector de texto: "
                          + (r.stderr or r.stdout or "")[-300:])
                except Exception as e:                   # noqa: BLE001
                    avisa(f"No se pudo instalar el lector de texto: {e}")
            # 3) diagnostico (antes era DIAGNOSTICO.bat)
            try:
                from nucleo import diagnostico_sistema
                texto, fallos, base = diagnostico_sistema.revisar()
                with open(os.path.join(base, "diagnostico.txt"), "w", encoding="utf-8") as fh:
                    fh.write(texto + "\n")
                if fallos:
                    malos = [x.replace("[FALLO] ", "") for x in texto.splitlines()
                             if x.startswith("[FALLO]")]
                    avisa(f"Diagnóstico: {fallos} problema(s): " + "; ".join(malos[:3])
                          + ". Informe completo en " + os.path.join(base, "diagnostico.txt"))
            except Exception:                            # noqa: BLE001
                pass
        def seguro():
            import os
            import traceback
            from nucleo.rutas import carpeta_datos
            ruta = os.path.join(carpeta_datos(), "preparar.log")
            try:
                with open(ruta, "a", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " empiezo\n")
                trabajo()
                with open(ruta, "a", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " hecho\n")
            except Exception:                            # noqa: BLE001
                try:
                    with open(ruta, "a", encoding="utf-8") as fh:
                        fh.write(traceback.format_exc() + "\n")
                except OSError:
                    pass
        threading.Thread(target=seguro, daemon=True).start()

    def _actualizar_archivo(self):
        from tkinter import filedialog
        from nucleo import actualizar
        ruta = filedialog.askopenfilename(parent=self, title="Paquete NovaBot.zip",
                                          filetypes=[("Paquete NovaBot", "*.zip")])
        if not ruta:
            return

        def trabajo():
            try:
                v1, v2 = actualizar.aplicar(ruta, self._carpeta(),
                                            log=lambda m: self.cola.put(("", m)))
                self.cola.put(("", f"Actualizada la versión {v1} → {v2}. La ventana se reinicia sola."))
                self.cola.put(("__aviso__", f"ok|Versión nueva instalada: {v1} → {v2}."))
            except actualizar.ErrorActualizar as e:
                self.cola.put(("", f"NO se ha actualizado: {e}"))
            except Exception as e:                      # noqa: BLE001
                self.cola.put(("", f"Error al actualizar: {e}"))
        threading.Thread(target=trabajo, daemon=True).start()

    # --------------------------------------------------- actualizar en marcha --
    #  Al cambiar los archivos del programa (una version nueva copiada en la
    #  carpeta) no hace falta cerrar nada:
    #  - si cambian las tareas, cada instancia en marcha termina el paso en
    #    curso y sigue con la misma tarea ya con el codigo nuevo;
    #  - si cambia la ventana, se apunta que instancias iban, se abre la
    #    ventana nueva y esta las vuelve a poner en marcha.
    def _carpeta(self):
        """La carpeta programa."""
        import os
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _huella(self) -> dict:
        import glob
        import os
        h = {}
        base = self._carpeta()
        for ruta in glob.glob(os.path.join(base, "**", "*.py"), recursive=True):
            rel = os.path.relpath(ruta, base).replace("\\", "/")
            if rel.startswith("pruebas/"):
                continue
            try:
                st = os.stat(ruta)
                h[rel] = (st.st_mtime, st.st_size)
            except OSError:
                pass
        return h

    def _vigilar_version(self):
        try:
            ahora = self._huella()
            if ahora != self._version and not self._relanzando:
                # esperar a que la copia termine: dos vistazos seguidos iguales
                if self._cambio_visto == ahora:
                    cambiados = sorted(k for k in set(ahora) | set(self._version)
                                       if ahora.get(k) != self._version.get(k))
                    self._version = ahora
                    self._cambio_visto = None
                    self._aplicar_version(cambiados)
                else:
                    self._cambio_visto = ahora
        finally:
            self.after(3000, self._vigilar_version)

    def _aplicar_version(self, cambiados):
        self.escribir("", "Versión nueva del programa (" + ", ".join(cambiados) + ").")
        if any(k == "main.py" or k.startswith("interfaz/") for k in cambiados):
            self._relanzar()
            return
        vivas = [f for f in self.filas if f.en_marcha()]
        if not vivas:
            self.escribir("", "Se usará al empezar la próxima tarea.")
            return
        for f in vivas:
            f.actualizar = True
            # una cuenta en pausa vuelve a arrancar en pausa (solo el boton la reanuda)
            f._pausa_antes = bool(getattr(f, "pausa", None) is not None and f.pausa.is_set())
            f.parada.set()
            f.lbl_estado.config(text="Actualizando…", fg=AMBAR)
        self.escribir("", "Cada instancia termina lo que está haciendo y sigue "
                          "con la versión nueva.")

    def _relanzar(self):
        """Abre la ventana nueva y cierra esta; la nueva reanuda las tareas."""
        import os
        import subprocess
        import sys
        self._relanzando = True
        vivas = [f.puerto for f in self.filas if f.en_marcha()]
        d = leer_prefs()
        d["reanudar"] = vivas
        d["reanudar_en_pausa"] = [f.puerto for f in self.filas if f.en_marcha()
                                  and getattr(f, "pausa", None) is not None and f.pausa.is_set()]
        guardar_prefs(d)
        for f in self.filas:
            if f.en_marcha():
                f.parada.set()
                f.lbl_estado.config(text="Actualizando…", fg=AMBAR)
        self.escribir("", "La ventana también ha cambiado: la abro de nuevo y "
                          "sigo con las mismas tareas.")
        fin = time.time() + 40

        def esperar():
            if any(f.en_marcha() for f in self.filas) and time.time() < fin:
                self.after(500, esperar)
                return
            for f in self.filas:
                if f.hilo is not None and f.hilo.is_alive():
                    f.hilo.terminate()
            exe = sys.executable
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) if sys.platform == "win32" else 0
            subprocess.Popen([exe, os.path.join(self._carpeta(), "main.py")], cwd=self._carpeta(),
                             creationflags=flags)
            self.parada.set()
            self.after(300, self.destroy)
        self.after(500, esperar)

    def _reanudar(self, puertos):
        filas = [f for f in self.filas if f.puerto in puertos and not f.en_marcha()]
        if filas:
            self.escribir("", "Ventana actualizada: sigo con las tareas que iban.")
        en_pausa = set(leer_prefs().get("reanudar_en_pausa", []))
        for f in filas:
            self.empezar_fila(f, en_pausa=f.puerto in en_pausa)
