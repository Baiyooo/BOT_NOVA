from rapidocr_onnxruntime import RapidOCR
import cv2

engine = RapidOCR()
img = cv2.imread(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\eventos_lista.png"))
res, elapse = engine(img)
print("n:", len(res) if res else 0, "elapse:", elapse)
for box, txt, score in (res or []):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    print(f"{min(xs):4.0f},{min(ys):4.0f}  {score:.2f}  {txt}")
