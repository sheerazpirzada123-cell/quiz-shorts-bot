"""Depth map: har background image se (1 = paas, 0 = door) float32 map. 2.5D parallax ke liye.
Pehle Depth Anything V2 Small (CPU, transformers) -> fail ho / DEPTH_OFFLINE=1 ho to ground-plane SYNTHETIC depth.
Depth map har location par sirf ek baar nikalti hai aur depthcache/ mein save hoti hai (actions/cache se model bhi cache hota hai)."""
import hashlib
import os

import cv2
import numpy as np

CACHE = "depthcache"
MODEL_ID = os.environ.get("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf")
_pipe, _failed = None, False


def ground_prior(h, w, hy=0.52):
    """Zameen ka synthetic depth: neeche (y bada) = paas, horizon par door. Zameen ke upar halka sa 'khada' hissa."""
    y = np.arange(h, dtype=np.float32)[:, None] / h
    g = np.clip((y - hy) / (1 - hy), 0, 1)
    ground = 0.22 + 0.78 * g                                    # perspective: inverse-depth y mein linear hoti hai
    above = 0.20 + 0.0 * y                                      # horizon ke upar ki cheezein (ghar, ped) = darmiyani door
    d = np.where(y >= hy, ground, above)
    return np.repeat(d, w, axis=1).astype(np.float32)


def sky_mask(img_bgr):
    """Aasman (upar ka neela/safed/halka hissa) = sabse door. Sirf upar ke 60% mein dhoondta hai."""
    h, w = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hh, ss, vv = hsv[..., 0], hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    blue = (hh > 85) & (hh < 130) & (ss > 0.12) & (vv > 0.45)
    cloud = (ss < 0.16) & (vv > 0.82)
    m = (blue | cloud).astype(np.float32)
    m[int(h * 0.62):] = 0
    m = cv2.GaussianBlur(m, (0, 0), 6)
    return np.clip(m * 1.6 - 0.3, 0, 1)


def synthetic(img_bgr, hy=0.52):
    h, w = img_bgr.shape[:2]
    d = ground_prior(h, w, hy)
    d = d * (1 - 0.8 * sky_mask(img_bgr))                       # aasman door
    return d


def _model():
    global _pipe, _failed
    if _pipe is None and not _failed:
        try:
            from transformers import pipeline
            _pipe = pipeline("depth-estimation", model=MODEL_ID, device=-1)
            print(f"[depth] model ready: {MODEL_ID}", flush=True)
        except Exception as e:
            _failed = True
            print("[depth] model load fail -> synthetic depth:", str(e)[:120], flush=True)
    return _pipe


def _neural(img_bgr):
    pipe = _model()
    if pipe is None:
        return None
    try:
        from PIL import Image
        h, w = img_bgr.shape[:2]
        im = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        out = pipe(im)["predicted_depth"]
        arr = np.asarray(out.squeeze().cpu().numpy() if hasattr(out, "cpu") else np.asarray(out), np.float32)
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_CUBIC)
        lo, hi = np.percentile(arr, 2), np.percentile(arr, 98)
        return np.clip((arr - lo) / max(1e-6, hi - lo), 0, 1).astype(np.float32)
    except Exception as e:
        print("[depth] inference fail:", str(e)[:120], flush=True)
        return None


def refine(d):
    """Edges saaf rakhte hue smooth (parallax mein 'tootna' kam), kam resolution par taake tez rahe."""
    h, w = d.shape
    s = cv2.resize(d, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    s = cv2.bilateralFilter(s, 7, 0.08, 7)
    s = cv2.GaussianBlur(s, (0, 0), 1.5)
    return np.clip(cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR), 0, 1)


def estimate(img_bgr, key=None):
    """img (BGR) -> depth float32 (h,w) 0..1 (1 = paas). Cache + fallback."""
    h, w = img_bgr.shape[:2]
    offline = bool(os.environ.get("DEPTH_OFFLINE"))
    key = key or hashlib.md5(img_bgr.tobytes()[::97]).hexdigest()[:12]
    path = os.path.join(CACHE, f"{key}{'_syn' if offline else ''}.npy")
    if os.path.exists(path):
        try:
            c = np.load(path)
            if c.shape == (h, w):
                return c
        except Exception:
            pass
    d = None if offline else _neural(img_bgr)
    prior = synthetic(img_bgr)
    if d is None:
        d = prior
    else:
        d = 0.80 * d + 0.20 * prior                              # model ko ground-plane se thoda stable rakho
        d = np.where(sky_mask(img_bgr) > 0.6, d * 0.3, d)
    d = refine(d)
    try:
        os.makedirs(CACHE, exist_ok=True)
        np.save(path, d.astype(np.float32))
    except Exception:
        pass
    return d.astype(np.float32)


def bake_dof(rgb, depth, focus=0.58):
    """Soft depth-of-field (bake): door ka background aur bahut paas ka foreground halka blur. rgb uint8 (h,w,3)."""
    b1 = cv2.GaussianBlur(rgb, (0, 0), 3.0)
    b2 = cv2.GaussianBlur(rgb, (0, 0), 7.5)
    k = np.clip(np.abs(depth - focus) - 0.12, 0, 0.5) / 0.5      # focus ke aas-paas bilkul saaf
    k = k[..., None]
    lvl1 = np.clip(k * 2, 0, 1)
    lvl2 = np.clip(k * 2 - 1, 0, 1)
    o = rgb.astype(np.float32) * (1 - lvl1) + b1.astype(np.float32) * lvl1
    o = o * (1 - lvl2) + b2.astype(np.float32) * lvl2
    return o.astype(np.uint8)


class Warper:
    """Ek scene ka parallax warper. rgb (H,W,3 uint8) + depth (H,W) ek hi size ke. Camera: zoom z, dolly (depth-wise zoom farq),
    pan (px), orbit (px, depth ke saath badhta shift). Maps kam resolution par banti hain (tez), phir full-res remap."""

    def __init__(self, rgb, depth, lo=4):
        self.rgb = rgb
        self.H, self.W = rgb.shape[:2]
        self.lo = lo
        self.lw, self.lh = self.W // lo, self.H // lo
        self.dep_lo = cv2.resize(depth, (self.lw, self.lh), interpolation=cv2.INTER_AREA)
        self.depth = depth
        gx, gy = np.meshgrid((np.arange(self.lw, dtype=np.float32) + 0.5) * lo, (np.arange(self.lh, dtype=np.float32) + 0.5) * lo)
        self.ux, self.uy = gx, gy

    @staticmethod
    def scale_at(d, z, dolly):
        return z * (1.0 + dolly * (d - 0.5))

    @staticmethod
    def shift_at(d, pan, orbit):
        return pan[0] + orbit * (d - 0.45), pan[1] + 0.25 * orbit * (d - 0.45)

    def depth_at(self, x, y, r=6):
        x0, x1 = int(max(0, min(self.W - 1, x - r))), int(max(1, min(self.W, x + r)))
        y0, y1 = int(max(0, min(self.H - 1, y - r))), int(max(1, min(self.H, y + r)))
        return float(self.depth[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)].mean())

    def project(self, x, y, d, z, dolly, pan, orbit):
        """Base-frame point (x,y) jiski depth d hai -> screen (x', y', scale)."""
        sc = self.scale_at(d, z, dolly)
        sx, sy = self.shift_at(d, pan, orbit)
        cx, cy = self.W / 2, self.H / 2
        return cx + sc * (x - cx) + sx, cy + sc * (y - cy) + sy, sc

    def render(self, z, dolly, pan, orbit, iters=2):
        cx, cy = self.W / 2, self.H / 2
        sx, sy = self.ux, self.uy
        for _ in range(iters):
            d = cv2.remap(self.dep_lo, (sx / self.lo - 0.5).astype(np.float32), (sy / self.lo - 0.5).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            sc = z * (1.0 + dolly * (d - 0.5))
            px, py = pan[0] + orbit * (d - 0.45), pan[1] + 0.25 * orbit * (d - 0.45)
            sx = (cx + (self.ux - cx - px) / sc).astype(np.float32)
            sy = (cy + (self.uy - cy - py) / sc).astype(np.float32)
        mx = cv2.resize(sx.astype(np.float32), (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        my = cv2.resize(sy.astype(np.float32), (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        return cv2.remap(self.rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)   # kinaron par edge-fill
