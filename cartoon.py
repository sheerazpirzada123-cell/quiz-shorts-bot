"""2D cartoon engine (sab kuch code se, koi image API nahi).

- Characters: bade gol sar wale rang-birangi cartoon (baal, skin, kapde, hijab/cap/glasses/beard), 13 emotions, 14 actions,
  lip-sync, palkein jhapakna, aankhon ki nazar doosre character ki taraf.
- Backgrounds: bedroom, kitchen, living, school, office, street, park, night, cafe, plain.
- Props: phone, alarm, pizza, exam paper... (sticker mein pop-in).
- Effects: paseena, gussa, aansu, hearts, sparkles, "?" "!" , zzz, speed lines. Camera: slow zoom + shake.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
GROUND = 955
FLOOR_Y = 840
AA = cv2.LINE_AA
OUT = (42, 30, 30)


def hexbgr(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


SKINS = {k: hexbgr(v) for k, v in dict(light="#FFD9BD", tan="#EDB98A", brown="#C58A5E", dark="#8D5B3C").items()}
HAIRS = {k: hexbgr(v) for k, v in dict(black="#2B2220", brown="#6B4026", blonde="#E3B94F", red="#B5442A", gray="#A8A8AE").items()}
CLOTH = {k: hexbgr(v) for k, v in dict(
    red="#E5484D", blue="#3E7BFA", green="#2FB36B", orange="#FF922B", purple="#8E5BE8", yellow="#FCC419",
    teal="#20C5B5", pink="#FF7EB6", gray="#8A94A6", black="#3A3F4B", white="#F4F6F8").items()}
PANTS = [hexbgr("#3B4A6B"), hexbgr("#4A4A55"), hexbgr("#6B4F3A")]
WHITE = (255, 255, 255)


def shade(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def mix(a, b, k):
    return tuple(int(a[i] * (1 - k) + b[i] * k) for i in range(3))


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def pop_scale(t):
    if t <= 0:
        return 0.0
    if t >= 0.35:
        return 1.0
    x = t / 0.35
    return ease_out(x) * (1 + 0.18 * math.sin(x * math.pi))


# ---------------------------------------------------------------- drawing helpers
def _i(p):
    return (int(round(p[0])), int(round(p[1])))


def circ(img, c, r, col, ow=4):
    r = max(1, int(round(r)))
    cv2.circle(img, _i(c), r, col, -1, AA)
    if ow:
        cv2.circle(img, _i(c), r, OUT, ow, AA)


def ell(img, c, ax, col, ang=0, a0=0, a1=360, ow=0, fill=True):
    ax = (max(1, int(round(ax[0]))), max(1, int(round(ax[1]))))
    if fill:
        cv2.ellipse(img, _i(c), ax, ang, a0, a1, col, -1, AA)
    if ow:
        cv2.ellipse(img, _i(c), ax, ang, a0, a1, OUT, ow, AA)


def poly(img, pts, col, ow=4, closed=True):
    p = np.array([_i(q) for q in pts], np.int32)
    cv2.fillPoly(img, [p], col, AA)
    if ow:
        cv2.polylines(img, [p], closed, OUT, ow, AA)


def pline(img, pts, w, col, ow=0):
    p = np.array([_i(q) for q in pts], np.int32)
    if ow:
        cv2.polylines(img, [p], False, OUT, int(w + 2 * ow), AA)
    cv2.polylines(img, [p], False, col, max(1, int(w)), AA)


def limb(img, pts, w, col, ow=4):
    pline(img, pts, w, col, ow)
    for q in (pts[0], pts[-1]):
        cv2.circle(img, _i(q), max(1, int(w / 2)), col, -1, AA)


def _rr_fill(img, x0, y0, x1, y1, r, col):
    r = int(max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2)))
    cv2.rectangle(img, (int(x0 + r), int(y0)), (int(x1 - r), int(y1)), col, -1, AA)
    cv2.rectangle(img, (int(x0), int(y0 + r)), (int(x1), int(y1 - r)), col, -1, AA)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(img, (int(cx), int(cy)), r, col, -1, AA)


def rrect(img, x0, y0, x1, y1, r, col, ow=4):
    if ow:
        _rr_fill(img, x0 - ow, y0 - ow, x1 + ow, y1 + ow, r + ow, OUT)
    _rr_fill(img, x0, y0, x1, y1, r, col)


def blend_ell(img, c, ax, col, alpha):
    x0, y0 = int(c[0] - ax[0] - 2), int(c[1] - ax[1] - 2)
    x1, y1 = int(c[0] + ax[0] + 3), int(c[1] + ax[1] + 3)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    ov = roi.copy()
    cv2.ellipse(ov, (int(c[0] - x0), int(c[1] - y0)), (int(ax[0]), int(ax[1])), 0, 0, 360, col, -1, AA)
    cv2.addWeighted(ov, alpha, roi, 1 - alpha, 0, roi)


def heart(img, c, s, col, ow=3):
    x, y = c
    pts = []
    for a in np.linspace(0, 2 * math.pi, 40):
        px = 16 * math.sin(a) ** 3
        py = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((x + px * s / 16, y + py * s / 16))
    poly(img, pts, col, ow)


def star4(img, c, r, col):
    x, y = c
    pts = [(x, y - r), (x + r * 0.28, y - r * 0.28), (x + r, y), (x + r * 0.28, y + r * 0.28),
           (x, y + r), (x - r * 0.28, y + r * 0.28), (x - r, y), (x - r * 0.28, y - r * 0.28)]
    poly(img, pts, col, 0)


def drop(img, x, y, r, col=(235, 190, 90)):
    pts = [(x, y - r * 1.9)] + [(x + r * math.cos(a), y + r * math.sin(a)) for a in np.linspace(-0.15 * math.pi, 1.15 * math.pi, 16)]
    poly(img, pts, col, 2)


# ---------------------------------------------------------------- text sprites
_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
          "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
_cache = {}


def _font(size):
    for p in _FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_sprite(text, size, fill=WHITE, stroke=OUT, sw=None, pill=None, pad=(26, 12)):
    key = (text, size, fill, stroke, sw, pill, pad)
    if key in _cache:
        return _cache[key]
    font = _font(size)
    sw = max(2, size // 9) if sw is None else sw
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = tmp.textbbox((0, 0), text, font=font, stroke_width=sw)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    # NOTE: colours are BGR; PIL gets them as if RGB, so the array comes back already in BGR order.
    if pill:
        w, h = tw + pad[0] * 2 + 6, th + pad[1] * 2 + 6
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((2, 2, w - 3, h - 3), radius=h // 2, fill=tuple(pill) + (255,), outline=(30, 30, 42, 255), width=4)
        d.text((w // 2 - tw // 2 - bb[0], h // 2 - th // 2 - bb[1]), text, font=font, fill=tuple(fill) + (255,))
    else:
        w, h = tw + 10, th + 10
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((5 - bb[0], 5 - bb[1]), text, font=font, fill=tuple(fill) + (255,), stroke_width=sw, stroke_fill=tuple(stroke) + (255,))
    arr = np.array(im)
    spr = (np.ascontiguousarray(arr[:, :, :3]), arr[:, :, 3].astype(np.float32) / 255.0)
    if len(_cache) > 400:
        _cache.clear()
    _cache[key] = spr
    return spr


def blit(img, spr, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    rgb, a = spr
    if scale <= 0.02 or alpha <= 0:
        return
    h, w = a.shape
    if abs(scale - 1.0) > 0.01 or abs(rot) > 0.1:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, scale)
        nw, nh = int(w * scale + abs(rot) * 2 + 4), int(h * scale + abs(rot) * 2 + 4)
        M[0, 2] += nw / 2 - w / 2
        M[1, 2] += nh / 2 - h / 2
        rgb = cv2.warpAffine(rgb, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=0)
        a = cv2.warpAffine(a, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=0)
        h, w = a.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0c, y0c = max(0, x0), max(0, y0)
    x1c, y1c = min(W, x0 + w), min(H, y0 + h)
    if x1c <= x0c or y1c <= y0c:
        return
    aa = a[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)][:, :, None] * alpha
    src = rgb[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)].astype(np.float32)
    roi = img[y0c:y1c, x0c:x1c].astype(np.float32)
    img[y0c:y1c, x0c:x1c] = (src * aa + roi * (1 - aa)).astype(np.uint8)


# ---------------------------------------------------------------- backgrounds
def _grad(h, top, bot):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    return (np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t).astype(np.uint8)


def _floor(img, col, line, y0=FLOOR_Y, planks=True):
    img[y0:] = col
    cv2.line(img, (0, y0), (W, y0), OUT, 4, AA)
    if planks:
        for i, y in enumerate(range(y0 + 52, H, 74)):
            cv2.line(img, (0, y), (W, y), line, 3, AA)


def _window(img, x, y, w, h, sky=(240, 205, 150), night=False):
    rrect(img, x, y, x + w, y + h, 10, (255, 255, 255), 5)
    cv2.rectangle(img, (x + 10, y + 10), (x + w - 10, y + h - 10), (95, 60, 40) if night else sky, -1)
    cv2.line(img, (x + w // 2, y + 10), (x + w // 2, y + h - 10), (255, 255, 255), 6, AA)
    cv2.line(img, (x + 10, y + h // 2), (x + w - 10, y + h // 2), (255, 255, 255), 6, AA)
    if night:
        circ(img, (x + w * 0.72, y + h * 0.28), 16, (170, 235, 250), 0)


def _clock(img, c, r, t=0.0):
    circ(img, c, r, (255, 255, 255), 4)
    for a in range(12):
        ang = a * math.pi / 6
        cv2.line(img, _i((c[0] + (r - 7) * math.sin(ang), c[1] - (r - 7) * math.cos(ang))),
                 _i((c[0] + (r - 2) * math.sin(ang), c[1] - (r - 2) * math.cos(ang))), OUT, 2, AA)
    cv2.line(img, _i(c), _i((c[0] + r * 0.5 * math.sin(2.4), c[1] - r * 0.5 * math.cos(2.4))), OUT, 4, AA)
    cv2.line(img, _i(c), _i((c[0] + r * 0.75 * math.sin(0.5), c[1] - r * 0.75 * math.cos(0.5))), OUT, 3, AA)


def make_bg(kind, seed=0):
    rnd = np.random.RandomState(seed)
    img = np.zeros((H, W, 3), np.uint8)
    k = kind if kind in ("bedroom", "kitchen", "living", "school", "office", "street", "park", "night", "cafe", "plain") else "plain"
    if k == "bedroom":
        img[:] = hexbgr("#D9C7F2")
        for x in range(0, W, 90):
            cv2.line(img, (x, 0), (x, FLOOR_Y), hexbgr("#CDB8EA"), 3, AA)
        _floor(img, hexbgr("#C9A27A"), hexbgr("#B58D66"))
        _window(img, 70, 190, 190, 230, night=False)
        rrect(img, 470, 360, 720, 520, 18, hexbgr("#7C6BD6"), 5)
        rrect(img, 450, 330, 560, 420, 28, hexbgr("#FFFFFF"), 5)
        rrect(img, 470, 440, 720, 560, 18, hexbgr("#9D8CF0"), 5)
        poly(img, [(420, 520), (460, 520), (470, 560), (410, 560)], hexbgr("#8D5B3C"), 4)
        rrect(img, 330, 210, 420, 330, 10, hexbgr("#FFE08A"), 5)
        heart(img, (375, 270), 34, hexbgr("#FF6B81"), 3)
    elif k == "kitchen":
        img[:] = hexbgr("#FFF1C9")
        for y in range(40, 560, 70):
            for x in range(0, W, 70):
                cv2.rectangle(img, (x, y), (x + 70, y + 70), hexbgr("#FFE8A8"), 1, AA)
        _floor(img, hexbgr("#E9D5B5"), hexbgr("#D8BE98"))
        rrect(img, -20, 560, 740, 850, 6, hexbgr("#B9824F"), 5)
        rrect(img, -20, 530, 740, 580, 6, hexbgr("#EDEDED"), 5)
        rrect(img, 40, 70, 250, 330, 14, hexbgr("#D8ECF2"), 5)
        cv2.line(img, (40, 200), (250, 200), OUT, 4, AA)
        rrect(img, 440, 130, 700, 260, 12, hexbgr("#F28C5B"), 5)
        for x in (500, 570, 640):
            circ(img, (x, 215), 9, (255, 255, 255), 3)
        circ(img, (360, 120), 44, hexbgr("#8FA3AD"), 5)
        _clock(img, (360, 120), 38)
    elif k == "living":
        img[:] = hexbgr("#A9E0DB")
        _floor(img, hexbgr("#B98F6A"), hexbgr("#A57D59"))
        rrect(img, 150, 150, 570, 400, 18, (40, 34, 34), 6)
        rrect(img, 165, 165, 555, 385, 10, hexbgr("#5F7C94"), 0)
        rrect(img, -30, 540, 740, 760, 50, hexbgr("#E87A5D"), 6)
        rrect(img, -30, 480, 300, 600, 40, hexbgr("#F08F72"), 5)
        rrect(img, 430, 480, 750, 600, 40, hexbgr("#F08F72"), 5)
        ell(img, (620, 330), (28, 20), hexbgr("#8D5B3C"), ow=4)
        for a in (-50, -20, 10, 40):
            ell(img, (620 + a * 0.8, 270), (16, 50), hexbgr("#2FB36B"), ang=a, ow=4)
    elif k == "school":
        img[:] = hexbgr("#CDEBC8")
        _floor(img, hexbgr("#D9B88B"), hexbgr("#C4A075"))
        rrect(img, 70, 120, 650, 440, 12, hexbgr("#2F6B55"), 8)
        pline(img, [(120, 200), (230, 190), (320, 215)], 6, (255, 255, 255))
        pline(img, [(120, 270), (300, 280), (430, 262)], 6, (255, 255, 255))
        _clock(img, (600, 60), 42)
        for x in (90, 330, 560):
            rrect(img, x, 560, x + 170, 590, 6, hexbgr("#C98F52"), 5)
            cv2.line(img, (x + 25, 590), (x + 25, 700), OUT, 6, AA)
            cv2.line(img, (x + 145, 590), (x + 145, 700), OUT, 6, AA)
    elif k == "office":
        img[:] = hexbgr("#DCE6F2")
        _floor(img, hexbgr("#9AA6B8"), hexbgr("#8894A8"), planks=False)
        _window(img, 60, 130, 330, 300, night=False)
        rrect(img, 450, 140, 680, 300, 8, (255, 255, 255), 5)
        pline(img, [(480, 270), (520, 220), (560, 245), (630, 175)], 7, hexbgr("#2FB36B"))
        rrect(img, 360, 560, 740, 600, 6, hexbgr("#B9824F"), 5)
        rrect(img, 480, 450, 650, 560, 8, (60, 50, 50), 5)
        rrect(img, 492, 462, 638, 548, 4, hexbgr("#9ED8F2"), 0)
    elif k == "street":
        img[:] = _grad(H, hexbgr("#8FD3F4"), hexbgr("#E4F6FF"))
        for x, w, h, c in ((-20, 190, 520, "#F2A65A"), (180, 160, 640, "#7AA7D9"), (350, 210, 460, "#E87A7A"), (570, 190, 600, "#8CC084")):
            rrect(img, x, FLOOR_Y - 120 - h, x + w, FLOOR_Y - 60, 6, hexbgr(c), 5)
            for wy in range(FLOOR_Y - 120 - h + 40, FLOOR_Y - 150, 90):
                for wx in range(x + 28, x + w - 40, 62):
                    cv2.rectangle(img, (wx, wy), (wx + 36, wy + 50), hexbgr("#FFF7D1"), -1, AA)
                    cv2.rectangle(img, (wx, wy), (wx + 36, wy + 50), OUT, 3, AA)
        img[FLOOR_Y - 60:] = hexbgr("#C9CED6")
        cv2.line(img, (0, FLOOR_Y - 60), (W, FLOOR_Y - 60), OUT, 4, AA)
        img[FLOOR_Y + 20:] = hexbgr("#7C828E")
        cv2.line(img, (0, FLOOR_Y + 20), (W, FLOOR_Y + 20), OUT, 4, AA)
        for x in range(0, W, 140):
            cv2.rectangle(img, (x + 20, 1170), (x + 100, 1186), (255, 255, 255), -1, AA)
    elif k == "park":
        img[:] = _grad(H, hexbgr("#8FD3F4"), hexbgr("#EAF8FF"))
        circ(img, (580, 170), 64, hexbgr("#FFD43B"), 5)
        for cx, cy, s in ((150, 160, 1.0), (400, 260, 0.8)):
            for dx, r in ((-40, 36), (0, 50), (45, 36)):
                cv2.circle(img, (int(cx + dx * s), int(cy)), int(r * s), (255, 255, 255), -1, AA)
        cv2.ellipse(img, (160, FLOOR_Y), (360, 200), 0, 180, 360, hexbgr("#79C86B"), -1, AA)
        cv2.ellipse(img, (600, FLOOR_Y), (360, 260), 0, 180, 360, hexbgr("#5DB35C"), -1, AA)
        img[FLOOR_Y:] = hexbgr("#6CC165")
        cv2.line(img, (0, FLOOR_Y), (W, FLOOR_Y), OUT, 4, AA)
        for tx in (90, 600):
            rrect(img, tx - 18, 470, tx + 18, FLOOR_Y, 6, hexbgr("#8D5B3C"), 5)
            circ(img, (tx, 420), 100, hexbgr("#3FA34D"), 5)
            circ(img, (tx - 50, 470), 62, hexbgr("#3FA34D"), 5)
            circ(img, (tx + 50, 470), 62, hexbgr("#3FA34D"), 5)
    elif k == "night":
        img[:] = _grad(H, hexbgr("#101A3F"), hexbgr("#2B3A7A"))
        for _ in range(60):
            x, y = rnd.randint(0, W), rnd.randint(0, 560)
            cv2.circle(img, (x, y), rnd.randint(1, 3), (255, 255, 235), -1, AA)
        circ(img, (560, 150), 62, hexbgr("#FFF1B8"), 0)
        circ(img, (582, 136), 56, hexbgr("#18224A"), 0)
        for x, w, h in ((-20, 200, 460), (190, 150, 600), (330, 220, 380), (560, 200, 540)):
            rrect(img, x, FLOOR_Y - 90 - h, x + w, FLOOR_Y - 40, 4, hexbgr("#1B2550"), 4)
            for wy in range(FLOOR_Y - 90 - h + 40, FLOOR_Y - 130, 80):
                for wx in range(x + 24, x + w - 36, 56):
                    on = rnd.rand() > 0.45
                    cv2.rectangle(img, (wx, wy), (wx + 30, wy + 44), hexbgr("#FFD86B") if on else hexbgr("#2D3A70"), -1, AA)
        img[FLOOR_Y - 40:] = hexbgr("#3B4468")
        cv2.line(img, (0, FLOOR_Y - 40), (W, FLOOR_Y - 40), OUT, 4, AA)
        img[FLOOR_Y + 30:] = hexbgr("#2A3050")
    elif k == "cafe":
        img[:] = hexbgr("#F6D7B0")
        _floor(img, hexbgr("#8D5B3C"), hexbgr("#7A4D32"))
        rrect(img, 60, 120, 400, 330, 12, hexbgr("#2F3B3B"), 6)
        pline(img, [(100, 180), (300, 180)], 6, (255, 255, 255))
        pline(img, [(100, 240), (350, 240)], 6, (255, 255, 255))
        for x in (470, 600):
            cv2.line(img, (x, 0), (x, 190), OUT, 4, AA)
            cv2.ellipse(img, (x, 200), (62, 52), 0, 180, 360, hexbgr("#FFC857"), -1, AA)
            cv2.ellipse(img, (x, 200), (62, 52), 0, 180, 360, OUT, 5, AA)
        rrect(img, -20, 560, 740, 850, 6, hexbgr("#B9824F"), 5)
        rrect(img, 80, 500, 190, 560, 8, (255, 255, 255), 5)
        rrect(img, 520, 470, 600, 560, 8, hexbgr("#EAD9C3"), 5)
    else:
        img[:] = hexbgr("#FFE9A8")
        for _ in range(26):
            x, y = rnd.randint(0, W), rnd.randint(0, H)
            cv2.circle(img, (x, y), rnd.randint(30, 90), hexbgr("#FFDF86"), -1, AA)
        _floor(img, hexbgr("#F6C66A"), hexbgr("#E8B455"), planks=False)
    return img


# ---------------------------------------------------------------- props (icons, centered at 0,0, ~120px)
def draw_prop(img, name, c, u, t):
    x, y = c

    def P(dx, dy):
        return (x + dx * u, y + dy * u)

    if name == "phone":
        rrect(img, *P(-30, -52), *P(30, 52), 12 * u, hexbgr("#2F3542"), 5)
        rrect(img, *P(-23, -42), *P(23, 40), 6 * u, hexbgr("#9ED8F2"), 0)
        circ(img, P(18, -44), 11 * u, hexbgr("#FF4D4D"), 3)
    elif name == "laptop":
        rrect(img, *P(-52, -40), *P(52, 22), 8 * u, hexbgr("#2F3542"), 5)
        rrect(img, *P(-44, -32), *P(44, 14), 4 * u, hexbgr("#9ED8F2"), 0)
        rrect(img, *P(-64, 22), *P(64, 36), 6 * u, hexbgr("#A9B1BD"), 5)
    elif name == "alarm":
        sh = math.sin(t * 38) * 4
        circ(img, P(-34 + sh, -46), 16 * u, hexbgr("#FFC857"), 4)
        circ(img, P(34 + sh, -46), 16 * u, hexbgr("#FFC857"), 4)
        circ(img, P(sh * 0.5, 4), 46 * u, hexbgr("#FF5A5F"), 5)
        circ(img, P(sh * 0.5, 4), 34 * u, (255, 255, 255), 3)
        cv2.line(img, _i(P(sh * 0.5, 4)), _i(P(sh * 0.5, -20)), OUT, 4, AA)
        cv2.line(img, _i(P(sh * 0.5, 4)), _i(P(16 + sh * 0.5, 12)), OUT, 4, AA)
    elif name == "pizza":
        poly(img, [P(-48, -42), P(48, -42), P(0, 54)], hexbgr("#FFC857"), 5)
        cv2.ellipse(img, _i(P(0, -42)), (int(52 * u), int(12 * u)), 0, 0, 360, hexbgr("#D99A3D"), -1, AA)
        cv2.ellipse(img, _i(P(0, -42)), (int(52 * u), int(12 * u)), 0, 0, 360, OUT, 4, AA)
        for dx, dy in ((-18, -18), (14, -12), (-2, 16)):
            circ(img, P(dx, dy), 9 * u, hexbgr("#E5484D"), 3)
    elif name == "burger":
        ell(img, P(0, -22), (50 * u, 28 * u), hexbgr("#E7A24B"), ow=5)
        rrect(img, *P(-52, -6), *P(52, 6), 4, hexbgr("#8D5B3C"), 4)
        rrect(img, *P(-54, 6), *P(54, 16), 4, hexbgr("#79C86B"), 4)
        ell(img, P(0, 30), (50 * u, 18 * u), hexbgr("#E7A24B"), ow=5)
    elif name == "coffee":
        rrect(img, *P(-34, -22), *P(30, 44), 12 * u, (255, 255, 255), 5)
        cv2.ellipse(img, _i(P(36, 8)), (int(18 * u), int(18 * u)), 0, -90, 90, OUT, 7, AA)
        for i, dx in enumerate((-16, 0, 16)):
            yy = -34 - 8 * math.sin(t * 4 + i)
            pline(img, [P(dx, -26), P(dx + 6, yy * 1.0 - 8), P(dx - 4, yy * 1.4 - 14)], 5, (235, 235, 235))
    elif name == "book":
        poly(img, [P(-54, -34), P(0, -26), P(0, 40), P(-54, 32)], hexbgr("#5B8DEF"), 5)
        poly(img, [P(54, -34), P(0, -26), P(0, 40), P(54, 32)], hexbgr("#7FA8FF"), 5)
        for dy in (-10, 4, 18):
            cv2.line(img, _i(P(-40, dy - 4)), _i(P(-10, dy)), (255, 255, 255), 3, AA)
    elif name == "exam":
        rrect(img, *P(-40, -52), *P(40, 52), 6 * u, (255, 255, 255), 5)
        for dy in (-30, -14, 2):
            cv2.line(img, _i(P(-26, dy)), _i(P(26, dy)), (190, 190, 190), 3, AA)
        blit(img, text_sprite("F", int(70 * u), fill=hexbgr("#E5484D"), sw=0), *P(0, 28), 1.0)
    elif name == "money":
        rrect(img, *P(-56, -32), *P(56, 32), 6 * u, hexbgr("#7BD389"), 5)
        circ(img, P(0, 0), 20 * u, hexbgr("#B7F0C0"), 4)
        blit(img, text_sprite("$", int(34 * u), fill=hexbgr("#2F8F46"), sw=0), *P(0, 0), 1.0)
    elif name == "wifi":
        for i, r in enumerate((60, 42, 24)):
            cv2.ellipse(img, _i(P(0, 36)), (int(r * u), int(r * u)), 0, 225, 315, OUT, 14, AA)
            cv2.ellipse(img, _i(P(0, 36)), (int(r * u), int(r * u)), 0, 225, 315, hexbgr("#3E7BFA") if i < 3 else OUT, 8, AA)
        circ(img, P(0, 36), 8 * u, hexbgr("#3E7BFA"), 3)
        if int(t * 3) % 2 == 0:
            pline(img, [P(-52, -40), P(52, 44)], 9, hexbgr("#E5484D"), 3)
    elif name == "battery":
        rrect(img, *P(-54, -30), *P(48, 30), 8 * u, (255, 255, 255), 5)
        rrect(img, *P(48, -12), *P(60, 12), 3, OUT, 0)
        rrect(img, *P(-48, -24), *P(-30, 24), 3 * u, hexbgr("#E5484D") if int(t * 3) % 2 == 0 else (255, 255, 255), 0)
    elif name == "heart":
        s = 1 + 0.08 * math.sin(t * 8)
        heart(img, P(0, 4), 70 * u * s, hexbgr("#FF4D6D"), 5)
    elif name == "lightbulb":
        circ(img, P(0, -14), 34 * u, hexbgr("#FFE066"), 5)
        rrect(img, *P(-16, 16), *P(16, 40), 4, hexbgr("#B7BDC8"), 4)
        for a in (-60, -20, 20, 60):
            ang = math.radians(a - 90)
            cv2.line(img, _i(P(52 * math.cos(ang), -14 + 52 * math.sin(ang))), _i(P(66 * math.cos(ang), -14 + 66 * math.sin(ang))), hexbgr("#FFC107"), 5, AA)
    elif name in ("question", "exclaim"):
        blit(img, text_sprite("?" if name == "question" else "!", int(120 * u), fill=hexbgr("#FFD43B"), sw=8), *P(0, 0), 1.0)
    elif name == "trophy":
        poly(img, [P(-34, -44), P(34, -44), P(26, 8), P(-26, 8)], hexbgr("#FFC83D"), 5)
        cv2.ellipse(img, _i(P(-34, -22)), (int(16 * u), int(16 * u)), 0, 90, 270, OUT, 6, AA)
        cv2.ellipse(img, _i(P(34, -22)), (int(16 * u), int(16 * u)), 0, -90, 90, OUT, 6, AA)
        rrect(img, *P(-8, 8), *P(8, 34), 2, hexbgr("#FFC83D"), 4)
        rrect(img, *P(-28, 34), *P(28, 50), 4, hexbgr("#8D5B3C"), 4)
    elif name == "bag":
        poly(img, [P(-42, -22), P(42, -22), P(50, 50), P(-50, 50)], hexbgr("#FF7EB6"), 5)
        cv2.ellipse(img, _i(P(0, -22)), (int(20 * u), int(22 * u)), 0, 180, 360, OUT, 6, AA)
    elif name == "tv":
        rrect(img, *P(-56, -38), *P(56, 36), 8 * u, hexbgr("#6B4F3A"), 5)
        rrect(img, *P(-46, -30), *P(46, 28), 4 * u, hexbgr("#9ED8F2"), 0)
        pline(img, [P(-20, -40), P(0, -58), P(20, -40)], 5, OUT)
    elif name == "bed":
        rrect(img, *P(-56, -4), *P(56, 28), 6 * u, hexbgr("#7C6BD6"), 5)
        rrect(img, *P(-56, -34), *P(-44, 40), 4, hexbgr("#8D5B3C"), 4)
        rrect(img, *P(-42, -18), *P(-12, 0), 8 * u, (255, 255, 255), 4)
    elif name == "cake":
        rrect(img, *P(-44, -2), *P(44, 40), 8 * u, hexbgr("#FFB3C7"), 5)
        rrect(img, *P(-34, -28), *P(34, -2), 8 * u, hexbgr("#FFE1A8"), 5)
        rrect(img, *P(-4, -48), *P(4, -28), 2, hexbgr("#3E7BFA"), 3)
        poly(img, [P(0, -66), P(-7, -52), P(7, -52)], hexbgr("#FF922B"), 2)
    elif name == "clock":
        _clock(img, P(0, 0), 52 * u)
    elif name == "fire":
        poly(img, [P(0, -58), P(30, -12), P(40, 24), P(18, 52), P(-18, 52), P(-40, 24), P(-28, -14), P(-8, 0)], hexbgr("#FF7A2F"), 5)
        poly(img, [P(0, -10), P(18, 20), P(10, 46), P(-10, 46), P(-18, 20)], hexbgr("#FFD43B"), 0)
    elif name == "skull":
        circ(img, P(0, -8), 40 * u, (255, 255, 255), 5)
        rrect(img, *P(-22, 22), *P(22, 48), 6, (255, 255, 255), 4)
        circ(img, P(-15, -8), 11 * u, OUT, 0)
        circ(img, P(15, -8), 11 * u, OUT, 0)
        poly(img, [P(0, 8), P(-6, 20), P(6, 20)], OUT, 0)
    elif name == "bell":
        sh = math.sin(t * 20) * 6
        poly(img, [P(-6 + sh, -46), P(6 + sh, -46), P(38 + sh, 30), P(-38 + sh, 30)], hexbgr("#FFC83D"), 5)
        circ(img, P(sh * 0.5, 40), 9 * u, hexbgr("#FFC83D"), 4)
        circ(img, P(30, -34), 14 * u, hexbgr("#FF4D4D"), 4)
    elif name == "chat":
        rrect(img, *P(-54, -40), *P(54, 28), 22 * u, (255, 255, 255), 5)
        poly(img, [P(-24, 26), P(-34, 52), P(-2, 26)], (255, 255, 255), 4, closed=False)
        for i, dx in enumerate((-24, 0, 24)):
            circ(img, P(dx, -6 + 5 * math.sin(t * 8 + i)), 8 * u, hexbgr("#6B7280"), 0)


# ---------------------------------------------------------------- character
BROW = {  # (raise, slant) slant>0: andar ka sira neecha (gussa), slant<0: andar ka sira upar (udaas / dar)
    "neutral": (0, 0), "happy": (6, -4), "sad": (0, -22), "angry": (-4, 24), "surprised": (18, -4),
    "scared": (12, -20), "excited": (12, -6), "embarrassed": (4, -14), "tired": (-6, -8), "smug": (2, 8),
    "confused": (8, -6), "laughing": (6, -6), "love": (6, -8),
}


def pose(action, t, speaking):
    s = math.sin
    p = dict(bob=s(t * 2.3) * 2.5, lean=0.0, hd=0.0, tilt=0.0, near=(78, 88), far=(80, 90), jump=0.0, shake=0.0,
             closed=False, phone=False, front=False, look=None, shx=0.0)
    a = action
    if speaking and a in ("idle", "talk"):
        a = "talk"
    if a == "talk":
        g, h = s(t * 5.4), s(t * 4.1 + 1.0)
        p.update(near=(50 + 14 * g, 10 + 42 * h), far=(80 + 6 * h, 90 + 4 * g), tilt=3 * s(t * 2.7), bob=s(t * 5.4) * 3)
    elif a == "wave":
        p.update(near=(-30, -92 + 30 * s(t * 10)), tilt=4, front=True)
    elif a == "point":
        p.update(near=(10 + 3 * s(t * 3), 6), lean=7)
    elif a == "shock":
        p.update(near=(-28, -72 + 5 * s(t * 24)), far=(-28, -72 + 5 * s(t * 24)), hd=-6, lean=-12,
                 jump=38 * max(0.0, 1 - t / 0.3) ** 2, shake=4.0)
    elif a == "think":
        p.update(near=(70, -125), far=(86, 92), tilt=6, hd=2, front=True, look=(0.2, -0.8))
    elif a == "shrug":
        p.update(near=(40, -38), far=(40, -38), shx=-8, tilt=-5 * s(t * 2))
    elif a == "celebrate":
        p.update(near=(-55, -82 + 10 * s(t * 9)), far=(-55, -82 + 10 * s(t * 9 + 1)), jump=abs(s(t * 7)) * 26)
    elif a == "sad":
        p.update(near=(88, 96), far=(88, 96), lean=8, hd=14, tilt=-4, bob=s(t * 1.6) * 2, look=(0.0, 0.9))
    elif a == "angry":
        p.update(near=(62, 112), far=(62, 112), shake=2.5, lean=6, jump=8 * abs(s(t * 9)))
    elif a == "facepalm":
        p.update(near=(75, -118), hd=10, tilt=-5, front=True, look=(0.0, 0.9))
    elif a == "phone":
        p.update(near=(62, -96), far=(82, 92), phone=True, hd=8, front=True, look=(0.0, 0.9))
    elif a == "sleep":
        p.update(near=(86, 92), far=(86, 92), closed=True, tilt=10, hd=12, bob=s(t * 1.4) * 5, lean=4)
    elif a == "laugh":
        p.update(near=(55, 160), far=(55, 160), jump=6 * abs(s(t * 8)), tilt=7 * s(t * 8), bob=s(t * 8) * 3)
    return p


def _hair_cap(img, hp, r, col, style, k, facing, t):
    top = []
    if style == "spiky":
        angs = np.linspace(192, 348, 15)
        for i, a in enumerate(angs):
            rr = 1.52 * r if i % 2 == 1 else 1.04 * r
            top.append(hp(rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a)) + 0.02 * r))
    else:
        for a in np.linspace(192, 348, 18):
            top.append(hp(1.06 * r * math.cos(math.radians(a)), 1.06 * r * math.sin(math.radians(a)) + 0.02 * r))
    line = []
    for x in np.linspace(0.97, -0.97, 14):
        y = -0.42 + 0.1 * math.sin(x * 5 + 0.6) + (0.05 if style == "long" else 0.0)
        line.append(hp(x * r, y * r))
    poly(img, top + line, col, 0)
    pline(img, top, 4, OUT)
    pline(img, [line[0], hp(0.9 * r, -0.3 * r)], 3, OUT)


def draw_char(img, ch, cx, gy, sc, action, emo, t, mouth, facing, speaking, other_dir=0.0, seed=0, enter=1.0):
    sc = sc * enter
    if sc < 0.05:
        return
    skin = SKINS.get(ch.get("skin", "tan"), SKINS["tan"])
    hcol = HAIRS.get(ch.get("hair_color", "black"), HAIRS["black"])
    shirt = CLOTH.get(ch.get("shirt", "blue"), CLOTH["blue"])
    pants = PANTS[seed % len(PANTS)]
    style = ch.get("hair", "short")
    acc = ch.get("accessory", "none")
    female = ch.get("gender") == "female"
    p = pose(action, t, speaking)

    shx = math.sin(t * 38) * p["shake"]
    jump = p["jump"]
    X = cx + shx

    def S(x, y):
        return (X + x * sc, gy + y * sc)

    leg, torso, hr = 78.0, 118.0, 90.0
    hip_y = -leg + p["bob"] * 0.4 - jump
    sh_y = hip_y - torso + p["bob"] * 0.6
    lean = p["lean"] * facing + p["shx"]
    shoulder = (lean, sh_y)
    hc_local = (lean * 1.4, sh_y - 8 - hr + p["hd"])
    tilt = math.radians(p["tilt"] * (1 if facing > 0 else -1))

    # shadow
    blend_ell(img, (X, gy + 4 * sc), (88 * sc * (1 - jump / 160), 14 * sc), (30, 30, 40), 0.28)

    # legs + shoes
    fy = -jump * 0.6
    for sx in (-1, 1):
        limb(img, [S(sx * 22, hip_y), S(sx * 26 + (sx * jump * 0.2), fy - 10)], 30 * sc, pants, int(4 * sc + 0.5))
        ell(img, S(sx * 28 + facing * 10, fy - 6), (26 * sc, 14 * sc), (245, 245, 245), ow=int(4 * sc + 0.5))

    # far arm (behind torso)
    def arm(side_dir, ang, hand_col, front_pass=False):
        sp = S(shoulder[0] + side_dir * 54, sh_y + 10 + p["shx"] * 0.3)
        a1, a2 = math.radians(ang[0]), math.radians(ang[1])
        l1, l2 = 60 * sc, 56 * sc
        el = (sp[0] + side_dir * l1 * math.cos(a1), sp[1] + l1 * math.sin(a1))
        hd = (el[0] + side_dir * l2 * math.cos(a2), el[1] + l2 * math.sin(a2))
        limb(img, [sp, el, hd], 24 * sc, shirt, int(4 * sc + 0.5))
        circ(img, hd, 17 * sc, skin, int(4 * sc + 0.5))
        return hd

    far_hand = arm(-facing, p["far"], skin)

    # torso
    rrect(img, X + (shoulder[0] - 58) * sc, gy + (sh_y - 8) * sc, X + (shoulder[0] + 58) * sc, gy + (hip_y + 14) * sc, 34 * sc, shirt, int(4 * sc + 0.5))
    ell(img, S(shoulder[0], hip_y + 6), (46 * sc, 8 * sc), pants, ow=0)
    if female and style != "hijab":
        poly(img, [S(shoulder[0] - 56, hip_y), S(shoulder[0] + 56, hip_y), S(shoulder[0] + 70, hip_y + 42), S(shoulder[0] - 70, hip_y + 42)], shade(shirt, 0.92), int(4 * sc + 0.5))
    # neck
    rrect(img, X + (shoulder[0] - 14) * sc, gy + (sh_y - 22) * sc, X + (shoulder[0] + 14) * sc, gy + (sh_y + 6) * sc, 6 * sc, shade(skin, 0.92), int(3 * sc + 0.5))

    near_hand = None
    if not p["front"]:
        near_hand = arm(facing, p["near"], skin)

    # head
    hcx, hcy = S(*hc_local)
    r = hr * sc
    k = sc

    def hp(dx, dy):
        c, s_ = math.cos(tilt), math.sin(tilt)
        return (hcx + dx * c - dy * s_, hcy + dx * s_ + dy * c)

    # --- back hair
    if style == "long":
        ell(img, hp(0, 0.5 * r), (1.14 * r, 1.4 * r), hcol, ang=math.degrees(tilt), ow=int(4 * sc + 0.5))
    elif style == "ponytail":
        sway = math.sin(t * 3) * 0.12
        pts = [hp(-facing * 0.7 * r, -0.4 * r), hp(-facing * (1.5 + sway) * r, 0.1 * r), hp(-facing * (1.45 + sway) * r, 0.9 * r), hp(-facing * 0.95 * r, 0.2 * r)]
        poly(img, pts, hcol, int(4 * sc + 0.5))
    elif style == "hijab":
        scarf = shade(shirt, 0.82) if ch.get("shirt") not in ("black",) else hexbgr("#5B6B8C")
        ell(img, hp(0, 0.25 * r), (1.2 * r, 1.32 * r), scarf, ang=math.degrees(tilt), ow=int(4 * sc + 0.5))
        poly(img, [hp(-1.0 * r, 0.5 * r), hp(1.0 * r, 0.5 * r), hp(1.0 * r, 1.45 * r), hp(0, 1.7 * r), hp(-1.0 * r, 1.45 * r)], scarf, int(4 * sc + 0.5))
    # ears
    if style != "hijab":
        for sx in (-1, 1):
            circ(img, hp(sx * 0.98 * r, 0.1 * r), 0.17 * r, skin, int(3 * sc + 0.5))
    # face
    face_col = skin
    if emo == "angry":
        face_col = mix(skin, (70, 70, 235), 0.28)
    elif emo in ("embarrassed", "love"):
        face_col = mix(skin, (150, 150, 250), 0.12)
    fr = r * (0.93 if style == "hijab" else 1.0)
    circ(img, (hcx, hcy), fr, face_col, int(5 * sc + 0.5))

    # --- front hair / headwear
    if style in ("short", "spiky", "long", "bun", "ponytail", "curly"):
        _hair_cap(img, hp, r, hcol, style, k, facing, t)
        if style == "bun":
            circ(img, hp(0, -1.2 * r), 0.36 * r, hcol, int(4 * sc + 0.5))
        if style == "curly":
            for a in np.linspace(195, 345, 8):
                circ(img, hp(1.1 * r * math.cos(math.radians(a)), 1.1 * r * math.sin(math.radians(a))), 0.27 * r, hcol, int(4 * sc + 0.5))
    elif style == "cap":
        capc = shade(shirt, 0.78) if ch.get("shirt") != "red" else hexbgr("#B03A3F")
        top = [hp(1.08 * r * math.cos(math.radians(a)), 1.08 * r * math.sin(math.radians(a)) + 0.0) for a in np.linspace(188, 352, 18)]
        poly(img, top + [hp(0.98 * r, -0.4 * r), hp(-0.98 * r, -0.4 * r)], capc, int(4 * sc + 0.5))
        ell(img, hp(facing * 0.62 * r, -0.4 * r), (0.72 * r, 0.14 * r), shade(capc, 0.85), ang=math.degrees(tilt), ow=int(4 * sc + 0.5))
    elif style == "hijab":
        scarf = shade(shirt, 0.82) if ch.get("shirt") not in ("black",) else hexbgr("#5B6B8C")
        top = [hp(1.2 * r * math.cos(math.radians(a)), 1.2 * r * math.sin(math.radians(a)) + 0.2 * r) for a in np.linspace(182, 358, 20)]
        inner = [hp(x * r, -0.5 * r + 0.1 * r * math.sin(x * 3)) for x in np.linspace(0.92, -0.92, 12)]
        poly(img, top + inner, scarf, 0)
        pline(img, inner, 4, OUT)
    elif style == "bald":
        ell(img, hp(-0.35 * r, -0.62 * r), (0.2 * r, 0.1 * r), mix(skin, WHITE, 0.45), ang=-30, ow=0)

    # --- blush
    blush = {"happy": 0.35, "excited": 0.4, "embarrassed": 0.75, "love": 0.7, "laughing": 0.4, "smug": 0.2}.get(emo, 0.0)
    if blush:
        for sx in (-1, 1):
            blend_ell(img, hp(sx * 0.58 * r, 0.3 * r), (0.2 * r, 0.12 * r), (130, 120, 255), blush)

    # --- eyes
    look = p["look"]
    if look is None:
        look = (other_dir * 0.75 + 0.12 * math.sin(t * 1.3), 0.05 * math.sin(t * 0.9))
    blink_phase = (t + seed * 0.37) % 3.4
    blinking = blink_phase < 0.12
    ex, ey = 0.36 * r, -0.04 * r
    rx, ry = 0.25 * r, 0.30 * r
    pr = 0.115 * r
    lid, lid_slant = 0.0, 0.0
    if emo in ("surprised", "scared"):
        rx, ry, pr = 0.28 * r, 0.36 * r, 0.075 * r
    elif emo == "tired":
        lid = 0.5
    elif emo == "smug":
        lid = 0.38
    elif emo == "angry":
        lid, lid_slant = 0.28, 0.5
    elif emo == "sad":
        lid, lid_slant = 0.18, -0.5
    elif emo == "excited":
        pr = 0.135 * r
    for sx in (-1, 1):
        c_ = hp(sx * ex, ey)
        if p["closed"] or emo == "laughing" or (blinking and emo != "surprised"):
            if emo == "laughing":
                pts = [hp(sx * ex - rx, ey + 0.05 * r), hp(sx * ex, ey - 0.13 * r), hp(sx * ex + rx, ey + 0.05 * r)]
            elif p["closed"]:
                pts = [hp(sx * ex - rx, ey - 0.02 * r), hp(sx * ex, ey + 0.1 * r), hp(sx * ex + rx, ey - 0.02 * r)]
            else:
                pts = [hp(sx * ex - rx, ey + 0.02 * r), hp(sx * ex + rx, ey + 0.02 * r)]
            pline(img, pts, max(3, 5 * sc), OUT)
            continue
        ell(img, c_, (rx, ry), (255, 255, 255), ang=math.degrees(tilt), ow=int(4 * sc + 0.5))
        lx = max(-0.5, min(0.5, look[0])) * (rx - pr) * 1.4
        ly = max(-0.8, min(0.9, look[1])) * (ry - pr) * 1.2
        pc = hp(sx * ex + lx, ey + ly)
        if emo == "love":
            heart(img, pc, pr * 3.0, (90, 90, 235), 0)
        else:
            circ(img, pc, pr, (45, 30, 30), 0)
            circ(img, (pc[0] - pr * 0.35, pc[1] - pr * 0.4), pr * 0.36, WHITE, 0)
            if emo == "excited":
                star4(img, (pc[0] + pr * 0.4, pc[1] + pr * 0.35), pr * 0.5, WHITE)
        if lid > 0:
            dy = ry * (2 * lid - 1)
            sl = lid_slant * ry * (1 if sx > 0 else -1) * -1
            lid_pts = [hp(sx * ex - rx * 1.25, ey - ry * 1.3), hp(sx * ex + rx * 1.25, ey - ry * 1.3),
                       hp(sx * ex + rx * 1.25, ey + dy + sl), hp(sx * ex - rx * 1.25, ey + dy - sl)]
            poly(img, lid_pts, face_col, 0)
            pline(img, [lid_pts[3], lid_pts[2]], max(3, 4 * sc), OUT)
        if emo == "tired":
            cv2.ellipse(img, _i(hp(sx * ex, ey + ry * 1.25)), (int(rx * 0.9), int(ry * 0.3)), math.degrees(tilt), 20, 160, (170, 120, 150), max(2, int(3 * sc)), AA)

    # brows
    raise_, slant = BROW.get(emo, (0, 0))
    bcol = shade(hcol, 0.9) if style != "bald" else (60, 50, 50)
    for sx in (-1, 1):
        by = ey - ry - 0.16 * r - raise_ * 0.012 * r
        inner_y = by + slant * 0.008 * r
        outer_y = by - slant * 0.004 * r
        extra = 0.0
        if emo == "smug" and sx == 1:
            extra = -0.12 * r
        if emo == "confused" and sx == -1:
            extra = -0.14 * r
        pline(img, [hp(sx * (ex + rx * 0.95), outer_y + extra), hp(sx * (ex - rx * 0.95), inner_y + extra)], max(4, 8 * sc), bcol)

    # nose
    pline(img, [hp(0.0, 0.14 * r), hp(0.03 * r, 0.2 * r)], max(2, 3 * sc), shade(skin, 0.7))

    # beard / mustache
    if acc == "beard":
        pts = [hp(0.98 * r * math.cos(math.radians(a)), 0.98 * r * math.sin(math.radians(a))) for a in np.linspace(18, 162, 16)]
        inner = [hp(0.62 * r * math.cos(math.radians(a)), 0.5 * r + 0.25 * r * math.sin(math.radians(a))) for a in np.linspace(150, 30, 10)]
        poly(img, pts + inner, hcol, 0)
    elif acc == "mustache":
        for sx in (-1, 1):
            ell(img, hp(sx * 0.2 * r, 0.42 * r), (0.2 * r, 0.07 * r), hcol, ang=math.degrees(tilt) + sx * 14, ow=0)

    # mouth
    mc = hp(0, 0.56 * r)
    mw = 0.3 * r
    lw = max(3, int(5 * sc))
    open_col = (50, 35, 120)
    if speaking and mouth > 0.06:
        w_ = {"surprised": 0.2, "scared": 0.26, "angry": 0.3, "sad": 0.24}.get(emo, 0.34) * r
        h_ = (0.04 + 0.26 * mouth) * r
        ell(img, mc, (w_, h_), open_col, ang=math.degrees(tilt), ow=lw)
        if h_ > 0.1 * r:
            ell(img, (mc[0], mc[1] + h_ * 0.45), (w_ * 0.6, h_ * 0.4), (120, 110, 235), ang=math.degrees(tilt), ow=0)
            if emo in ("happy", "excited", "laughing", "smug"):
                cv2.ellipse(img, _i(mc), (int(w_ * 0.92), int(h_ * 0.9)), math.degrees(tilt), 200, 340, WHITE, max(3, int(h_ * 0.35)), AA)
    else:
        if emo in ("happy", "excited", "laughing", "love"):
            wide = 0.36 * r if emo != "love" else 0.24 * r
            hh = 0.26 * r if emo in ("excited", "laughing") else 0.16 * r
            pts = [hp(-wide, 0.5 * r), hp(wide, 0.5 * r)] + [hp(wide * math.cos(a), 0.5 * r + hh * math.sin(a)) for a in np.linspace(0, math.pi, 14)]
            poly(img, pts, open_col, lw)
            pline(img, [hp(-wide * 0.8, 0.51 * r), hp(wide * 0.8, 0.51 * r)], max(3, int(0.07 * r)), WHITE)
        elif emo == "sad":
            cv2.ellipse(img, _i(hp(0, 0.7 * r)), (int(0.22 * r), int(0.13 * r)), math.degrees(tilt), 200, 340, OUT, lw, AA)
        elif emo == "angry":
            pts = [hp(-0.28 * r, 0.6 * r), hp(0.28 * r, 0.6 * r), hp(0.24 * r, 0.52 * r), hp(-0.24 * r, 0.52 * r)]
            poly(img, pts, (245, 245, 245), lw)
            pline(img, [hp(-0.12 * r, 0.52 * r), hp(-0.12 * r, 0.6 * r)], 2, OUT)
            pline(img, [hp(0.12 * r, 0.52 * r), hp(0.12 * r, 0.6 * r)], 2, OUT)
        elif emo == "surprised":
            ell(img, mc, (0.1 * r, 0.14 * r), open_col, ow=lw)
        elif emo == "scared":
            pts = [hp(-0.28 * r + i * 0.07 * r, 0.58 * r + (0.04 * r if i % 2 else -0.04 * r)) for i in range(9)]
            pline(img, pts, lw, OUT)
        elif emo == "embarrassed":
            pts = [hp(-0.18 * r + i * 0.06 * r, 0.58 * r + 0.025 * r * math.sin(t * 9 + i * 2)) for i in range(7)]
            pline(img, pts, lw, OUT)
        elif emo == "tired":
            pline(img, [hp(-0.15 * r, 0.62 * r), hp(0.15 * r, 0.6 * r)], lw, OUT)
        elif emo == "smug":
            pline(img, [hp(-0.2 * r, 0.6 * r), hp(0.05 * r, 0.62 * r), hp(0.3 * r, 0.5 * r)], lw, OUT)
        elif emo == "confused":
            pts = [hp(-0.24 * r + i * 0.06 * r, 0.6 * r + 0.045 * r * (1 if i % 2 else -1)) for i in range(9)]
            pline(img, pts, lw, OUT)
        else:
            cv2.ellipse(img, _i(hp(0, 0.5 * r)), (int(0.2 * r), int(0.1 * r)), math.degrees(tilt), 20, 160, OUT, lw, AA)

    # glasses
    if acc == "glasses":
        for sx in (-1, 1):
            cv2.circle(img, _i(hp(sx * ex, ey)), int(0.34 * r), OUT, max(3, int(5 * sc)), AA)
        pline(img, [hp(-ex + 0.34 * r, ey), hp(ex - 0.34 * r, ey)], max(3, int(4 * sc)), OUT)

    # near arm in front (think / facepalm / phone / wave)
    if p["front"]:
        near_hand = arm(facing, p["near"], skin)
        if p["phone"]:
            ph = (near_hand[0] + facing * 6 * sc, near_hand[1] - 34 * sc)
            rrect(img, ph[0] - 26 * sc, ph[1] - 44 * sc, ph[0] + 26 * sc, ph[1] + 44 * sc, 9 * sc, (60, 50, 47), int(4 * sc + 0.5))
            rrect(img, ph[0] - 20 * sc, ph[1] - 36 * sc, ph[0] + 20 * sc, ph[1] + 34 * sc, 5 * sc, (250, 225, 160), 0)
            circ(img, near_hand, 17 * sc, skin, int(4 * sc + 0.5))

    # emotion fx
    top = hp(0, -1.25 * r)
    fxt = t
    if emo == "angry":
        vx, vy = hp(0.62 * r, -0.62 * r)
        s_ = 12 * sc
        pline(img, [(vx - s_, vy - s_ * 0.4), (vx - s_ * 0.2, vy - s_ * 0.4), (vx - s_ * 0.4, vy - s_)], 4, (60, 60, 230))
        pline(img, [(vx + s_, vy - s_ * 0.4), (vx + s_ * 0.2, vy - s_ * 0.4), (vx + s_ * 0.4, vy - s_)], 4, (60, 60, 230))
        pline(img, [(vx - s_, vy + s_ * 0.4), (vx - s_ * 0.2, vy + s_ * 0.4), (vx - s_ * 0.4, vy + s_)], 4, (60, 60, 230))
        pline(img, [(vx + s_, vy + s_ * 0.4), (vx + s_ * 0.2, vy + s_ * 0.4), (vx + s_ * 0.4, vy + s_)], 4, (60, 60, 230))
        for i in range(2):
            ph_ = (fxt * 1.6 + i * 0.5) % 1.0
            circ(img, (top[0] + (-1 if i else 1) * 0.5 * r + (-1 if i else 1) * ph_ * 30 * sc, top[1] + 0.5 * r - ph_ * 90 * sc), (10 + 18 * ph_) * sc, (235, 235, 235), 0)
    elif emo in ("scared", "embarrassed"):
        ph_ = (fxt * 1.2) % 1.0
        drop(img, hp(0.95 * r, -0.5 * r + ph_ * 0.5 * r)[0], hp(0.95 * r, -0.5 * r + ph_ * 0.5 * r)[1], 8 * sc)
    elif emo == "sad":
        for sx in (-1, 1):
            ph_ = (fxt * 1.1 + (0.3 if sx > 0 else 0)) % 1.0
            drop(img, hp(sx * ex, ey + ry + ph_ * 0.9 * r)[0], hp(sx * ex, ey + ry + ph_ * 0.9 * r)[1], 7 * sc)
    elif emo == "laughing":
        for sx in (-1, 1):
            ph_ = (fxt * 2.0 + (0.4 if sx > 0 else 0)) % 1.0
            drop(img, hp(sx * (ex + rx + 0.2 * r), ey - 0.2 * r + ph_ * 0.4 * r)[0], hp(sx * (ex + rx + 0.2 * r), ey - 0.2 * r + ph_ * 0.4 * r)[1], 7 * sc)
    elif emo == "love":
        for i in range(3):
            ph_ = (fxt * 0.7 + i / 3.0) % 1.0
            heart(img, (top[0] + (i - 1) * 55 * sc + 10 * math.sin(fxt * 3 + i), top[1] + 40 * sc - ph_ * 120 * sc), 22 * sc, (110, 110, 250), 3)
    elif emo == "excited":
        for i in range(3):
            a_ = fxt * 3 + i * 2.1
            star4(img, (hcx + 1.35 * r * math.cos(a_ * 0.6 + i * 2.1), hcy - 0.2 * r + 1.1 * r * math.sin(a_ * 0.6 + i * 2.1)), (9 + 6 * math.sin(a_)) * sc, (80, 210, 255))
    elif emo == "confused":
        blit(img, text_sprite("?", int(70 * sc), fill=(60, 200, 255), sw=6), top[0] + 20 * sc, top[1] - 5 * sc, 1.0 + 0.08 * math.sin(fxt * 6), 1.0, 10 * math.sin(fxt * 4))
    elif emo == "surprised":
        blit(img, text_sprite("!", int(86 * sc), fill=(60, 200, 255), sw=7), top[0] + 38 * sc, top[1] - 5 * sc, 1.0 + 0.1 * math.sin(fxt * 12), 1.0, -8)
    if action == "sleep":
        for i in range(3):
            ph_ = (fxt * 0.5 + i / 3.0) % 1.0
            blit(img, text_sprite("Z", int((34 + 26 * ph_) * sc), fill=(255, 255, 255), sw=5), top[0] + 40 * sc + ph_ * 70 * sc, top[1] + 30 * sc - ph_ * 100 * sc, 1.0, 1.0 - ph_ * 0.6)
    return hcx, hcy


# ---------------------------------------------------------------- scene renderer
def _speed_lines(img, c, t, col=(255, 255, 255), alpha=0.5):
    ov = img.copy()
    n = 26
    for i in range(n):
        a = i * 2 * math.pi / n + 0.05 * math.sin(t * 20 + i)
        r0, r1 = 230 + 20 * (i % 3), 900
        p = np.array([[c[0] + r0 * math.cos(a - 0.025), c[1] + r0 * math.sin(a - 0.025)],
                      [c[0] + r1 * math.cos(a), c[1] + r1 * math.sin(a)],
                      [c[0] + r0 * math.cos(a + 0.025), c[1] + r0 * math.sin(a + 0.025)]], np.int32)
        cv2.fillPoly(ov, [p], col, AA)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)


class SceneRenderer:
    def __init__(self, bg_kind, seed=0, intro=False):
        self.bg = make_bg(bg_kind, seed)
        self.seed = seed
        self.intro = intro

    def positions(self, n):
        if n <= 1:
            return [(W * 0.5, 1.18)]
        return [(W * 0.27, 1.02), (W * 0.73, 1.02)]

    def frame(self, sc, cast, t, mouth, dur):
        img = self.bg.copy()
        n = min(len(cast), 2)
        pos = self.positions(n)
        spk = int(sc.get("speaker", 0)) % max(1, n)
        emo_main, act_main = sc.get("emotion", "neutral"), sc.get("action", "talk")
        emo_l, act_l = sc.get("listener_emotion", "neutral"), sc.get("listener_action", "idle")
        enter = pop_scale(t + 0.001) if self.intro else 1.0
        if act_main == "shock" and t < 0.55:
            _speed_lines(img, (pos[spk][0], 600), t, alpha=0.35 * (1 - t / 0.55))
        order = [i for i in range(n) if i != spk] + [spk]
        for i in order:
            cx, scl = pos[i]
            facing = 1 if (n == 1 or i == 0) else -1
            other = 0.0 if n == 1 else (1 if i == 0 else -1)
            ch = cast[i]
            if i == spk:
                draw_char(img, ch, cx, GROUND, scl, act_main, emo_main, t + 0.37 * i, mouth, facing, True, other, self.seed + i, enter)
            else:
                draw_char(img, ch, cx, GROUND, scl, act_l, emo_l, t + 0.37 * i, 0.0, facing, False, other, self.seed + i, enter)
        # name tags
        for i in range(n):
            nm = str(cast[i].get("name", ""))[:12].upper()
            if nm:
                on = i == spk
                spr = text_sprite(nm, 30, fill=OUT if on else (70, 60, 60), sw=0, pill=hexbgr("#FFD43B") if on else (255, 255, 255), pad=(18, 6))
                blit(img, spr, pos[i][0], GROUND + 46, 1.0 if on else 0.9)
        # label banner (POV / time stamp)
        lab = (sc.get("label") or "").strip()
        if lab:
            k = pop_scale(t - 0.05)
            spr = text_sprite(lab.upper(), 40, fill=OUT, sw=0, pill=(255, 255, 255), pad=(26, 12))
            blit(img, spr, W / 2, 128, min(1.0, 640 / spr[1].shape[1]) * k)
        # prop sticker
        pr = sc.get("prop", "none")
        if pr and pr != "none":
            k = pop_scale(t - 0.12)
            bob = math.sin(t * 3) * 6
            cy = 335 + bob
            cv2.circle(img, _i((W / 2, cy)), int(120 * k), (255, 255, 255), -1, AA)
            cv2.circle(img, _i((W / 2, cy)), int(120 * k), OUT, 6, AA)
            if k > 0.2:
                draw_prop(img, pr, (W / 2, cy), 1.25 * k, t)
        # camera: slow push-in + shake
        z = 1.0 + 0.045 * ease_out(t / max(dur, 0.5))
        tx = ty = 0.0
        if (act_main == "shock" or emo_main in ("angry", "scared")) and t < 0.5:
            amp = 9 * (1 - t / 0.5)
            tx, ty = amp * math.sin(t * 60), amp * math.cos(t * 53)
        M = np.float32([[z, 0, (1 - z) * W / 2 + tx], [0, z, (1 - z) * 640 + ty]])
        return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
