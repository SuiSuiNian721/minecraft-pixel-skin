"""从模板数据生成可复现的候选 PNG、逐格分层图和本地立体审阅页。"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from skin_tools import (blank_skin, changed_pixels, compose_template, file_hash, load_json,
                        pixel_hash, validate_skin, uv_faces, write_json, write_png)

ROOT = Path(__file__).resolve().parents[1]


def font(size, bold=False):
    candidates = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + [
        r"C:\Windows\Fonts\msyh.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def crop_face(image, model, face, layer):
    x, y, w, h = uv_faces(model)[face][layer]
    return image.crop((x, y, x + w, y + h))


def draw_board(rows, title, subtitle, output):
    """每行展示一个面的基础、外层、同坐标叠加；不模拟外层体积。"""
    width, row_height = 1200, 460
    board = Image.new("RGB", (width, 160 + row_height * len(rows)), "#eff4fa")
    draw = ImageDraw.Draw(board)
    draw.text((36, 25), title, font=font(32, True), fill="#304b69")
    draw.text((36, 79), subtitle, font=font(17), fill="#657990")
    for row_index, row in enumerate(rows):
        top = 132 + row_index * row_height
        draw.text((36, top), row["label"], font=font(23, True), fill="#3d617d")
        base = crop_face(row["image"], row["model"], row["face"], "base")
        outer = crop_face(row["image"], row["model"], row["face"], "outer")
        combined = Image.alpha_composite(base, outer)
        for column, (name, tile) in enumerate(zip(["基础层", "外层 · 棋盘为透明", "同坐标叠加"], [base, outer, combined])):
            left = 26 + column * 390
            draw.rounded_rectangle((left, top + 39, left + 368, top + 424), radius=18, fill="white")
            draw.text((left + 24, top + 51), name, font=font(19, True), fill="#466380")
            cell = min(40, 320 // max(tile.width, tile.height))
            gx, gy = left + 30, top + 93
            for x in range(tile.width):
                draw.text((gx + x*cell + cell//2 - 4, gy - 17), str(x), font=font(11), fill="#8b99ab")
            for y in range(tile.height):
                draw.text((gx - 17, gy + y*cell + cell//2 - 7), str(y), font=font(11), fill="#8b99ab")
                for x in range(tile.width):
                    check = (245, 247, 251, 255) if (x+y) % 2 == 0 else (225, 231, 240, 255)
                    color = tile.getpixel((x, y))
                    displayed = tuple(round(color[k]*color[3]/255 + check[k]*(1-color[3]/255)) for k in range(3))
                    box = (gx+x*cell, gy+y*cell, gx+(x+1)*cell, gy+(y+1)*cell)
                    draw.rectangle(box, fill=displayed, outline="#becddb", width=1)
        draw.text((36, top + 434), row.get("note", "局部坐标从左上角 (0,0) 开始。"), font=font(14), fill="#6e8399")
    write_png(output, board)


def make_review(project_path, output_dir):
    project_path, output = Path(project_path).resolve(), Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError("审阅输出目录已存在；请使用新的版本目录")
    project = load_json(project_path)
    has_source, has_fixture = "source" in project, "fixture" in project
    if has_source == has_fixture:
        raise ValueError("审阅项目必须且只能指定 source 或 fixture")
    if has_source and any("example_overlays" in card for card in project["cards"]):
        raise ValueError("角色 source 项目不能使用指南 example_overlays；发型应依据该角色参考图制作")
    model = project["model"]
    source_record = None
    fixture_colors_by_role = {}
    if "source" in project:
        source_path = Path(project["source"])
        if not source_path.is_absolute():
            source_path = project_path.parent / source_path
        source_record = {"path": str(source_path.resolve()), "sha256": file_hash(source_path)}
        common = Image.open(source_path).convert("RGBA")
    else:
        fixture_path = ROOT / project["fixture"]
        fixture = load_json(fixture_path)
        fixture_colors_by_role = {value["role"]: value["rgba"] for value in fixture["palette"].values()}
        common = compose_template(blank_skin(model, (185, 199, 210, 255)), fixture, model, purpose="review")
    if common.size != (64, 64):
        raise ValueError("审阅源图必须为 64×64")
    for variant in project["palettes"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", variant["id"]):
            raise ValueError("配色 id 必须是安全的文件名片段")
    # 先读取全部输入，避免开始写出后才发现缺失文件。
    templates = []
    for card in project["cards"]:
        template_path = ROOT / card["template"]
        overlay_paths = card.get("example_overlays", [])
        if not isinstance(overlay_paths, list) or any(not isinstance(p, str) for p in overlay_paths):
            raise ValueError("example_overlays 必须是示例夹具路径字符串数组")
        overlays = []
        for overlay_path in overlay_paths:
            path = (ROOT / overlay_path).resolve()
            if not path.is_relative_to(ROOT / "assets" / "fixtures"):
                raise ValueError("指南示例叠层必须位于 assets/fixtures")
            overlay = load_json(path)
            if overlay.get("approval", {}).get("status") != "reference_only":
                raise ValueError("指南示例叠层必须标为 reference_only")
            overlays.append((path, overlay))
        templates.append((card, template_path, load_json(template_path), overlays))
    output.mkdir(parents=True)
    write_png(output / "common-fixture.png", common)
    metadata = {"title": project["title"], "subtitle": project["subtitle"], "model": model,
                "focus": project.get("focus", "head"), "palettes": project["palettes"], "cards": []}
    overall = []
    checks = {"fixture_pixel_sha256": pixel_hash(common), "source": source_record,
              "cards": [], "game_runtime_verified": False}
    for card, template_path, template, overlays in templates:
        card_source = common.copy()
        overlay_records = []
        for path, overlay in overlays:
            card_source = compose_template(card_source, overlay, model, purpose="review")
            overlay_records.append({"path": str(path), "id": overlay["id"],
                                    "version": overlay["version"], "sha256": file_hash(path)})
        item = {"id": template["id"], "label": card["label"], "detail": card["detail"],
                "version": template["version"], "approval": template["approval"]["status"],
                "skins": {}, "skin_files": {}, "matrices": template["surfaces"],
                "decisions": template.get("reconstruction_decisions", []), "palette": template["palette"],
                "protected_visible": template.get("protected_visible", []),
                "example_overlays": overlay_records}
        first_image = None
        for variant in project["palettes"]:
            overrides = {key: fixture_colors_by_role[template["palette"][key]["role"]]
                         for key in template.get("required_palette_bindings", [])
                         if template["palette"][key]["role"] in fixture_colors_by_role}
            overrides.update(variant["overrides"])
            image = compose_template(card_source, template, model, overrides, "review")
            result = validate_skin(image, model, [template], {template["id"]: overrides},
                                   project.get("allowed_alpha"), project.get("exceptions"))
            if not result["passed"]:
                raise ValueError(json.dumps(result, ensure_ascii=False))
            filename = f"{template['id']}_{variant['id']}_64x64.png"
            target = output / filename
            write_png(target, image)
            reread = Image.open(target).convert("RGBA")
            if reread.tobytes() != image.tobytes():
                raise RuntimeError("候选 PNG 回读不一致")
            item["skins"][variant["id"]] = data_url(target)
            item["skin_files"][variant["id"]] = filename
            changes = changed_pixels(common, image)
            record = {"template_id": template["id"], "template_version": template["version"],
                      "template_sha256": file_hash(template_path), "purpose": "review", "model": model,
                      "palette": variant["id"], "palette_overrides": overrides,
                      "pixel_sha256": pixel_hash(image), "changed_pixels": changes,
                      "source": source_record, "example_overlays": overlay_records,
                      "exceptions": project.get("exceptions", []),
                      "allowed_alpha": project.get("allowed_alpha", []),
                      "png_readback_verified": True, "validation": result}
            write_json(target.with_suffix(".manifest.json"), record)
            checks["cards"].append(record)
            if first_image is None:
                first_image = image
        layers = []
        for surface in template["surfaces"]:
            layers.append({"label": f"{card['label']} · {surface['face']}", "image": first_image,
                           "model": model, "face": surface["face"],
                           "note": "眼型外层为 KEEP；图中头发来自参考头模" +
                           ("与指南示例叠层，不能直接套给角色。" if overlays else "，角色发型以自身参考图为准。")})
        chart = output / f"{template['id']}_layers.png"
        draw_board(layers, card["label"] + " · 像素分层", "重建候选，尚待确认；每个大方格对应 PNG 的一个像素。", chart)
        item["layer_chart"] = data_url(chart)
        item["layer_chart_file"] = chart.name
        overall.append(layers[0])
        metadata["cards"].append(item)
    board = output / "像素分层总览.png"
    draw_board(overall, project["title"] + " · 逐格分层", "眼型与发型独立 · 基础层 / 外层 / 叠加 · 发型以当前角色参考图为准", board)
    metadata["overview"] = data_url(board)
    metadata["guide"] = data_url(ROOT / "assets/sources/guide-eyes.png")
    source = ROOT / "assets/sources/reference_xiaoli.png"
    reference = Image.open(source).convert("RGBA")
    extracted = load_json(ROOT / "assets/templates/reference_xiaoli_front/template.json")
    rebuilt = compose_template(blank_skin("slim"), extracted, "slim", purpose="review")
    equal = all(crop_face(reference, "slim", "head.front", layer).tobytes() ==
                crop_face(rebuilt, "slim", "head.front", layer).tobytes() for layer in ("base", "outer"))
    if not equal:
        raise RuntimeError("小璃原始分层精确回放失败")
    reference_chart = output / "小璃_精确分层验证.png"
    draw_board([{"label": "林小璃 · 原始 PNG 精确提取", "image": reference, "model": "slim", "face": "head.front",
                 "note": "基础层全图起点 (8,8)，外层起点 (40,8)；不是两种角色眼睛的通用保护区。"}],
               "小璃原图 · 分层验证", "原图像素 → 模板矩阵 → 分层回放：基础层与外层均逐格一致。", reference_chart)
    metadata["reference_chart"] = data_url(reference_chart)
    if source_record and file_hash(source_record["path"]) != source_record["sha256"]:
        raise RuntimeError("审阅源文件哈希发生变化")
    checks["reference_exact_roundtrip"] = equal
    checks["reference_sha256"] = file_hash(source)
    checks["guide_sha256"] = file_hash(ROOT / "assets/sources/guide.png")
    # 检查两种角色眼睛换瞳色时实际改变的像素。
    for item in metadata["cards"]:
        colors = list(item["skin_files"])
        if len(colors) >= 2:
            a = Image.open(output / item["skin_files"][colors[0]])
            b = Image.open(output / item["skin_files"][colors[1]])
            item["palette_changed_pixels"] = changed_pixels(a, b)
    page = (ROOT / "assets/review-template.html").read_text(encoding="utf-8")
    data_json = json.dumps(metadata, ensure_ascii=False).replace("<", "\\u003c")
    page = page.replace("__TITLE__", html.escape(project["title"]))
    page = page.replace("__REVIEW_DATA__", data_json)
    page = page.replace("__VIEWER_CODE__", (ROOT / "assets/vendor/skinview3d.bundle.js").read_text(encoding="utf-8"))
    with (output / "眼型模板审阅.html").open("x", encoding="utf-8", newline="\n") as file:
        file.write(page)
    write_json(output / "review-data.json", metadata)
    write_json(output / "pixel-validation.json", checks)
    print(json.dumps({"output": str(output), "candidates": len(metadata["cards"]),
                      "reference_exact_roundtrip": equal, "game_runtime_verified": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    make_review(args.project, args.output)
