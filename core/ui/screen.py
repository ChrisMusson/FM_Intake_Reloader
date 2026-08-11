"""Read pixels from the screen and interpret the FM preview panel."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from core.platform import IS_WINDOWS
from core.ui.screen_config import RATINGS, STARS

DEBUG_CAPTURE_DIR = Path(__file__).resolve().parents[2] / "calibration_debug"


def _linux_capture_commands(path):
    commands = []

    if shutil.which("spectacle"):
        commands.append(["spectacle", "-b", "-n", "-o", path])
    if shutil.which("gnome-screenshot"):
        commands.append(["gnome-screenshot", "-f", path])
    if os.environ.get("DISPLAY") and shutil.which("import"):
        commands.append(["import", "-silent", "-window", "root", path])

    if not commands:
        raise RuntimeError(
            "No supported Linux screenshot backend found. Install spectacle or gnome-screenshot, "
            "or run an X11 session with ImageMagick's 'import' available."
        )

    return commands


def _wait_for_capture_file(path, timeout=3.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(interval)
    return path.exists() and path.stat().st_size > 0


def capture_region(region):
    left, top, width, height = region
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid region size: {region!r}")

    if IS_WINDOWS:
        import pyautogui

        return pyautogui.screenshot(region=region).convert("RGB")

    fd, raw_path = tempfile.mkstemp(prefix="fm_screenshot_", suffix=".png")
    os.close(fd)
    screenshot_path = Path(raw_path)
    errors = []

    try:
        for command in _linux_capture_commands(str(screenshot_path)):
            screenshot_path.unlink(missing_ok=True)
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)

            if completed.returncode == 0 and _wait_for_capture_file(screenshot_path):
                with Image.open(screenshot_path) as image:
                    image = image.convert("RGB")
                    if left < 0 or top < 0 or left + width > image.width or top + height > image.height:
                        raise RuntimeError(f"Requested region {region!r} is outside captured screen bounds {image.size!r}")
                    return image.crop((left, top, left + width, top + height))

            details = (completed.stderr.strip() or completed.stdout.strip() or "no output").replace("\n", " ")
            errors.append(f"{command[0]} failed: {details}")

        raise RuntimeError("; ".join(errors))
    finally:
        screenshot_path.unlink(missing_ok=True)


def sample_pixel(point):
    x, y = point
    return capture_region((x, y, 1, 1)).getpixel((0, 0))


def _count_matching_pixels_in_array(pixels, colour, tolerance=40):
    red = pixels[..., 0].astype(np.int16)
    green = pixels[..., 1].astype(np.int16)
    blue = pixels[..., 2].astype(np.int16)
    target_red, target_green, target_blue = colour
    mask = (np.abs(red - target_red) <= tolerance) & (np.abs(green - target_green) <= tolerance) & (np.abs(blue - target_blue) <= tolerance)
    return int(mask.sum())


def count_matching_pixels(region, colour, tolerance=40):
    return count_matching_pixels_in_image(capture_region(region), colour, tolerance=tolerance)


def count_matching_pixels_in_image(image, colour, tolerance=40):
    pixels = np.asarray(image, dtype=np.uint8)
    return _count_matching_pixels_in_array(pixels, colour, tolerance=tolerance)


def save_debug_image(image, label, directory=DEBUG_CAPTURE_DIR):
    """Write a capture to disk so a failed sample can be inspected afterwards."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{label}.png"
    image.save(path)
    return path


def guess_star_rating(yellow_pixels, half_increment=STARS.half_increment, full_increment=STARS.full_increment):
    stars, expected = min(
        ((index / 2, int(half_increment) * ((index + 1) // 2) + int(full_increment) * (index // 2)) for index in range(11)),
        key=lambda item: abs(yellow_pixels - item[1]),
    )
    return stars, expected, abs(yellow_pixels - expected)


def read_star_rating():
    yellow_pixels = count_matching_pixels(STARS.region, STARS.colour)
    stars, _expected, _difference = guess_star_rating(yellow_pixels)
    return stars, yellow_pixels


def read_letter_ratings(pixels_per_rating=RATINGS.pixels_per_rating):
    pixels = np.asarray(capture_region(RATINGS.region), dtype=np.uint8)
    counts = {grade: _count_matching_pixels_in_array(pixels, colour, tolerance=0) for grade, colour in RATINGS.colours.items()}
    return "".join(grade * max(0, int(round(counts[grade] / pixels_per_rating))) for grade in sorted(counts))
