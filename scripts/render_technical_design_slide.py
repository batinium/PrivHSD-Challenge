"""Render the technical design pitch slide asset."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "challenge" / "assets" / "technical_design_tradeoff_slide.png"

WIDTH = 1920
HEIGHT = 1080

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    width: int = 2,
    radius: int = 18,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def line_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    *,
    size: int,
    fill: str,
    bold: bool = False,
    anchor: str | None = None,
) -> None:
    draw.text(xy, text, fill=fill, font=font(size, bold=bold), anchor=anchor)


def wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    *,
    size: int,
    fill: str,
    max_width: int,
    line_gap: int = 8,
    bold: bool = False,
) -> int:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    fnt = font(size, bold=bold)
    for word in words:
        candidate = " ".join([*current, word])
        bbox = draw.textbbox((0, 0), candidate, font=fnt)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=fill, font=fnt)
        y += size + line_gap
    return y


def wrap_lines_by_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    fnt: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        bbox = draw.textbbox((0, 0), candidate, font=fnt)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def bullet_list(
    draw: ImageDraw.ImageDraw,
    items: list[str],
    xy: tuple[int, int],
    *,
    size: int,
    fill: str,
    max_width: int,
    bullet_fill: str,
    line_gap: int = 7,
) -> int:
    x, y = xy
    fnt = font(size)
    for item in items:
        draw.ellipse((x, y + 8, x + 9, y + 17), fill=bullet_fill)
        lines = wrap_lines_by_pixels(draw, item, fnt=fnt, max_width=max_width - 28)
        line_y = y
        for line in lines:
            draw.text((x + 22, line_y), line, fill=fill, font=fnt)
            line_y += size + 4
        y = line_y + line_gap
    return y


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: str,
    width: int = 5,
) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=fill, width=width)
    if x2 >= x1:
        points = [(x2, y2), (x2 - 16, y2 - 10), (x2 - 16, y2 + 10)]
    else:
        points = [(x2, y2), (x2 + 16, y2 - 10), (x2 + 16, y2 + 10)]
    draw.polygon(points, fill=fill)


def stage_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    title: str,
    body: list[str],
    fill: str,
    outline: str,
    title_size: int = 29,
    body_size: int = 19,
) -> None:
    rounded_box(draw, xy, fill=fill, outline=outline, width=3, radius=20)
    x1, y1, x2, _ = xy
    title_y = y1 + 24
    for line in title.split("\n"):
        line_text(
            draw,
            line,
            (x1 + 24, title_y),
            size=title_size,
            fill="#182238",
            bold=True,
        )
        title_y += title_size + 5
    y = title_y + 8
    for item in body:
        y = wrapped_text(
            draw,
            item,
            (x1 + 24, y),
            size=body_size,
            fill="#2B3748",
            max_width=x2 - x1 - 48,
            line_gap=5,
        )
        y += 8


def ladder_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    step: str,
    title: list[str],
    caption: str,
    fill: str,
    outline: str,
    bars: int,
) -> None:
    rounded_box(draw, xy, fill=fill, outline=outline, width=3, radius=18)
    x1, y1, _x2, _y2 = xy
    line_text(draw, step, (x1 + 18, y1 + 15), size=26, fill=outline, bold=True)
    title_y = y1 + 18
    for line in title:
        line_text(draw, line, (x1 + 58, title_y), size=21, fill="#182238", bold=True)
        title_y += 25
    line_text(draw, caption, (x1 + 18, y1 + 73), size=16, fill="#445164")
    for b in range(5):
        cx = x1 + 26 + b * 30
        cy = y1 + 110
        draw.ellipse(
            (cx, cy, cx + 16, cy + 16),
            fill=outline if b < bars else "#CFD6DF",
        )


def render() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#F6F8FC")
    draw = ImageDraw.Draw(image)

    # Background bands keep the public story, novelty, and implementation detail distinct.
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#F6F8FC")
    draw.rectangle((0, 850, WIDTH, HEIGHT), fill="#EEF3F7")

    # Public pipeline row.
    line_text(draw, "PUBLIC REVIEW FLOW", (82, 38), size=18, fill="#5D6878", bold=True)
    stages = [
        (
            (80, 68, 300, 240),
            "Input CSV",
            ["text + labels + IDs", "metadata preserved"],
            "#E9F2FF",
            "#3573B7",
        ),
        (
            (350, 50, 625, 258),
            "Privacy Detection",
            ["direct PII + author clues", "deterministic baseline always runs"],
            "#E8F7F4",
            "#1D8A78",
        ),
        (
            (675, 50, 950, 258),
            "Meaning\nProtection",
            ["target/action/negation kept", "cue loss flagged"],
            "#FFF5DF",
            "#C17E1C",
        ),
        (
            (1000, 50, 1275, 258),
            "LLM-Guided\nClassification",
            ["cleaned text only", "hate label + reason tags"],
            "#EDF1FA",
            "#506993",
        ),
        (
            (1325, 50, 1600, 258),
            "Residual PII\nCheck",
            ["validate LLM suggestions", "review metadata only"],
            "#F2F7FF",
            "#5577AD",
        ),
        (
            (1650, 68, 1840, 240),
            "Human\nReview",
            ["review queue", "protected text + flags"],
            "#EAF7EF",
            "#2F8A5F",
        ),
    ]
    for xy, title, body, fill, outline in stages:
        stage_card(
            draw,
            xy,
            title=title,
            body=body,
            fill=fill,
            outline=outline,
            title_size=24,
            body_size=17,
        )

    for start_x, end_x in [
        (300, 350),
        (625, 675),
        (950, 1000),
        (1275, 1325),
        (1600, 1650),
    ]:
        arrow(draw, (start_x + 14, 154), (end_x - 14, 154), fill="#7A8594", width=5)

    # Current design band: one protected review path, not a public candidate ladder.
    rounded_box(
        draw,
        (80, 318, 1840, 818),
        fill="#FFFFFF",
        outline="#D3DBE6",
        width=2,
        radius=24,
    )
    rounded_box(
        draw,
        (112, 350, 544, 786),
        fill="#122033",
        outline="#122033",
        width=0,
        radius=20,
    )
    line_text(draw, "CURRENT DESIGN", (140, 390), size=20, fill="#9BC7FF", bold=True)
    line_text(draw, "Privacy-Minimized", (140, 450), size=38, fill="#FFFFFF", bold=True)
    line_text(draw, "Review Layer", (140, 500), size=42, fill="#FFFFFF", bold=True)
    wrapped_text(
        draw,
        "Produce one protected text for review, then add LLM HSD signals and validated residual PII flags.",
        (142, 578),
        size=24,
        fill="#DDE7F6",
        max_width=360,
        line_gap=8,
    )

    # Single protected review path.
    review_steps = [
        (
            (610, 372, 828, 528),
            "Detect",
            ["PII, handles, locations", "author clues + metadata"],
            "#E8F7F4",
            "#1D8A78",
        ),
        (
            (866, 372, 1084, 528),
            "Mask",
            ["typed placeholders", "strict direct cleanup"],
            "#E2F4EE",
            "#168469",
        ),
        (
            (1122, 372, 1340, 528),
            "Preserve",
            ["target/action/negation", "quote + counterspeech"],
            "#FFF5DF",
            "#C17E1C",
        ),
        (
            (1378, 372, 1596, 528),
            "Classify",
            ["cleaned text only", "label + reason tags"],
            "#EDF1FA",
            "#506993",
        ),
        (
            (1634, 372, 1814, 528),
            "Flag",
            ["validated residual PII", "no auto-apply"],
            "#EAF7EF",
            "#2F8A5F",
        ),
    ]
    for xy, title, body, fill, outline in review_steps:
        stage_card(
            draw,
            xy,
            title=title,
            body=body,
            fill=fill,
            outline=outline,
            title_size=26,
            body_size=16,
        )
    for start_x, end_x in [(828, 866), (1084, 1122), (1340, 1378), (1596, 1634)]:
        arrow(draw, (start_x + 8, 441), (end_x - 8, 441), fill="#8A95A5", width=4)

    # Evidence panels.
    evidence_panels = [
        (
            (610, 568, 998, 714),
            "Privacy evidence",
            [
                "direct/quasi identifier reduction",
                "strict residual cleanup count",
                "metadata leakage signal",
            ],
            "#F8FBFA",
            "#B6CEC7",
            "#176D58",
        ),
        (
            (1034, 568, 1422, 714),
            "HSD context kept",
            [
                "target/action/negation retention",
                "target-group distribution retained",
                "quote/counterspeech cues",
            ],
            "#FFFCF3",
            "#D8BA75",
            "#9A6718",
        ),
        (
            (1458, 568, 1814, 714),
            "Review metadata",
            [
                "LLM hate label + reason tags",
                "residual PII suggestion status",
                "human decides, not AI",
            ],
            "#EDF3FF",
            "#9EB4D5",
            "#385D92",
        ),
    ]
    for xy, title, items, fill, outline, accent in evidence_panels:
        rounded_box(draw, xy, fill=fill, outline=outline, width=2, radius=16)
        x1, y1, x2, _ = xy
        line_text(draw, title, (x1 + 24, y1 + 24), size=24, fill=accent, bold=True)
        bullet_list(
            draw,
            items,
            (x1 + 26, y1 + 66),
            size=17,
            fill="#2E3B4C",
            max_width=x2 - x1 - 48,
            bullet_fill=accent,
            line_gap=0,
        )

    # Under the hood implementation band.
    line_text(draw, "UNDER THE HOOD", (82, 888), size=18, fill="#5D6878", bold=True)
    panels = [
        (
            "Always-on rules",
            ["regex/context detectors", "target + utility cue lexicons", "strict residual cleanup"],
            "#FFFFFF",
            "#B7C0CE",
        ),
        (
            "PII Assist",
            ["Presidio + scrubadub", "span fusion + cue-safe filters", "GLiNER explicit research path"],
            "#FFFFFF",
            "#B7C0CE",
        ),
        (
            "Model signals",
            [
                "local LLM HSD review",
                "binary labels + reason tags",
                "ML advisory remains fallback",
            ],
            "#FFFFFF",
            "#B7C0CE",
        ),
        (
            "Residual review",
            ["validate LLM PII suggestions", "reject placeholders/HSD cues", "metadata only; no auto-apply"],
            "#FFFFFF",
            "#B7C0CE",
        ),
    ]
    panel_x = 80
    for title, items, fill, outline in panels:
        rounded_box(
            draw,
            (panel_x, 918, panel_x + 420, 1040),
            fill=fill,
            outline=outline,
            width=2,
            radius=16,
        )
        line_text(draw, title, (panel_x + 22, 940), size=24, fill="#182238", bold=True)
        bullet_list(
            draw,
            items,
            (panel_x + 24, 978),
            size=16,
            fill="#334153",
            max_width=350,
            bullet_fill="#4776A8",
            line_gap=0,
        )
        panel_x += 445

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, quality=95)


if __name__ == "__main__":
    render()
