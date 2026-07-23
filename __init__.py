from .coilforge.metadata import PLUGIN_VERSION

__version__ = PLUGIN_VERSION

try:
    import pcbnew  # noqa: F401
except ImportError:
    SpiralPlugin = None
else:
    from .kicad_spiral_plugin import SpiralPlugin
    SpiralPlugin().register()
