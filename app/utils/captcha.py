from __future__ import annotations

import base64
import io
import random
import string

from PIL import Image, ImageDraw, ImageFont

# 去除易混淆字符
_CHARS = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - 旧版 Pillow
        return ImageFont.load_default()


def generate_captcha(length: int = 4, width: int = 128, height: int = 44) -> tuple[str, str]:
    """返回 (验证码文本, data:image/png;base64,...)。"""
    code = "".join(random.SystemRandom().choice(_CHARS) for _ in range(length))
    image = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(image)
    font = _font(28)

    for _ in range(6):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(190, 200, 215), width=1)
    for _ in range(40):
        draw.point((random.randint(0, width), random.randint(0, height)), fill=(200, 205, 215))

    char_width = width // (length + 1)
    for index, char in enumerate(code):
        x = char_width * (index + 1) - 10 + random.randint(-3, 3)
        y = random.randint(2, 6)
        color = (random.randint(30, 90), random.randint(60, 120), random.randint(120, 190))
        draw.text((x, y), char, font=font, fill=color)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return code, f"data:image/png;base64,{encoded}"
