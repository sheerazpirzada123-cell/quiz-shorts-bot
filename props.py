# Prop Library for Kurzgesagt style flat vector objects
import cv2
import numpy as np

class PropLibrary:
    @staticmethod
    def draw_chicken(canvas, pos, scale=1.0, action="idle", frame_idx=0):
        x, y = int(pos[0]), int(pos[1])
        # Body
        cv2.ellipse(canvas, (x, y), (int(30*scale), int(22*scale)), 0, 0, 360, (245, 245, 245), -1)
        cv2.ellipse(canvas, (x, y), (int(30*scale), int(22*scale)), 0, 0, 360, (40, 40, 40), 2)
        # Head & Peck Motion
        head_offset = int(np.sin(frame_idx * 0.3) * 5) if action == "peck" else 0
        hx, hy = x + int(20*scale), y - int(25*scale) + head_offset
        cv2.circle(canvas, (hx, hy), int(14*scale), (245, 245, 245), -1)
        cv2.circle(canvas, (hx, hy), int(14*scale), (40, 40, 40), 2)
        # Beak & Comb
        cv2.drawContours(canvas, [np.array([[hx+8, hy-2], [hx+22, hy+3], [hx+8, hy+8]])], 0, (0, 165, 255), -1)
        cv2.circle(canvas, (hx, hy-14), int(5*scale), (0, 0, 230), -1)
        # Eye
        cv2.circle(canvas, (hx+4, hy-3), int(2.5*scale), (20, 20, 20), -1)

    @staticmethod
    def draw_chalkboard(canvas, pos, text="y = f(x)", scale=1.0):
        x, y = int(pos[0]), int(pos[1])
        w, h = int(220*scale), int(140*scale)
        cv2.rectangle(canvas, (x - w//2, y - h//2), (x + w//2, y + h//2), (40, 65, 45), -1)
        cv2.rectangle(canvas, (x - w//2, y - h//2), (x + w//2, y + h//2), (30, 100, 180), 4)
        cv2.putText(canvas, text, (x - w//2 + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7*scale, (240, 240, 240), 2)
        cv2.polylines(canvas, [np.array([[x-80, y+40], [x-30, y+10], [x+20, y+35], [x+70, y-20]])], False, (50, 220, 255), 3)

    @staticmethod
    def draw_coin_bag(canvas, pos, scale=1.0):
        x, y = int(pos[0]), int(pos[1])
        cv2.circle(canvas, (x, y+10), int(35*scale), (30, 160, 230), -1)
        cv2.circle(canvas, (x, y+10), int(35*scale), (20, 100, 160), 2)
        cv2.putText(canvas, "$", (x-12, y+22), cv2.FONT_HERSHEY_DUPLEX, 1.2*scale, (10, 80, 120), 3)

    @staticmethod
    def draw_signboard(canvas, pos, text="UNFAIR!", scale=1.0):
        x, y = int(pos[0]), int(pos[1])
        cv2.rectangle(canvas, (x-6, y), (x+6, y+80), (30, 60, 90), -1)
        cv2.rectangle(canvas, (x-90, y-50), (x+90, y), (40, 90, 140), -1)
        cv2.rectangle(canvas, (x-90, y-50), (x+90, y), (20, 40, 70), 3)
        cv2.putText(canvas, text, (x-75, y-15), cv2.FONT_HERSHEY_SIMPLEX, 0.8*scale, (240, 240, 240), 2)
