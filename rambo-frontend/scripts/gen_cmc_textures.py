"""Generate CMC poster textures into ../public/cmc/ (Pillow only).

  python rambo-frontend/scripts/gen_cmc_textures.py
  # or override output dir:
  CMC_OUT=some/dir python gen_cmc_textures.py

Produces:
  smoke-bg.png  : black base + gold smoke pooled at the edges (RGB)
  gold-dust.png : sparse glowing gold specks (transparent RGBA)
  grunge.png    : faint grain + scratches (transparent RGBA)

These are same-origin assets the poster (/card/:market) layers in; the export stays
canvas-clean. Overwrite smoke-bg.png with a ChatGPT plate, or drop cmc-logo.png, for
higher-end art (see ../public/cmc/README.md)."""
import os, random
from PIL import Image, ImageFilter, ImageChops, ImageDraw, ImageOps, ImageEnhance

OUT = os.environ.get("CMC_OUT",
                     os.path.join(os.path.dirname(__file__), "..", "public", "cmc"))
os.makedirs(OUT, exist_ok=True)
W, H = 1536, 1024
random.seed(7)


def value_noise():
    acc = Image.new("L", (W, H), 0)
    for octave, wt in [(2, 0.7), (3, 0.7), (4, 0.5), (5, 0.3), (6, 0.18)]:
        cw = 2 ** octave
        ch = max(1, round(cw * H / W))
        small = Image.new("L", (cw, ch))
        small.putdata([random.randint(0, 255) for _ in range(cw * ch)])
        up = small.resize((W, H), Image.BICUBIC).point(lambda p, wt=wt: int(p * wt))
        acc = ImageChops.add(acc, up)
    return ImageOps.autocontrast(acc.filter(ImageFilter.GaussianBlur(7)))


def edge_mask():
    m = Image.new("L", (W, H), 255)
    ImageDraw.Draw(m).ellipse([W * 0.07, -H * 0.05, W * 0.93, H * 1.05], fill=0)
    return m.filter(ImageFilter.GaussianBlur(150)).point(lambda p: int(p * 0.8))


def make_smoke():
    n = value_noise().point(lambda p: int((p / 255) ** 0.82 * 255))
    smoke = ImageEnhance.Contrast(ImageChops.multiply(n, edge_mask())).enhance(1.2)
    gold = ImageOps.colorize(smoke, black=(2, 1, 0), mid=(120, 88, 22), white=(232, 198, 112))
    ImageEnhance.Brightness(gold).enhance(0.85).save(os.path.join(OUT, "smoke-bg.png"))


def make_dust():
    dust = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(dust)
    for _ in range(230):
        x, y, r = random.randint(0, W), random.randint(0, H), random.randint(1, 3)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(240, 207, 115, random.randint(120, 255)))
    glow = dust.filter(ImageFilter.GaussianBlur(2))
    Image.alpha_composite(glow, dust).save(os.path.join(OUT, "gold-dust.png"))


def make_grunge():
    # half-res keeps the PNG small (it's base64-inlined into the export); CSS cover
    # scales it up and the grain still reads.
    gw, gh = W // 2, H // 2
    alpha = Image.effect_noise((gw, gh), 55).point(lambda p: 0 if p < 165 else min(48, p - 165))
    g = Image.new("RGBA", (gw, gh), (205, 205, 205, 0))
    g.putalpha(alpha)
    gd = ImageDraw.Draw(g)
    for _ in range(14):
        x = random.randint(0, gw)
        gd.line([(x, random.randint(0, gh)), (x + random.randint(-16, 16), random.randint(0, gh))],
                fill=(220, 220, 220, 24), width=1)
    g.save(os.path.join(OUT, "grunge.png"), optimize=True)


if __name__ == "__main__":
    make_smoke(); make_dust(); make_grunge()
    for f in ("smoke-bg.png", "gold-dust.png", "grunge.png"):
        print(f, Image.open(os.path.join(OUT, f)).size)
    print("OUT:", os.path.abspath(OUT))
