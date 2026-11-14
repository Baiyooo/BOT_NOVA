"""Agente de percepcion: mira la pantalla y dice QUE hay y DONDE.

Junta dos «sentidos» (multimodal):
  - vista: un detector tipo YOLO (ONNX, pequeño: corre en CPU en ~30-80 ms;
    si hay una NVIDIA o DirectML disponible, la usa sola) que encuentra
    objetos del juego: ballena, gema, flota, pirata...
  - lectura: el OCR (RapidOCR) para los textos de la pantalla.
El resultado es una Escena que consultan los agentes de tarea (ballenas,
gemas, flotas, piratas) y el verificador antes de pulsar nada.

Si no hay modelo (o falla), cae a los detectores clasicos (plantillas y
colores), asi el bot sigue funcionando igual que antes.
"""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from vision import gpu_compartida

CLASES = ["ballena", "gema", "flota", "pirata"]
NOMBRE_MODELO = "novabot_det.onnx"
TAM = 640


class Detector:
    """Detector ONNX (salida estilo YOLOv8: 1 x (4+nc) x N)."""

    _uno = None
    _cerrojo = threading.Lock()

    #  la grafica solo se usa si va al menos asi de mas rapida que el procesador
    GANANCIA_GPU = 1.25

    def __init__(self, ruta):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2            # no comerse el PC (hay varias instancias)
        opts.inter_op_num_threads = 1
        self.sesion = ort.InferenceSession(ruta, sess_options=opts,
                                           providers=["CPUExecutionProvider"])
        self.entrada = self.sesion.get_inputs()[0].name
        self.proveedor = "CPU"
        self._gpu = None                  # (nombre, funcion) si la grafica compensa
        self.ms = self.ms_cpu = self.ms_gpu = None
        self._args_motor = (ruta, ort, opts)
        self._gpu_probada = False
        self.dispositivo = "CPU"          # con que se hizo la ultima inferencia
        self._probar_motor()
        meta = self.sesion.get_modelmeta().custom_metadata_map or {}
        nombres = meta.get("names")
        self.clases = CLASES
        if nombres:
            try:
                import ast
                d = ast.literal_eval(nombres)
                self.clases = [d[i] for i in sorted(d)]
            except Exception:                                 # noqa: BLE001
                pass

    # ---- motor: procesador o grafica (la que haya), lo que vaya mejor
    def _correr_cpu(self, x):
        return self.sesion.run(None, {self.entrada: x})[0]

    def _probar_motor(self):
        """Mide (una vez con la grafica permitida; si el usuario la tiene
        desactivada solo se mide el procesador y se mira otra vez al activarla)."""
        con_gpu = gpu_compartida.usar_gpu()
        try:
            self._elegir_motor(*self._args_motor, con_gpu=con_gpu)
            self._gpu_probada = con_gpu
        except Exception:                                     # noqa: BLE001
            self._gpu, self.proveedor = None, "CPU"
            self._gpu_probada = True

    def _correr(self, x):
        """Una inferencia: grafica si compensa, el usuario la permite y hay turno
        (compartido, con limite de imagenes por segundo); si no, procesador."""
        usar = gpu_compartida.usar_gpu()
        if usar and not self._gpu_probada:
            self._probar_motor()
        self.dispositivo = "CPU"
        if usar and self._gpu is not None:
            lim = max(0.5, 8 * (self.ms_cpu or 100) / 1000)    # mas lento que el procesador: ocupada
            y = gpu_compartida.compartida().ejecutar(self._gpu[1], x, lim)
            if y is not None:
                self.dispositivo = "GPU"
                return y
        return self._correr_cpu(x)

    def _elegir_motor(self, ruta, ort, opts, con_gpu=True):
        """Si el PC tiene grafica, la prueba una vez: solo se queda con ella si
        da lo mismo que el procesador y va claramente mas rapida. Sin grafica
        (o si no compensa) se usa el procesador, con 2 hilos."""
        x = np.random.default_rng(0).random((1, 3, TAM, TAM), dtype=np.float32)
        ref = self._correr_cpu(x)

        def medir(f):
            f(x)                                         # calentar
            t = time.perf_counter()
            for _ in range(3):
                y = f(x)
            return (time.perf_counter() - t) / 3, y

        t_cpu, _ = medir(self._correr_cpu)
        candidatos = []
        # 1) onnxruntime con CUDA o DirectML, si esta instalado ese paquete
        for prov in ("CUDAExecutionProvider", "DmlExecutionProvider"):
            if con_gpu and prov in ort.get_available_providers():
                try:
                    ses = ort.InferenceSession(ruta, sess_options=opts,
                                               providers=[prov, "CPUExecutionProvider"])
                    nombre = ses.get_inputs()[0].name
                    candidatos.append((prov.replace("ExecutionProvider", ""),
                                       lambda x, ses=ses, nombre=nombre: ses.run(None, {nombre: x})[0]))
                except Exception:                             # noqa: BLE001
                    pass
        # 2) OpenCV por OpenCL: vale para graficas NVIDIA, AMD e Intel sin instalar nada
        try:
            if con_gpu and cv2.ocl.haveOpenCL():
                cv2.ocl.setUseOpenCL(True)
                if cv2.ocl.useOpenCL():
                    red = cv2.dnn.readNetFromONNX(ruta)
                    red.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    red.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL_FP16)

                    def por_opencl(x, red=red):
                        red.setInput(x)
                        return red.forward()
                    candidatos.append(("GPU (OpenCL)", por_opencl))
        except Exception:                                     # noqa: BLE001
            pass
        mejor = None
        for nombre, f in candidatos:
            try:
                t, y = medir(f)
            except Exception:                                 # noqa: BLE001
                continue
            if y.shape != ref.shape or float(np.abs(y[:, 4:] - ref[:, 4:]).max()) > 0.05:
                continue                                 # no da lo mismo: no se usa
            if t * self.GANANCIA_GPU < t_cpu and (mejor is None or t < mejor[0]):
                mejor = (t, nombre, f)
        self.ms_cpu = round(1000 * t_cpu)
        self.ms_gpu = round(1000 * mejor[0]) if mejor else None
        if mejor is not None:
            self.proveedor, self._gpu = mejor[1], (mejor[1], mejor[2])
        else:
            self.proveedor, self._gpu = "CPU", None
        if mejor is None or "OpenCL" not in mejor[1]:
            try:
                cv2.ocl.setUseOpenCL(False)              # dejar OpenCV como estaba
            except Exception:                                 # noqa: BLE001
                pass
        self.ms = round(1000 * (mejor[0] if mejor else t_cpu))

    @classmethod
    def cargar(cls):
        """El detector compartido (uno por proceso), o None si no hay modelo."""
        with cls._cerrojo:
            if cls._uno is None:
                cls._uno = False
                from nucleo import conocimiento
                for r in conocimiento.rutas_modelo():         # el mas reciente primero
                    try:
                        cls._uno = cls(r)
                        break
                    except Exception:                         # noqa: BLE001
                        cls._uno = False
            return cls._uno or None

    def detectar(self, img, umbral=0.35, iou=0.5):
        h, w = img.shape[:2]
        s = TAM / max(h, w)
        nw, nh = int(round(w * s)), int(round(h * s))
        lienzo = np.full((TAM, TAM, 3), 114, np.uint8)
        dx, dy = (TAM - nw) // 2, (TAM - nh) // 2
        lienzo[dy:dy + nh, dx:dx + nw] = cv2.resize(img, (nw, nh))
        x = cv2.cvtColor(lienzo, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self._correr(x)[0]                                  # (4+nc, N)
        if out.shape[0] > out.shape[1]:
            out = out.T
        cajas, puntos, clases = out[:4].T, out[4:].T, None
        clases = puntos.argmax(1)
        conf = puntos.max(1)
        sel = conf >= umbral
        cajas, conf, clases = cajas[sel], conf[sel], clases[sel]
        res = []
        if len(cajas):
            xywh = []
            for cx, cy, bw, bh in cajas:
                x0 = (cx - bw / 2 - dx) / s
                y0 = (cy - bh / 2 - dy) / s
                xywh.append([float(x0), float(y0), float(bw / s), float(bh / s)])
            idx = cv2.dnn.NMSBoxes(xywh, conf.astype(float).tolist(), umbral, iou)
            for i in np.array(idx).flatten():
                x0, y0, bw, bh = xywh[i]
                c = int(clases[i])
                res.append({"clase": self.clases[c] if c < len(self.clases) else str(c),
                            "caja": (int(x0), int(y0), int(bw), int(bh)),
                            "centro": (int(x0 + bw / 2), int(y0 + bh / 2)),
                            "conf": float(conf[i])})
        return res


class Escena:
    """Lo que hay en una captura: objetos (detector) y textos (OCR, bajo demanda)."""

    def __init__(self, img, objetos, fuente):
        self.img = img
        self.objetos = objetos
        self.fuente = fuente            # "modelo" o "clasico"
        self._textos = {}
        self.t = time.time()

    def de(self, clase, conf=0.0):
        return [o for o in self.objetos if o["clase"] == clase and o.get("conf", 1) >= conf]

    def cerca(self, punto, clase=None, radio=80):
        return [o for o in self.objetos if (clase is None or o["clase"] == clase)
                and (o["centro"][0] - punto[0]) ** 2 + (o["centro"][1] - punto[1]) ** 2 < radio ** 2]

    def textos(self, zona=None):
        from vision import ocr
        if zona not in self._textos:
            self._textos[zona] = ocr.leer(self.img, zona)
        return self._textos[zona]

    def busca(self, *frases, zona=None):
        from vision import ocr
        h, w = self.img.shape[:2]
        return ocr.buscar(self.textos(zona), *frases, zona=zona, w=w, h=h)


def _clasico(img):
    """Sin modelo: los detectores de siempre (plantillas y colores)."""
    objs = []
    try:
        from tareas.ballenas import deteccion
        for c in deteccion.ballenas_por_forma([img]):
            objs.append({"clase": "ballena", "centro": c, "caja": (c[0] - 26, c[1] - 16, 52, 32), "conf": 0.7})
        for c in deteccion.gemas_2d(img):
            objs.append({"clase": "gema", "centro": c, "caja": (c[0] - 24, c[1] - 22, 48, 54), "conf": 0.8})
    except Exception:                                         # noqa: BLE001
        pass
    try:
        from tareas.piratas.sigilo import PiratasSigilo
        for x, y, r in PiratasSigilo._estorbos(img):
            objs.append({"clase": "flota", "centro": (int(x), int(y)),
                         "caja": (int(x - 45), int(y - 70), 90, 90), "conf": 0.6})
    except Exception:                                         # noqa: BLE001
        pass
    return objs


def ver(img, umbral=0.35) -> Escena:
    """Agente de percepcion: Escena de la captura."""
    det = Detector.cargar()
    if det is not None:
        try:
            return Escena(img, det.detectar(img, umbral), "modelo")
        except Exception:                                     # noqa: BLE001
            pass
    return Escena(img, _clasico(img), "clasico")


def estado_detector() -> dict:
    """Estado para la interfaz: {dispositivo "GPU"|"CPU", ms_por_imagen,
    gpu_disponible (hay grafica utilizable que compensa), usar_gpu (interruptor
    del usuario), motivo, lector_texto_listo}. No carga el modelo si no hace falta."""
    import importlib.util
    usar = gpu_compartida.usar_gpu()
    est = {"dispositivo": "CPU", "ms_por_imagen": None, "gpu_disponible": False,
           "usar_gpu": usar, "motivo": "", "lector_texto_listo": False}
    try:
        est["lector_texto_listo"] = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except Exception:                                         # noqa: BLE001
        pass
    det = Detector.cargar()
    if det is None:
        est["motivo"] = "sin modelo (detectores clasicos)"
        return est
    est["gpu_disponible"] = det._gpu is not None
    if det._gpu is not None and usar and det.dispositivo == "GPU":
        est["dispositivo"] = "GPU"
        est["ms_por_imagen"] = det.ms_gpu
        est["motivo"] = f"{det._gpu[0]}: {det.ms_gpu} ms frente a {det.ms_cpu} ms en procesador"
        return est
    est["ms_por_imagen"] = det.ms_cpu
    if not usar:
        est["motivo"] = "grafica desactivada por el usuario"
    elif det._gpu is None:
        est["motivo"] = ("la grafica no esta disponible o no compensa"
                         if det._gpu_probada else "procesador")
    else:
        est["motivo"] = (gpu_compartida.compartida().motivo or "procesador hasta que haya turno de grafica")
    return est


def poner_usar_gpu(valor: bool) -> bool:
    """Interruptor «usar_gpu» (persistente, en caliente). Solo es efectivo si la
    grafica compensa al medir."""
    return gpu_compartida.poner_usar_gpu(valor)


def info() -> str:
    det = Detector.cargar()
    if det is None:
        return "sin modelo (detectores clásicos)"
    ms = getattr(det, "ms", None)
    return f"modelo {NOMBRE_MODELO} en {det.proveedor}" + (f" (~{ms} ms por imagen)" if ms else "")
