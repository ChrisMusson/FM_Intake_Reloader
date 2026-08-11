import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from core.ui.screen import capture_region, count_matching_pixels_in_image, sample_pixel, save_debug_image

CONFIG_PATH = Path(__file__).resolve().parents[1] / "core" / "ui" / "screen_config.py"

STAR_COLOUR = (244, 188, 0)
RATING_COLOURS = {"A": (73, 230, 35), "B": (168, 222, 29), "C": (255, 214, 79), "D": (255, 135, 71), "E": (255, 108, 73), "F": (255, 84, 84)}
RATING_PIXELS_PER_RATING = 175
CONTINUE_TOLERANCE = 10

STEPS = [
    ("star_top_left", "Click the top-left of the region containing the star rating for the intake preview"),
    ("star_bottom_right", "Click the bottom-right of the region containing the star rating for the intake preview"),
    ("full_star_sample_top_left", "Click the top-left of any example of a star rating with a whole number of stars (no white stars)"),
    ("full_star_sample_bottom_right", "Click the bottom-right of that same region"),
    ("half_star_sample_top_left", "Click the top-left of any example of a star rating with a non-whole number of stars (no white stars)"),
    ("half_star_sample_bottom_right", "Click the bottom-right of that same region"),
    ("rating_top_left", "Click the top-left of the letter ratings region"),
    ("rating_bottom_right", "Click the bottom-right of the letter ratings region"),
    ("continue_pixel", "Click a pixel inside the Continue button that doesn't contain text"),
    ("continue_colour_sample", "Move your cursor off the Continue/Fixtures button so the colour isn't the hover colour, then click anywhere"),
    ("confirm_reload", "Click the centre of the 'No' option in the reload confirmation dialog"),
]


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Region:
    def __init__(self, left, top, width, height):
        self.left = left
        self.top = top
        self.width = width
        self.height = height

    def as_tuple(self):
        return (self.left, self.top, self.width, self.height)


def build_region(first, second):
    left = min(first.x, second.x)
    top = min(first.y, second.y)
    right = max(first.x, second.x)
    bottom = max(first.y, second.y)
    return Region(left, top, right - left + 1, bottom - top + 1)


def describe_colours(image, limit=6):
    """Summarise the most common colours in a capture, for working out what the stars are actually made of."""
    colours = sorted(image.convert("RGB").getcolors(maxcolors=1 << 24), reverse=True)
    return ", ".join(f"{colour}x{count}" for count, colour in colours[:limit])


def calculate_star_increments(full_pixels, full_rating, half_pixels, half_rating):
    if full_rating <= 0 or not math.isclose(full_rating, round(full_rating), abs_tol=1e-6):
        raise ValueError(f"Expected a whole-number full-star rating, got {full_rating!r}")
    if half_rating <= 0:
        raise ValueError(f"Expected a positive half-star rating, got {half_rating!r}")

    doubled_half = round(half_rating * 2)
    if not math.isclose(half_rating * 2, doubled_half, abs_tol=1e-6) or doubled_half % 2 == 0:
        raise ValueError(f"Expected a half-star rating ending in .5, got {half_rating!r}")

    if full_pixels <= 0:
        raise ValueError("The whole-star sample contained no star-coloured pixels")
    if half_pixels <= 0:
        raise ValueError("The half-star sample contained no star-coloured pixels")

    pixels_per_full_star = full_pixels / int(round(full_rating))
    completed_stars = math.floor(half_rating)
    half_increment = int(round(half_pixels - completed_stars * pixels_per_full_star))
    full_increment = int(round(pixels_per_full_star - half_increment))

    if half_increment <= 0 or full_increment <= 0:
        raise ValueError(f"Computed invalid star increments from samples: half={half_increment}, full={full_increment}")

    return (half_increment, full_increment)


def render_config(clicks, continue_colour, star_increments):
    star_region = build_region(clicks["star_top_left"], clicks["star_bottom_right"]).as_tuple()
    rating_region = build_region(clicks["rating_top_left"], clicks["rating_bottom_right"]).as_tuple()

    rating_colour_lines = ["    colours={"]
    for grade in sorted(RATING_COLOURS):
        rating_colour_lines.append(f'        "{grade}": {RATING_COLOURS[grade]},')
    rating_colour_lines.append("    },")

    lines = [
        '"""Auto-generated screen calibration values."""',
        "",
        "class StarsCalibration:",
        "    def __init__(self, region, colour, half_increment, full_increment):",
        "        self.region = region",
        "        self.colour = colour",
        "        self.half_increment = half_increment",
        "        self.full_increment = full_increment",
        "",
        "",
        "class RatingsCalibration:",
        "    def __init__(self, region, pixels_per_rating, colours):",
        "        self.region = region",
        "        self.pixels_per_rating = pixels_per_rating",
        "        self.colours = colours",
        "",
        "",
        "class ContinueButtonCalibration:",
        "    def __init__(self, xy, colour, tolerance):",
        "        self.xy = xy",
        "        self.colour = colour",
        "        self.tolerance = tolerance",
        "",
        "",
        "STARS = StarsCalibration(",
        f"    region={star_region},",
        f"    colour={STAR_COLOUR},",
        f"    half_increment={star_increments[0]},",
        f"    full_increment={star_increments[1]},",
        ")",
        "",
        "RATINGS = RatingsCalibration(",
        f"    region={rating_region},",
        f"    pixels_per_rating={RATING_PIXELS_PER_RATING},",
        *rating_colour_lines,
        ")",
        "",
        "CONTINUE_BUTTON = ContinueButtonCalibration(",
        f"    xy=({clicks['continue_pixel'].x}, {clicks['continue_pixel'].y}),",
        f"    colour={continue_colour},",
        f"    tolerance={CONTINUE_TOLERANCE},",
        ")",
        "",
        f"RELOAD_DIALOG_NO_BUTTON = ({clicks['confirm_reload'].x}, {clicks['confirm_reload'].y})",
        "",
    ]
    return "\n".join(lines)


class CalibrationApp:
    def __init__(self, root):
        self.root = root
        self.clicks = {}
        self.history = []
        self.marker_ids = []
        self.continue_colour = None
        self.full_star_pixels = None
        self.full_star_rating = None
        self.half_star_pixels = None
        self.half_star_rating = None
        self.continue_colour_prompt_shown = False
        self.reload_dialog_prompt_shown = False

        self.root.title("FM Screen Calibration")
        for attr, value in (("-fullscreen", True), ("-alpha", 0.78)):
            try:
                self.root.attributes(attr, value)
            except tk.TclError:
                pass
        self.root.configure(bg="#0f1720")

        self.canvas = tk.Canvas(self.root, bg="#0f1720", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        card_width = min(820, max(560, screen_width - 120))
        card_height = 250
        card_left = (screen_width - card_width) // 2
        card_top = max(60, (screen_height - card_height) // 2 - 120)
        card_right = card_left + card_width
        card_bottom = card_top + card_height
        title_y = card_top + 46
        instruction_y = title_y + 48
        helper_y = instruction_y + 68

        self.canvas.create_rectangle(card_left + 8, card_top + 10, card_right + 8, card_bottom + 10, fill="#0a0f16", outline="")
        self.canvas.create_rectangle(card_left, card_top, card_right, card_bottom, fill="#18232f", outline="#314355", width=1)
        self.canvas.create_rectangle(card_left + 24, card_top + 20, card_left + 96, card_top + 24, fill="#8fb7d8", outline="")
        self.canvas.create_text(
            card_left + 28, title_y, anchor="nw", fill="#f8fafc", font=("TkDefaultFont", 18, "bold"), text="FM Screen Calibration"
        )
        self.instruction_text = self.canvas.create_text(
            card_left + 28, instruction_y, anchor="nw", fill="#e2e8f0", width=card_width - 56, font=("TkDefaultFont", 14), text=""
        )
        self.canvas.create_text(
            card_left + 28,
            helper_y,
            anchor="nw",
            fill="#94a3b8",
            width=card_width - 56,
            font=("TkDefaultFont", 10),
            text=(
                "Left click to record. Right click to undo. Press Escape to quit. "
                "You will need one whole-star sample and one half-star sample visible behind the overlay. "
                "After choosing the Continue button pixel, move your cursor off the button and click again so the resting colour "
                "can be sampled automatically."
            ),
        )

        self.root.bind("<Button-1>", self.on_left_click)
        self.root.bind("<Button-3>", self.on_right_click)
        self.root.bind("<Escape>", self.on_escape)
        self.update_instruction()

    def current_step(self):
        if len(self.history) >= len(STEPS):
            return None
        return STEPS[len(self.history)]

    def update_instruction(self):
        step = self.current_step()
        text = "Calibration complete. Writing core/screen_config.py..." if step is None else step[1]
        self.canvas.itemconfigure(self.instruction_text, text=text)

    def draw_marker(self, point):
        radius = 7
        return self.canvas.create_oval(
            point.x - radius, point.y - radius, point.x + radius, point.y + radius, fill="#ef4444", outline="#ffffff", width=2
        )

    def prompt_for_continue_colour(self):
        if self.continue_colour_prompt_shown:
            return
        self.continue_colour_prompt_shown = True
        messagebox.showinfo(
            "Sample Continue Colour",
            (
                "Move your cursor off the Continue/Fixtures button so it returns to its resting colour, "
                "then click anywhere on this overlay. The click position does not matter."
            ),
            parent=self.root,
        )
        self.root.lift()
        self.root.focus_force()

    def prompt_for_reload_dialog(self):
        if self.reload_dialog_prompt_shown:
            return
        self.reload_dialog_prompt_shown = True
        messagebox.showinfo(
            "Open Reload Dialog",
            "Switch back to FM, open the 'load last game' confirmation dialog so the 'No' option is visible, then return here and press OK.",
            parent=self.root,
        )
        self.root.lift()
        self.root.focus_force()

    def wait_until_hidden(self, timeout=1.5, interval=0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update_idletasks()
            self.root.update()
            if not self.root.winfo_viewable():
                return
            time.sleep(interval)

    def run_without_overlay(self, callback, settle=0.35):
        self.root.withdraw()
        self.wait_until_hidden()
        time.sleep(settle)
        try:
            return callback()
        finally:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.update()

    def sample_continue_colour(self):
        point = self.clicks["continue_pixel"]
        return self.run_without_overlay(lambda: sample_pixel((point.x, point.y)))

    def sample_star_pixels(self, top_left_key, bottom_right_key):
        region = build_region(self.clicks[top_left_key], self.clicks[bottom_right_key]).as_tuple()
        label = top_left_key.replace("_top_left", "")

        yellow_pixels = self.capture_and_count(region, label)
        if yellow_pixels == 0:
            print(f"No star-coloured pixels in {region}, retrying with a longer settle...", flush=True)
            yellow_pixels = self.capture_and_count(region, f"{label}_retry", settle=1.0)

        return region, yellow_pixels

    def capture_and_count(self, region, label, settle=0.35):
        """Grab the whole screen once, then save both the screen and the cropped region for inspection."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        screen = self.run_without_overlay(lambda: capture_region((0, 0, screen_width, screen_height)), settle=settle)

        left, top, width, height = region
        crop = screen.crop((left, top, left + width, top + height))
        screen_path = save_debug_image(screen, f"{label}_screen")
        crop_path = save_debug_image(crop, f"{label}_region")
        print(f"Saved {screen_path} and {crop_path}", flush=True)
        print(f"Most common colours in {label}: {describe_colours(crop)}", flush=True)

        return count_matching_pixels_in_image(crop, STAR_COLOUR)

    def ask_star_rating(self, title, prompt, *, whole_number):
        while True:
            rating = simpledialog.askfloat(title, prompt, parent=self.root, minvalue=0.5, maxvalue=5.0)
            if rating is None:
                return None

            doubled = round(rating * 2)
            if not math.isclose(rating * 2, doubled, abs_tol=1e-6):
                messagebox.showerror("Invalid rating", "Use a star rating in 0.5 increments, such as 2, 3.5, or 4.")
                continue
            if whole_number and doubled % 2 != 0:
                messagebox.showerror("Invalid rating", "This sample must be a whole-number star rating, such as 2 or 4.")
                continue
            if not whole_number and doubled % 2 == 0:
                messagebox.showerror("Invalid rating", "This sample must include a half star, such as 2.5 or 4.5.")
                continue

            return doubled / 2

    def on_left_click(self, event):
        step = self.current_step()
        if step is None:
            return

        key, prompt = step
        point = Point(event.x_root, event.y_root)
        self.clicks[key] = point
        self.history.append(key)

        marker_id = None if key == "continue_colour_sample" else self.draw_marker(point)
        self.marker_ids.append(marker_id)
        print(f"{prompt}: ({point.x}, {point.y})", flush=True)

        if key == "continue_pixel":
            self.prompt_for_continue_colour()
        elif key == "full_star_sample_bottom_right":
            region, self.full_star_pixels = self.sample_star_pixels("full_star_sample_top_left", "full_star_sample_bottom_right")
            if not self.reject_empty_star_sample(region, "whole-star"):
                return
            self.full_star_rating = self.ask_star_rating(
                "Whole-Star Sample Rating", "Enter the displayed whole-number rating for this sample, such as 2 or 4.", whole_number=True
            )
            if self.full_star_rating is None:
                self.undo_star_sample()
                return
            print(f"Sampled whole-star region {region}: rating={self.full_star_rating} yellow_pixels={self.full_star_pixels}", flush=True)
        elif key == "half_star_sample_bottom_right":
            region, self.half_star_pixels = self.sample_star_pixels("half_star_sample_top_left", "half_star_sample_bottom_right")
            if not self.reject_empty_star_sample(region, "half-star"):
                return
            self.half_star_rating = self.ask_star_rating(
                "Half-Star Sample Rating",
                "Enter the displayed rating for this sample, including the half star, such as 2.5 or 4.5.",
                whole_number=False,
            )
            if self.half_star_rating is None:
                self.undo_star_sample()
                return
            print(f"Sampled half-star region {region}: rating={self.half_star_rating} yellow_pixels={self.half_star_pixels}", flush=True)
        elif key == "continue_colour_sample":
            self.continue_colour = self.sample_continue_colour()
            saved_point = self.clicks["continue_pixel"]
            print(f"Sampled CONTINUE_COLOUR at ({saved_point.x}, {saved_point.y}): {self.continue_colour}", flush=True)
            self.prompt_for_reload_dialog()

        self.update_instruction()
        if len(self.history) == len(STEPS):
            self.finish()

    def reject_empty_star_sample(self, region, description):
        sampled = self.full_star_pixels if description == "whole-star" else self.half_star_pixels
        if sampled:
            return True

        messagebox.showerror(
            "Empty sample",
            (
                f"No star-coloured pixels were found in the {description} region {region}.\n\n"
                "Check that the region covers the yellow stars and that FM is visible behind this overlay, "
                "then select the two corners again."
            ),
            parent=self.root,
        )
        self.undo_star_sample()
        return False

    def undo_star_sample(self):
        """Roll back both corner clicks of the sample being recorded."""
        self.undo_last()
        self.undo_last()
        self.update_instruction()

    def on_right_click(self, _event):
        self.undo_last()

    def undo_last(self):
        if not self.history:
            return

        key = self.history.pop()
        removed = self.clicks.pop(key)
        marker_id = self.marker_ids.pop()
        if marker_id is not None:
            self.canvas.delete(marker_id)

        if key == "confirm_reload":
            self.reload_dialog_prompt_shown = False
        elif key in {"half_star_sample_top_left", "half_star_sample_bottom_right"}:
            self.half_star_pixels = None
            self.half_star_rating = None
        elif key in {"full_star_sample_top_left", "full_star_sample_bottom_right"}:
            self.full_star_pixels = None
            self.full_star_rating = None
        elif key == "continue_colour_sample":
            self.continue_colour = None
            self.reload_dialog_prompt_shown = False
        elif key == "continue_pixel":
            self.continue_colour = None
            self.continue_colour_prompt_shown = False
            self.reload_dialog_prompt_shown = False

        print(f"Removed {key}: ({removed.x}, {removed.y})", flush=True)
        self.update_instruction()

    def on_escape(self, _event):
        self.root.destroy()

    def finish(self):
        if self.continue_colour is None:
            raise RuntimeError("Continue colour was not sampled")
        if self.full_star_pixels is None or self.full_star_rating is None:
            raise RuntimeError("Whole-star sample was not captured")
        if self.half_star_pixels is None or self.half_star_rating is None:
            raise RuntimeError("Half-star sample was not captured")

        star_increments = calculate_star_increments(self.full_star_pixels, self.full_star_rating, self.half_star_pixels, self.half_star_rating)
        output = render_config(self.clicks, self.continue_colour, star_increments)
        CONFIG_PATH.write_text(output, encoding="utf-8")

        print()
        print(f"Wrote {CONFIG_PATH}", flush=True)
        print(output, flush=True)

        self.root.clipboard_clear()
        self.root.clipboard_append(output)
        self.root.update()

        messagebox.showinfo(
            "Calibration complete",
            f"Done. core/screen_config.py was updated at:\n{CONFIG_PATH}\n\nThe new file contents were copied to your clipboard.",
            parent=self.root,
        )
        self.root.destroy()


def main():
    print("Calibration starting...", flush=True)
    print("Make sure the FM window is visible behind this overlay.", flush=True)
    print(f"Updated values will be written to {CONFIG_PATH}", flush=True)
    root = tk.Tk()
    CalibrationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
