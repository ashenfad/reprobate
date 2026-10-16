"""Optional renderer for PIL/Pillow images."""

from .registry import register, register_lazy


def install() -> None:
    """Register the Pillow renderers.

    Run by the registry the first time it meets a PIL type: an
    object of that type exists, so PIL is already loaded and the
    import below costs nothing.
    """
    from PIL import Image

    @register(Image.Image)
    def render_image(obj: "Image.Image", budget: int) -> str:
        w, h = obj.size
        mode = obj.mode
        fmt = obj.format
        fmt_part = f", format={fmt}" if fmt else ""
        header = f"Image({w}x{h}, {mode}{fmt_part})"

        return header[:budget]


register_lazy("PIL", install)
