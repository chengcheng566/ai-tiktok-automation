from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
CONTENT_FILE = ROOT / "output" / "daily-content.txt"
OUTPUT_DIR = ROOT / "output" / "videos"
WORK_DIR = ROOT / "output" / "video_frames"


def check_dependencies() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed.")
        sys.exit(1)

    result = subprocess.run(
        ["ffmpeg", "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if result.returncode != 0:
        print("FFmpeg is not installed.")
        sys.exit(1)


def extract_section(text: str, name: str, next_names: list[str]) -> str:
    pattern = rf"\*\*{re.escape(name)}\*\*\s*(.*?)(?=\n\s*\*\*(?:{'|'.join(map(re.escape, next_names))})\*\*|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

    if not match:
        return ""

    return match.group(1).strip()


def load_content() -> dict[str, str]:
    if not CONTENT_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CONTENT_FILE}")

    text = CONTENT_FILE.read_text(encoding="utf-8", errors="replace")

    sections = [
        "TITLE",
        "HOOK",
        "SCRIPT_ENGLISH",
        "SCRIPT_BURMESE",
        "CAPTION",
        "HASHTAGS",
    ]

    data: dict[str, str] = {}

    for index, section in enumerate(sections):
        remaining = sections[index + 1 :]
        data[section] = extract_section(text, section, remaining)

    return data


def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"

        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def make_slide(text: str, filename: Path, title: bool = False) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1080, 1920

    image = Image.new("RGB", (width, height), (18, 18, 28))
    draw = ImageDraw.Draw(image)

    # Simple modern background
    draw.rectangle((0, 0, width, height), fill=(18, 18, 28))
    draw.ellipse((700, -180, 1250, 370), fill=(65, 55, 120))
    draw.ellipse((-250, 1450, 450, 2150), fill=(40, 85, 120))

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    try:
        title_font = ImageFont.truetype(bold_path, 76)
        body_font = ImageFont.truetype(font_path, 54)
        small_font = ImageFont.truetype(font_path, 34)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    text = text.strip()

    if title:
        font = title_font
        max_width = 900
    else:
        font = body_font
        max_width = 880

    lines = wrap_text(draw, text, font, max_width)

    line_height = 95 if title else 75
    total_height = len(lines) * line_height

    y = (height - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2

        draw.text(
            (x + 3, y + 3),
            line,
            font=font,
            fill=(0, 0, 0),
        )

        draw.text(
            (x, y),
            line,
            font=font,
            fill=(245, 245, 245),
        )

        y += line_height

    footer = "Global AI Content"
    bbox = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(
        ((width - (bbox[2] - bbox[0])) // 2, height - 120),
        footer,
        font=small_font,
        fill=(190, 190, 205),
    )

    image.save(filename, quality=95)


def build_video(data: dict[str, str]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in WORK_DIR.glob("*.png"):
        old_file.unlink()

    slides: list[tuple[str, str]] = []

    if data["TITLE"]:
        slides.append((data["TITLE"], "title"))

    if data["HOOK"]:
        slides.append((data["HOOK"], "body"))

    if data["SCRIPT_ENGLISH"]:
        # Keep the generated script readable in a short video.
        english = re.sub(r"\[[^\]]+\]", "", data["SCRIPT_ENGLISH"]).strip()
        slides.append((english, "body"))

    if data["SCRIPT_BURMESE"]:
        burmese = re.sub(r"\[[^\]]+\]", "", data["SCRIPT_BURMESE"]).strip()
        slides.append((burmese, "body"))

    if not slides:
        raise ValueError("No usable content was found.")

    frame_paths: list[Path] = []

    for index, (text, kind) in enumerate(slides):
        frame = WORK_DIR / f"slide_{index:02d}.png"
        make_slide(
            text=text,
            filename=frame,
            title=(kind == "title"),
        )
        frame_paths.append(frame)

    output_file = OUTPUT_DIR / "daily-tiktok.mp4"

    # Each slide stays on screen for 4 seconds.
    input_pattern = str(WORK_DIR / "slide_%02d.png")

    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        "1/4",
        "-i",
        input_pattern,
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-movflags",
        "+faststart",
        str(output_file),
    ]

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        raise RuntimeError("FFmpeg failed to create the video.")

    return output_file


def main() -> None:
    check_dependencies()

    data = load_content()

    output_file = build_video(data)

    print(f"Video created successfully: {output_file}")

    if data["CAPTION"]:
        print("\nCAPTION:")
        print(data["CAPTION"])

    if data["HASHTAGS"]:
        print("\nHASHTAGS:")
        print(data["HASHTAGS"])


if __name__ == "__main__":
    main()
