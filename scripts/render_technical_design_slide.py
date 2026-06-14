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
) -> None:
    rounded_box(draw, xy, fill=fill, outline=outline, width=3, radius=20)
    x1, y1, x2, _ = xy
    line_text(draw, title, (x1 + 24, y1 + 24), size=29, fill="#182238", bold=True)
    y = y1 + 72
    for item in body:
        y = wrapped_text(
            draw,
            item,
            (x1 + 24, y),
            size=19,
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
    line_text(draw, "PUBLIC CONTRACT", (82, 38), size=18, fill="#5D6878", bold=True)
    stages = [
        (
            (80, 68, 330, 240),
            "Input CSV",
            ["text + labels + IDs", "metadata preserved"],
            "#E9F2FF",
            "#3573B7",
        ),
        (
            (390, 50, 735, 258),
            "Privacy Detection",
            ["direct PII, quasi IDs, author clues", "deterministic baseline always runs"],
            "#E8F7F4",
            "#1D8A78",
        ),
        (
            (790, 50, 1135, 258),
            "Meaning Protection",
            ["preserve target groups, actions, negation", "reject cue-loss candidates"],
            "#FFF5DF",
            "#C17E1C",
        ),
        (
            (1190, 50, 1535, 258),
            "HSD Classification",
            ["advisory hate/not-hate score", "target-group stats after scoring"],
            "#EDF1FA",
            "#506993",
        ),
        (
            (1590, 68, 1840, 240),
            "NGO Review",
            ["portal check queue", "protected text + score"],
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
        )

    for start_x, end_x in [(330, 390), (735, 790), (1135, 1190), (1535, 1590)]:
        arrow(draw, (start_x + 14, 154), (end_x - 14, 154), fill="#7A8594", width=5)

    # Novel contribution band.
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
    line_text(draw, "NOVEL ADDITION", (140, 390), size=20, fill="#9BC7FF", bold=True)
    line_text(draw, "Gradual PII", (140, 450), size=42, fill="#FFFFFF", bold=True)
    line_text(draw, "Removal Ladder", (140, 502), size=42, fill="#FFFFFF", bold=True)
    wrapped_text(
        draw,
        "Generate several candidates, each with stronger privacy. Score them and select the best tradeoff.",
        (142, 578),
        size=24,
        fill="#DDE7F6",
        max_width=360,
        line_gap=8,
    )

    # Candidate ladder.
    ladder = [
        ("0", ["Original"], "not released", "#F1F4F8", "#8C98A8", 0),
        ("1", ["Balanced", "mask"], "regex + context", "#E8F7F4", "#1D8A78", 2),
        ("2", ["Strict", "cleanup"], "residual PII rung", "#DDF3ED", "#168469", 3),
        ("3", ["PII Assist"], "Presidio + GLiNER", "#D7EFE8", "#117A62", 4),
        ("4", ["Style +", "policy"], "token candidate", "#D1E9E1", "#0D6F59", 5),
    ]
    x = 610
    y = 372
    card_w = 225
    for index, (step, title, caption, fill, outline, bars) in enumerate(ladder):
        x1 = x + index * 245
        ladder_card(
            draw,
            (x1, y, x1 + card_w, y + 126),
            fill=fill,
            outline=outline,
            step=step,
            title=title,
            caption=caption,
            bars=bars,
        )
        if index < len(ladder) - 1:
            arrow(draw, (x1 + card_w + 8, y + 63), (x1 + 238, y + 63), fill="#8A95A5", width=4)

    # Scoring panels.
    rounded_box(
        draw,
        (610, 548, 1076, 686),
        fill="#F8FBFA",
        outline="#B6CEC7",
        width=2,
        radius=16,
    )
    line_text(draw, "Privacy gain score", (636, 572), size=25, fill="#176D58", bold=True)
    bullet_list(
        draw,
        ["direct/quasi identifier reduction", "residual warning count", "metadata leakage signal"],
        (638, 610),
        size=18,
        fill="#2E3B4C",
        max_width=390,
        bullet_fill="#176D58",
        line_gap=2,
    )
    rounded_box(
        draw,
        (1112, 548, 1578, 720),
        fill="#FFFCF3",
        outline="#D8BA75",
        width=2,
        radius=16,
    )
    line_text(draw, "HSD score preservation", (1138, 572), size=25, fill="#9A6718", bold=True)
    bullet_list(
        draw,
        [
            "target/action/negation retention",
            "target-group distribution retained",
            "advisory hate-score drift",
            "quote/counterspeech cues",
        ],
        (1140, 610),
        size=18,
        fill="#2E3B4C",
        max_width=390,
        bullet_fill="#B77A1E",
        line_gap=2,
    )
    rounded_box(
        draw,
        (1614, 548, 1814, 686),
        fill="#EDF3FF",
        outline="#5577AD",
        width=2,
        radius=16,
    )
    line_text(draw, "Selector", (1644, 574), size=27, fill="#385D92", bold=True)
    wrapped_text(
        draw,
        "best privacy/utility tradeoff",
        (1644, 610),
        size=18,
        fill="#2E3B4C",
        max_width=136,
        line_gap=5,
    )
    arrow(draw, (1578, 606), (1614, 606), fill="#7A8594", width=4)

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
            ["Presidio, scrubadub, GLiNER", "span fusion + cue-safe filters", "optional, local-only default"],
            "#FFFFFF",
            "#B7C0CE",
        ),
        (
            "Model signals",
            [
                "token-policy RoBERTa + HateBERT",
                "Dynabench RoBERTa HSD probe",
                "Cardiff Twitter RoBERTa hate probe",
            ],
            "#FFFFFF",
            "#B7C0CE",
        ),
        (
            "Next verifier",
            ["gpt-oss-safeguard-20b", "structured policy review", "supports NGO check flow"],
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
