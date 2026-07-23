# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the legacy KiCad ActionPlugin runtime."""

from .coilforge.legacy_plugin import SpiralDialog, SpiralPlugin, ValidationError

__all__ = ("SpiralDialog", "SpiralPlugin", "ValidationError")
