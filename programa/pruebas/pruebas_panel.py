import sys, os, tempfile, types
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
w=panel.ventana_ajustes_cuenta(W(),t,"X",{}, {"opciones":{"salto":True},"rutina":{"sigilo":True},"tickets":0}, lambda d: guardado.update(d))
print("dialogo ok")
# empezar_fila con ajustes propios
p_=preferencias.leer_prefs(); p_.setdefault("cuentas",{})["5585"]={"propios":True,"opciones":{"salto":False,"dados":False},"rutina":{"normales":True,"sigilo":False},"tickets":5}
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
f.reset=lambda: None; f.n_veces=lambda: 0; f.tarea=lambda: "rutina"; f.marcha=lambda v: None
ventana.App.empezar_fila(b,f)
opc=Proc.args[4]
print({k:opc[k] for k in ("salto","dados","normales","roaming_tickets")}, opc["que"])
