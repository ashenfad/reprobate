"""Optional renderer for PIL/Pillow images."""

try:
    from PIL import Image
except ImportError:
    Image = None

from .registry import register

if Image is not None:

    @register(Image.Image)
    def render_image(obj: "Image.Image", budget: int) -> str:
        w, h = obj.size
        mode = obj.mode
        fmt = obj.format
        fmt_part = f", format={fmt}" if fmt else ""
        header = f"Image({w}x{h}, {mode}{fmt_part})"

        return header[:budget]
