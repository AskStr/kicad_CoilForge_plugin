# -*- coding: utf-8 -*-
"""Shared window sizing policy for wxPython and tkinter user interfaces."""

PREFERRED_WINDOW_WIDTH = 1360
PREFERRED_WINDOW_HEIGHT = 880
MINIMUM_WINDOW_WIDTH = 1040
MINIMUM_WINDOW_HEIGHT = 680
WINDOW_HORIZONTAL_MARGIN = 32
WINDOW_VERTICAL_MARGIN = 72
CONTENT_PADDING = 8
WORKSPACE_MAIN_WEIGHT = 65
WORKSPACE_SIDEBAR_WEIGHT = 35
WORKSPACE_MAIN_RATIO = (
    float(WORKSPACE_MAIN_WEIGHT)
    / (WORKSPACE_MAIN_WEIGHT + WORKSPACE_SIDEBAR_WEIGHT)
)


def workspace_main_width(total_width):
    """Return the fixed 65% width reserved for the parameter workspace."""
    return max(0, int(round(max(0, int(total_width)) * WORKSPACE_MAIN_RATIO)))


def fitted_window_size(screen_width, screen_height,
                       preferred_width=PREFERRED_WINDOW_WIDTH,
                       preferred_height=PREFERRED_WINDOW_HEIGHT,
                       minimum_width=MINIMUM_WINDOW_WIDTH,
                       minimum_height=MINIMUM_WINDOW_HEIGHT):
    """Return preferred/minimum sizes clamped to the available display."""
    screen_width = max(1, int(screen_width))
    screen_height = max(1, int(screen_height))
    usable_width = max(1, screen_width - WINDOW_HORIZONTAL_MARGIN)
    usable_height = max(1, screen_height - WINDOW_VERTICAL_MARGIN)
    width = min(max(1, int(preferred_width)), usable_width)
    height = min(max(1, int(preferred_height)), usable_height)
    min_width = min(max(1, int(minimum_width)), width)
    min_height = min(max(1, int(minimum_height)), height)
    return width, height, min_width, min_height


def centered_geometry(width, height, screen_width, screen_height):
    """Return a tkinter geometry string centered within the display."""
    x = max(0, (int(screen_width) - int(width)) // 2)
    y = max(0, (int(screen_height) - int(height)) // 2)
    return "{}x{}+{}+{}".format(int(width), int(height), x, y)
