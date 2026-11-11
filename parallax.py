# Parallax Diorama Engine
import os
import cv2
import numpy as np

class ParallaxEngine:
    def __init__(self):
        self.depth_model = None

    def generate_depth_map(self, img):
        if os.environ.get("DEPTH_OFFLINE") == "1":
            return self._synthetic_depth(img)
        try:
            import torch
            if self.depth_model is None:
                self.depth_model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small").eval()
            h, w = img.shape[:2]
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            input_tensor = torch.from_numpy(img_rgb).permute(2,0,1).unsqueeze(0).float() / 255.0
            with torch.no_grad():
                prediction = self.depth_model(input_tensor)
                depth = torch.nn.functional.interpolate(
                    prediction.unsqueeze(1), size=(h, w), mode="bicubic", align_corners=False
                ).squeeze().cpu().numpy()
            depth_norm = cv2.normalize(depth, None, 0, 1, cv2.NORM_MINMAX)
            return depth_norm
        except Exception:
            return self._synthetic_depth(img)

    def _synthetic_depth(self, img):
        h, w = img.shape[:2]
        gradient = np.linspace(0.0, 1.0, h, dtype=np.float32)
        return np.repeat(gradient[:, np.newaxis], w, axis=1)

    def render_diorama_frame(self, img, depth_map, shift_x=0.0, shift_y=0.0, zoom=1.0):
        h, w = img.shape[:2]
        grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
        map_x = (grid_x - (depth_map * shift_x)).astype(np.float32)
        map_y = (grid_y - (depth_map * shift_y)).astype(np.float32)
        remapped = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        if zoom != 1.0:
            cx, cy = w // 2, h // 2
            M = cv2.getRotationMatrix2D((cx, cy), 0, zoom)
            remapped = cv2.warpAffine(remapped, M, (w, h))
        return remapped
