"""Tests for PIL/Pillow extension."""

import pytest

Image = pytest.importorskip("PIL.Image")

import reprobate


class TestImage:
    def test_rgb_image(self):
        img = Image.new("RGB", (640, 480))
        r = reprobate.render(img, 200)
        assert "Image" in r
        assert "640x480" in r
        assert "RGB" in r

    def test_rgba_image(self):
        img = Image.new("RGBA", (100, 200))
        r = reprobate.render(img, 200)
        assert "100x200" in r
        assert "RGBA" in r

    def test_grayscale_image(self):
        img = Image.new("L", (32, 32))
        r = reprobate.render(img, 200)
        assert "32x32" in r
        assert "L" in r

    def test_budget_respected(self):
        img = Image.new("RGB", (1920, 1080))
        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(img, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
