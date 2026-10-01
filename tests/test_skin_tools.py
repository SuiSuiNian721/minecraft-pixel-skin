"""可执行的像素约束测试；不依赖角色名称或浏览器显示结果。"""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skin_tools.py"
spec = importlib.util.spec_from_file_location("skin_tools", SCRIPT)
skin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = skin
spec.loader.exec_module(skin)


def sample_template():
    base = [["."] * 8 for _ in range(8)]
    outer = [["."] * 8 for _ in range(8)]
    base[5][2] = "I"
    outer[5][2] = "-"
    return {
        "schema_version": 1, "id": "test_eye", "version": "0.1.0",
        "models": ["slim", "classic"], "approval": {"status": "pending"},
        "provenance": {"kind": "reconstructed_from_guide", "note": "测试样本"},
        "palette": {"I": {"rgba": [80, 170, 90, 255], "role": "iris"}},
        "surfaces": [{"face": "head.front", "base": base, "outer": outer}],
        "protected_visible": [{"face": "head.front", "xy": [2, 5], "role": "iris"}],
        "allowed_alpha": [],
    }


class SkinToolsTests(unittest.TestCase):
    def test_uv_has_exact_area_and_no_overlap_for_each_model(self):
        for model, expected in [("slim", 1568), ("classic", 1632)]:
            faces = skin.uv_faces(model)
            base, outer = skin.uv_masks(model)
            self.assertEqual(len(faces), 36)
            self.assertEqual(len(base), expected)
            self.assertEqual(len(outer), expected)
            self.assertFalse(base & outer)
        self.assertEqual(skin.uv_faces("slim")["leftArm.front"]["base"], [36, 52, 3, 12])
        self.assertEqual(skin.uv_faces("slim")["leftLeg.front"]["outer"], [4, 52, 4, 12])

    def test_pending_template_cannot_be_used_for_production(self):
        with self.assertRaisesRegex(ValueError, "未确认"):
            skin.compose_template(skin.blank_skin("slim"), sample_template(), "slim")

    def test_clear_and_keep_are_distinct_and_input_is_immutable(self):
        source = skin.blank_skin("slim")
        source.putpixel((42, 13), (100, 120, 140, 255))
        source.putpixel((43, 13), (110, 130, 150, 255))
        before = source.tobytes()
        result = skin.compose_template(source, sample_template(), "slim", purpose="review")
        self.assertEqual(result.getpixel((42, 13)), (0, 0, 0, 0))
        self.assertEqual(result.getpixel((43, 13)), (110, 130, 150, 255))
        self.assertEqual(source.tobytes(), before)
        self.assertEqual(skin.changed_pixels(source, result), [[10, 13], [42, 13]])

    def test_palette_change_does_not_change_footprint(self):
        t = sample_template()
        source = skin.blank_skin("slim")
        green = skin.compose_template(source, t, "slim", purpose="review")
        pink = skin.compose_template(source, t, "slim", {"I": [218, 90, 123, 255]}, "review")
        self.assertEqual(skin.changed_pixels(green, pink), [[10, 13]])
        with self.assertRaisesRegex(ValueError, "调色板"):
            skin.compose_template(source, t, "slim", {"unknown": [1, 2, 3, 255]}, "review")

    def test_character_palette_binding_must_be_explicit(self):
        t = sample_template()
        t["required_palette_bindings"] = ["I"]
        with self.assertRaisesRegex(ValueError, "绑定"):
            skin.compose_template(skin.blank_skin("slim"), t, "slim", purpose="review")
        result = skin.compose_template(skin.blank_skin("slim"), t, "slim", {"I": [200, 80, 100, 255]}, "review")
        self.assertEqual(result.getpixel((10, 13)), (200, 80, 100, 255))

    def test_checker_finds_occlusion_and_exact_coordinate(self):
        t = sample_template()
        im = skin.compose_template(skin.blank_skin("slim"), t, "slim", purpose="review")
        im.putpixel((42, 13), (70, 80, 90, 255))
        result = skin.validate_skin(im, "slim", templates=[t])
        errors = [x for x in result["errors"] if x["code"] == "eye_occluded"]
        self.assertEqual([x["xy"] for x in errors], [[42, 13]])

    def test_declared_lens_alpha_is_local_and_exact(self):
        im = skin.blank_skin("slim")
        im.putpixel((42, 13), (30, 40, 50, 128))
        allowed = [{"face": "head.front", "layer": "outer", "xy": [2, 5], "values": [128]}]
        self.assertTrue(skin.validate_skin(im, "slim", allowed_alpha=allowed)["passed"])
        im.putpixel((43, 13), (30, 40, 50, 128))
        result = skin.validate_skin(im, "slim", allowed_alpha=allowed)
        errors = [x for x in result["errors"] if x["code"] == "undeclared_alpha"]
        self.assertEqual([x["xy"] for x in errors], [[43, 13]])
        im.putpixel((42, 13), (30, 40, 50, 64))
        self.assertFalse(skin.validate_skin(im, "slim", allowed_alpha=allowed)["passed"])

    def test_invalid_base_and_unused_uv_are_rejected(self):
        im = skin.blank_skin("slim")
        im.putpixel((8, 8), (0, 0, 0, 0))
        im.putpixel((0, 0), (10, 20, 30, 255))
        codes = {x["code"] for x in skin.validate_skin(im, "slim")["errors"]}
        self.assertIn("base_alpha", codes)
        self.assertIn("unused_uv", codes)

    def test_bad_template_matrices_and_unknown_color_are_rejected(self):
        for mutation in ("bad_width", "unknown_color", "clear_base"):
            t = sample_template()
            if mutation == "bad_width":
                t["surfaces"][0]["base"][0] = ["."] * 7
            elif mutation == "unknown_color":
                t["surfaces"][0]["base"][0][0] = "missing"
            else:
                t["surfaces"][0]["base"][0][0] = "-"
            with self.assertRaises(ValueError):
                skin.validate_template(t, "slim")

    def test_exact_extraction_round_trip_preserves_both_face_layers(self):
        im = skin.blank_skin("slim")
        im.putpixel((42, 13), (30, 40, 50, 128))
        t = skin.extract_template(im, "head.front", "slim", "sample", {"kind": "exact_png"})
        result = skin.compose_template(skin.blank_skin("slim", (1, 2, 3, 255)), t, "slim", purpose="review")
        for box in ((8, 8, 16, 16), (40, 8, 48, 16)):
            self.assertEqual(result.crop(box).tobytes(), im.crop(box).tobytes())

    def test_exclusive_write_and_two_pixel_diff(self):
        a = skin.blank_skin("slim")
        b = a.copy()
        b.putpixel((8, 8), (1, 2, 3, 255))
        b.putpixel((9, 8), (4, 5, 6, 255))
        self.assertEqual(skin.changed_pixels(a, b), [[8, 8], [9, 8]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            skin.write_json(path, {"中文": "正确"})
            with self.assertRaises(FileExistsError):
                skin.write_json(path, {})
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_catalog_detects_stale_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            t = sample_template()
            skin.write_json(root / "template.json", t)
            index = {"entries": [{"id": t["id"], "version": "old", "state": "candidate", "path": "template.json"}], "production_ready_count": 0}
            skin.write_json(root / "index.json", index)
            report = skin.validate_catalog(root / "index.json")
            self.assertFalse(report["passed"])
            self.assertTrue(any(e["code"] == "catalog_version_mismatch" for e in report["errors"]))

    def test_eye_templates_preserve_existing_outer_hairstyle(self):
        root = Path(__file__).resolve().parents[1]
        source = skin.blank_skin("slim")
        outer_mask = skin.uv_masks("slim")[1]
        # 不同位置、不同颜色的原外层，包含刻意遮眼的头发。
        for x, y in outer_mask:
            if (x + y) % 3 == 0:
                source.putpixel((x, y), (80 + x, 100 + y, 170, 255))
        for xy in ((11, 11), (12, 11)):
            source.putpixel(xy, (70, 80, 160, 255))
        for letter in "ABC":
            template = skin.load_json(root / f"assets/templates/eye_{letter}/template.json")
            result = skin.compose_template(source, template, "slim", purpose="review")
            self.assertTrue(all(result.getpixel(xy) == source.getpixel(xy) for xy in outer_mask), letter)
            self.assertFalse(any(p["role"].startswith("hair") for p in template["palette"].values()), letter)
            for xy in ((11, 11), (12, 11)):
                self.assertEqual(result.getpixel(xy), source.getpixel(xy), letter)

    def test_compose_cli_keeps_reference_occlusion_with_explicit_local_exception(self):
        template = sample_template()
        template["surfaces"][0]["outer"] = ["........"] * 8
        source = skin.blank_skin("slim")
        source.putpixel((42, 13), (40, 50, 60, 128))
        exception = [{"face": "head.front", "xy": [2, 5], "reason": "当前角色参考图明确遮眼",
                      "authorization": "测试用已选角色参考图"}]
        allowed = [{"face": "head.front", "xy": [2, 5], "values": [128]}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skin.write_png(root / "source.png", source)
            skin.write_json(root / "template.json", template)
            skin.write_json(root / "exceptions.json", exception)
            skin.write_json(root / "alpha.json", allowed)
            output = root / "candidate.png"
            command = [sys.executable, str(SCRIPT), "compose", "--source", str(root / "source.png"),
                       "--model", "slim", "--template", str(root / "template.json"), "--purpose", "review",
                       "--output", str(output)]
            failed = subprocess.run(command, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(output.exists())
            passed = subprocess.run(command + ["--exceptions", str(root / "exceptions.json"),
                                              "--allowed-alpha", str(root / "alpha.json")], capture_output=True)
            self.assertEqual(passed.returncode, 0, passed.stderr.decode("utf-8", errors="replace"))
            result = Image.open(output).convert("RGBA")
            self.assertEqual(skin.changed_pixels(source, result), [[10, 13]])
            manifest = skin.load_json(output.with_suffix(".manifest.json"))
            self.assertEqual(manifest["exceptions"], exception)
            self.assertEqual(manifest["allowed_alpha"], allowed)
            self.assertEqual(skin.file_hash(root / "source.png"), manifest["source_sha256"])
        with self.assertRaisesRegex(ValueError, "授权记录"):
            skin.validate_skin(source, "slim", exceptions=[{"face": "head.front", "xy": [2, 5], "reason": "遮眼"}])
        with self.assertRaisesRegex(ValueError, "基础层冲突"):
            skin.validate_skin(source, "slim", exceptions=[{**exception[0], "layer": "base"}])

    def test_reference_project_cannot_reuse_guide_hairstyle_overlay(self):
        spec = importlib.util.spec_from_file_location("render_review", SCRIPT.with_name("render_review.py"))
        review = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skin.write_json(root / "project.json", {"source": "unused.png", "cards": [
                {"example_overlays": ["assets/fixtures/guide-bc-hair.json"]}]})
            with self.assertRaisesRegex(ValueError, "角色 source 项目"):
                review.make_review(root / "project.json", root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
