"""Single-line normalization shared by engine renderers."""


def single_line(text: str) -> str:
    """Collapse newline variants into visible escapes."""
    return text.replace("\r\n", "\\n").replace("\r", "\\r").replace("\n", "\\n")
