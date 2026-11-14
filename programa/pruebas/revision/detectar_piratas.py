import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from tareas.piratas import normales

img = cv2.imread(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\captura_5585.png"))
pts = normales.PiratasNormales.simbolos_pirata(img)
print("detectados:", len(pts))
print(pts)
vis = img.copy()
for i, (x, y) in enumerate(pts):
    cv2.circle(vis, (x, y), 24, (0, 255, 0), 2)
    cv2.putText(vis, str(i), (x + 12, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\piratas_detectados.png"), vis)
