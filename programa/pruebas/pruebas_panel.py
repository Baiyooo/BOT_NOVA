import sys
import os
import tempfile
import types
os.environ["LOCALAPPDATA"]=tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
class W:
    def __init__(s,*a,**k): s.cfg=dict(k); s.hijos=[]
    def __getattr__(s,n):
        if n.startswith("__"): raise AttributeError(n)
        return lambda *a,**k: (400 if n=="winfo_width" else (True if n=="winfo_exists" else None))
    def config(s,**k): s.cfg.update(k)
    configure=config
    def cget(s,k): return s.cfg.get(k,"")
    def __setitem__(s,k,v): s.cfg[k]=v
class V:
    def __init__(s,value=None,**k): s.v=value
    def get(s): return s.v
    def set(s,x): s.v=x
    def trace_add(s,*a): pass
tk=types.ModuleType("tkinter")
for n in ("Frame","Label","Button","Canvas","Text","Scrollbar","Toplevel","Tk","Menubutton","Menu","Checkbutton","Spinbox"): setattr(tk,n,type(n,(W,),{}))
tk.BooleanVar=tk.StringVar=tk.IntVar=V; tk.TclError=Exception
sys.modules["tkinter"]=tk
ttk=types.ModuleType("tkinter.ttk")
class _Estilo:
    def __init__(s,*a,**k): pass
    def theme_use(s,*a): pass
    def configure(s,*a,**k): pass
    def map(s,*a,**k): pass
ttk.Style=_Estilo
ttk.Notebook=type("Notebook",(W,),{"add":lambda s,*a,**k: None})
tk.ttk=ttk; sys.modules["tkinter.ttk"]=ttk
from nucleo import estadisticas
from nucleo import diagnostico
from interfaz import panel
estadisticas.sumar("127.0.0.1:5565","sigilo",5); estadisticas.sumar("127.0.0.1:5565","normales",2)
estadisticas.sumar("127.0.0.1:5565","segundos",3700); estadisticas.sumar("127.0.0.1:5565","errores")
diagnostico.registrar("fallo de prueba",cuenta="127.0.0.1:5565",tarea="Simulación")
t={k:"#000000" for k in ("FONDO","PANEL","PANEL2","BORDE","TEXTO","SUAVE","AMBAR","TEAL","ROJO","VERDE")}
p=panel.PanelControl(W(),t)
p.actualizar({"detectadas":4,"conectadas":3,"activas":2,"ataques":7,"recompensas":1,"segundos":3700,"errores":1},{"5565":"Cuenta A"})
print(p.valor["cuentas"].cfg, p.sub["cuentas"].cfg, p.valor["tiempo"].cfg)
print(p.lbl_err.cfg["text"])
e=panel.PanelEstadisticas(W(),t); e.abierto.set(True); e.actualizar({"5565":"Cuenta A"})
print(e.txt.cfg)
w=panel.ventana_registro(W(),t,"x","/nonexistent")
print("FALLOS: 0")
from interfaz import preferencias
from interfaz import tarjeta
from interfaz import ventana
f=tarjeta.FilaInstancia(W(),"Cuenta B",5585,"#fff")
print("fila ok", f.lbl_nombre.cfg["text"])
# App._actualizar_panel y renombrar con una app falsa
class A: pass
a=A(); a.filas=[f]; a.conectadas={"127.0.0.1:5585"}; a.panel=p; a.panel_est=e
a._nombres=lambda: preferencias.leer_prefs().get("nombres",{})
ventana.App._actualizar_panel(a)
print("hoy:", f.lbl_hoy.cfg.get("text"))
estadisticas.sumar("127.0.0.1:5585","sigilo",4)
ventana.App._actualizar_panel(a); print("hoy:", f.lbl_hoy.cfg.get("text"))
import tkinter as tk2
sd=types.ModuleType("tkinter.simpledialog"); sd.askstring=lambda *a,**k:"Mi cuenta"; sys.modules["tkinter.simpledialog"]=sd; tk2.simpledialog=sd
a._nombres=lambda: preferencias.leer_prefs().get("nombres",{}); a.title=None
ventana.App._renombrar(a,f); print("nombre:", f.lbl_nombre.cfg["text"], preferencias.leer_prefs().get("nombres"))
# ---- ajustes por cuenta
guardado={}
w=panel.ventana_ajustes_cuenta(W(),t,"X",{"opciones":{"salto":True},"rutina":{"sigilo":True},"tickets":0}, lambda d: guardado.update(d), cuentas=[("5555","Otra")], ballenas={"rol":"invoca","con":"5555"})
print("dialogo ok")
# empezar_fila con los ajustes de la cuenta
p_=preferencias.leer_prefs(); p_.setdefault("cuentas",{})["5585"]={"opciones":{"salto":False,"dados":False},"rutina":{"normales":True,"sigilo":False},"tickets":5}
preferencias.guardar_prefs(p_)
class Proc:
    def __init__(s,target=None,daemon=None,args=()): Proc.args=args
    def start(s): pass
class MP:
    Process=Proc
    def Event(s): return object()
b=A(); b.mp=MP(); b.adb="adb"; b.cola_mp=None
for n,vv in (("op_atacar",True),("op_salto",True),("op_dados",True),("op_defensa",True),("op_mision",True),("op_mult",True),("op_ascender",True)): setattr(b,n,V(vv))
b.op_rutina={"normales":V(False),"sigilo":V(True),"gratis":V(True)}
b._tickets=lambda: 0; b.escribir=lambda *a,**k: None
b._ballenas_dia=lambda: 2; b._cfg_ballenas=lambda: {}
b._generales=lambda: ventana.App._generales(b); b.ajustes_de=lambda p: ventana.App.ajustes_de(b,p)
b._opciones_de=lambda f: ventana.App._opciones_de(b,f); b._firma_ajustes=lambda f: ventana.App._firma_ajustes(b,f)
f.reset=lambda: None; f.n_veces=lambda: 0; f.tarea=lambda: "rutina"; f.marcha=lambda v: None
ventana.App.empezar_fila(b,f)
opc=Proc.args[4]
print({k:opc[k] for k in ("salto","dados","normales","roaming_tickets")}, opc["que"])
# ---- «Solo ballenas»: en el desplegable y con los ajustes compartidos con la Rutina
from interfaz import catalogo
from cerebro import rutina as _rut
assert "Solo ballenas" in [n for _g, ns in catalogo.TAREA_GRUPOS for n in ns]
assert catalogo.TAREA_FILA["Solo ballenas"] == "ballenas" and catalogo.NOMBRE_TAREA["ballenas"] == "Solo ballenas"
_cfgb = {"rol": "apoya", "con": "5555", "robots": 3, "dia": 4}
class _C: name = "127.0.0.1:5999"
_r = _rut.Rutina(_C(), ballenas=_cfgb); _s = _rut.SoloBallenas(_C(), ballenas=_cfgb)
assert (_s.b_rol, _s.b_con, _s.b_robots, _s.ballenas_dia, _s.ruta) == (_r.b_rol, _r.b_con, _r.b_robots, _r.ballenas_dia, _r.ruta)
assert sorted(k for k, v in _s.que.items() if v) == ["ballenas", "escombros", "gemas"]   # casillas por defecto
assert [k for k, v in _rut.SoloBallenas(_C(), ballenas={**_cfgb, "escombros": False, "gemas": False}).que.items() if v] == ["ballenas"]
print("solo ballenas ok")

# ---- ajustes de ballenas unificados: migracion y resumen de la tarjeta
from cerebro import config_ballenas as _cb
_v = _cb.normalizar({"rol": "invoca", "con": "5555", "robots": 3, "dia": 4})
assert (_v["rol"], _v["con"], _v["robots"], _v["dia"]) == ("invoca", "5555", 3, 4)      # lo de antes sigue igual
assert (_v["grupo"], _v["reparar"], _v["gemas"]) == (True, True, True)                  # lo nuevo, por defecto
assert _cb.normalizar({"rol": "apoya", "con": ""})["rol"] == "no"                       # sin pareja no hay ballenas
assert _cb.normalizar({"rol": "sola", "con": "5555"})["con"] == ""                      # sola no tiene pareja
assert _cb.NOMBRE_MODO["sola"].startswith("Sola") and _cb.NOMBRE_MODO["invoca"] == "Invoca con ayuda de otra cuenta"
assert _cb.resumen({"rol": "sola", "dia": 2, "robots": 6}, hechas=0) == "Sola \u00b7 2 al d\u00eda (llevo 0) \u00b7 6 drones \u00b7 gemas: s\u00ed \u00b7 escombros: s\u00ed (>18/2/1 M)"
assert _cb.resumen({"rol": "invoca", "con": "5555", "dia": 4, "robots": 3, "gemas": False}, {"5555": "Otra"}, 1) == "Con Otra (invoca) \u00b7 4 al d\u00eda (llevo 1) \u00b7 3 drones \u00b7 gemas: no \u00b7 escombros: s\u00ed (>18/2/1 M)"
assert _cb.resumen({}) == "Sin configurar: pulsa Ajustes"
# guardar desde Ajustes: sola no deja pareja y la antigua queda libre
_guard = {}
_A = types.SimpleNamespace(_cfg_ballenas=lambda: {"5585": {"rol": "invoca", "con": "5555"}, "5555": {"rol": "apoya", "con": "5585"}},
                           _guardar_cfg_ballenas=lambda c: _guard.update(c), escribir=lambda *a, **k: None)
from interfaz import ajustes as _aj
_aj._Ajustes._guardar_pareja(_A, "5585", {"rol": "sola", "dia": 2, "robots": 6}, False)
assert _guard["5585"]["rol"] == "sola" and _guard["5585"]["con"] == "" and _guard["5555"]["rol"] == "no"
# valores raros no revientan; emparejar con una cuenta ocupada libera a su pareja antigua
assert _cb.normalizar({"rol": "sola", "robots": "", "dia": "abc"})["robots"] == 6
assert _cb.normalizar({"rol": "sola", "dia": "x"})["dia"] == 2 and _cb.normalizar({"rol": "sola", "dia": 0})["dia"] == 0
_cfg = {"5001": {"rol": "invoca", "con": "5002"}, "5002": {"rol": "apoya", "con": "5001"}, "5003": {"rol": "sola"}}
_con, _av = _cb.aplicar(_cfg, "5003", {"rol": "invoca", "con": "5002", "dia": "", "robots": "x"})
assert _con == "5002" and _cfg["5002"]["con"] == "5003" and _cfg["5002"]["rol"] == "apoya"
assert _cfg["5001"]["rol"] == "no" and _cfg["5001"]["con"] == "" and _av, _av
_con, _av = _cb.aplicar(_cfg, "5003", {"rol": "sola"})                   # pasar a sola libera a la pareja
assert _con == "" and _cfg["5002"]["rol"] == "no" and _cfg["5003"]["con"] == ""
# la tarjeta de "Solo ballenas": sin Limite, con el resumen del ajuste
p_ = preferencias.leer_prefs(); p_["ballenas"] = {"5585": {"rol": "sola", "dia": 2, "robots": 6}}; preferencias.guardar_prefs(p_)
f = tarjeta.FilaInstancia(W(), "Cuenta B", 5585, "#fff")      # la de arriba tiene tarea() falseada
f.tarea_propia.set("Solo ballenas"); f._cambio(guardar=False)
assert f.lbl_unidad.cfg["text"].startswith("Sola \u00b7 2 al d\u00eda (llevo 0)"), f.lbl_unidad.cfg["text"]
assert f.spin.cfg.get("state") == "disabled"
p_["ballenas"] = {}; preferencias.guardar_prefs(p_); f.pintar_ballenas()
assert f.lbl_unidad.cfg["text"] == "Sin configurar: pulsa Ajustes"
f.tarea_propia.set("Rutina autom\u00e1tica"); f._cambio(guardar=False)
assert "l\u00edmite" in f.lbl_unidad.cfg["text"] or f.lbl_unidad.cfg["text"] == "hasta que la pares"
assert _cb.normalizar({"rol": "sola"})["escombros"] is True and _cb.normalizar({"rol": "sola", "escombros": False})["escombros"] is False   # migracion: por defecto si
assert _cb.resumen({"rol": "sola", "dia": 2, "escombros": False}, hechas=0).endswith("gemas: s\u00ed \u00b7 escombros: no")
# minimos de escombros de ballena: defectos 18/2/1 (migracion), lectura segura y unidades
_m = _cb.normalizar({"rol": "sola"})
assert (_m["min_mineral"], _m["min_cristal"], _m["min_aleacion"]) == (18.0, 2.0, 1.0)
_m = _cb.normalizar({"rol": "sola", "min_mineral": "", "min_cristal": "2,5", "min_aleacion": "abc"})
assert (_m["min_mineral"], _m["min_cristal"], _m["min_aleacion"]) == (18.0, 2.5, 1.0)
assert _cb.normalizar({"rol": "sola", "min_mineral": -4})["min_mineral"] == 0.0
assert _cb.minimos_unidades({"min_mineral": 20, "min_cristal": 3, "min_aleacion": 0.5}) == {
    "mineral": 20_000_000, "cristal": 3_000_000, "aleacion": 500_000}
assert "(>18/2/1 M)" in _cb.resumen({"rol": "sola", "dia": 2}, hechas=0)
assert _rut.Rutina(_C(), ballenas={"rol": "sola", "min_cristal": 5}).b_minimos["cristal"] == 5_000_000      # la Rutina, los mismos ajustes
assert _rut.SoloBallenas.ESCOMBROS_DE_BALLENAS is True and _rut.Rutina.ESCOMBROS_DE_BALLENAS is False
print("ajustes ballenas ok")
