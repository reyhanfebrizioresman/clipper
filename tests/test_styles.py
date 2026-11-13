from clipper import render
from clipper.styles import STYLES


def test_burn_cmd_uses_selected_style():
    cmd = render.burn_cmd("in.mp4", "a.srt", "out.mp4", style=STYLES["bold"])
    assert STYLES["bold"].force_style in " ".join(cmd)


def test_burn_cmd_default_is_lato():
    assert STYLES["lato"].force_style in " ".join(render.burn_cmd("i.mp4", "a.srt", "o.mp4"))
