"""Minecraft 原生像素母版：提取、组合、检查。仅依赖 Python 3.10+ 和 Pillow。"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image

SCHEMA_VERSION = 1


def uv_faces(model: str) -> dict:
    """坐标按 PNG 从左上至右下；left/right 均指角色自身。"""
    if model not in ("slim", "classic"):
        raise ValueError(f"未知模型：{model}")
    arm_width = 3 if model == "slim" else 4
    # name, unfolded origin, width, depth, height, outer offset
    parts = [
        ("head", 0, 0, 8, 8, 8, 32, 0),
        ("body", 16, 16, 8, 4, 12, 0, 16),
        ("rightArm", 40, 16, arm_width, 4, 12, 0, 16),
        ("leftArm", 32, 48, arm_width, 4, 12, 16, 0),
        ("rightLeg", 0, 16, 4, 4, 12, 0, 16),
        ("leftLeg", 16, 48, 4, 4, 12, -16, 0),
    ]
    result = {}
    for name, x, y, w, d, h, dx, dy in parts:
        boxes = {
            "top": [x + d, y, w, d], "bottom": [x + d + w, y, w, d],
            "right": [x, y + d, d, h], "front": [x + d, y + d, w, h],
            "left": [x + d + w, y + d, d, h], "back": [x + 2*d + w, y + d, w, h],
        }
        for side, box in boxes.items():
            bx, by, bw, bh = box
            result[f"{name}.{side}"] = {"base": box, "outer": [bx + dx, by + dy, bw, bh]}
    return result


def rectangle_pixels(box):
    x, y, w, h = box
    return {(x + u, y + v) for v in range(h) for u in range(w)}


def uv_masks(model):
    faces = uv_faces(model)
    return tuple(set().union(*(rectangle_pixels(f[layer]) for f in faces.values()))
                 for layer in ("base", "outer"))


def blank_skin(model, color=(255, 239, 229, 255)):
    rgba(color)
    if color[3] != 255:
        raise ValueError("完整皮肤的基础填充必须不透明")
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for xy in uv_masks(model)[0]:
        image.putpixel(xy, tuple(color))
    return image


def rgba(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(
        type(x) is not int or not 0 <= x <= 255 for x in value
    ):
        raise ValueError(f"无效 RGBA：{value!r}")
    return tuple(value)


def normalized_rows(rows, width, height):
    if not isinstance(rows, list) or len(rows) != height:
        raise ValueError(f"像素矩阵应有 {height} 行")
    result = []
    for row in rows:
        if not isinstance(row, (str, list)) or len(row) != width:
            raise ValueError(f"像素矩阵每行应有 {width} 格")
        if any(not isinstance(cell, str) for cell in row):
            raise ValueError("每格必须是调色板键、KEEP(.) 或 CLEAR(-)")
        result.append(list(row))
    return result


def global_xy(item, model, default_layer="outer"):
    faces = uv_faces(model)
    layer = item.get("layer", default_layer)
    if item.get("face") not in faces or layer not in ("base", "outer"):
        raise ValueError("区域标记包含未知面或层")
    x, y, width, height = faces[item["face"]][layer]
    local = item.get("xy")
    if (not isinstance(local, (list, tuple)) or len(local) != 2
            or any(type(q) is not int for q in local)
            or not 0 <= local[0] < width or not 0 <= local[1] < height):
        raise ValueError(f"区域坐标超出该面：{item}")
    return x + local[0], y + local[1]


def validate_template(template, model):
    if template.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("不支持的模板 schema_version")
    if model not in template.get("models", []):
        raise ValueError(f"模板不支持模型 {model}")
    for field in ("id", "version"):
        if not isinstance(template.get(field), str) or not template[field].strip():
            raise ValueError(f"模板缺少 {field}")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", template["id"]):
        raise ValueError("模板 id 只能包含字母、数字、下划线和连字符")
    if template.get("approval", {}).get("status") not in ("pending", "approved", "reference_only"):
        raise ValueError("模板缺少有效审核状态")
    if template.get("provenance", {}).get("kind") not in ("exact_png", "reconstructed_from_guide", "authored"):
        raise ValueError("模板缺少有效来源类型")
    palette = template.get("palette")
    if not isinstance(palette, dict) or not palette:
        raise ValueError("模板缺少调色板")
    for key, item in palette.items():
        if not isinstance(key, str) or not key or key in (".", "-"):
            raise ValueError("调色板键不能使用 KEEP/CLEAR 保留符号")
        rgba(item.get("rgba"))
        if not item.get("role"):
            raise ValueError(f"调色板 {key} 缺少颜色用途")
    bindings = template.get("required_palette_bindings", [])
    if not isinstance(bindings, list) or any(key not in palette for key in bindings):
        raise ValueError("模板必需配色绑定必须指向有效调色板键")
    faces = uv_faces(model)
    surfaces = template.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError("模板至少要声明一个面")
    occupied = set()
    for surface in surfaces:
        face = surface.get("face")
        if face not in faces or face in occupied:
            raise ValueError(f"面名称重复或不存在：{face}")
        occupied.add(face)
        for layer in ("base", "outer"):
            _, _, w, h = faces[face][layer]
            for row in normalized_rows(surface.get(layer), w, h):
                for token in row:
                    if token not in (".", "-") and token not in palette:
                        raise ValueError(f"未知调色板键：{token}")
                    if layer == "base" and (token == "-" or
                            (token in palette and palette[token]["rgba"][3] != 255)):
                        raise ValueError("模板不能清空基础层或写入半透明基础像素")
    for item in template.get("protected_visible", []):
        global_xy(item, model)
        if item.get("layer", "outer") != "outer":
            raise ValueError("可见保护区指向对应外层")
    alpha_rules(template.get("allowed_alpha", []), model)
    return True


def palette_values(template, overrides=None):
    result = {key: rgba(value["rgba"]) for key, value in template["palette"].items()}
    for key, value in (overrides or {}).items():
        if key not in result:
            raise ValueError(f"未知调色板覆盖键：{key}")
        updated = rgba(value)
        if updated[3] != result[key][3]:
            raise ValueError("换色不能改变模板 Alpha；请建立显式透明度变体")
        result[key] = updated
    return result


def compose_template(source, template, model, overrides=None, purpose="production"):
    validate_template(template, model)
    if purpose not in ("production", "review"):
        raise ValueError("purpose 只能是 production 或 review")
    if purpose == "production" and template["approval"]["status"] != "approved":
        raise ValueError("模板尚未确认，只能使用 --purpose review 生成候选")
    if source.size != (64, 64):
        raise ValueError("源皮肤必须为 64×64")
    missing = set(template.get("required_palette_bindings", [])) - set(overrides or {})
    if missing:
        raise ValueError("必须显式绑定当前角色的调色板颜色：" + ", ".join(sorted(missing)))
    colors = palette_values(template, overrides)
    result = source.convert("RGBA").copy()
    faces = uv_faces(model)
    for surface in template["surfaces"]:
        for layer in ("base", "outer"):
            x, y, w, h = faces[surface["face"]][layer]
            for v, row in enumerate(normalized_rows(surface[layer], w, h)):
                for u, token in enumerate(row):
                    if token != ".":
                        result.putpixel((x + u, y + v), (0, 0, 0, 0) if token == "-" else colors[token])
    return result


def alpha_rules(items, model):
    result = {}
    for item in items:
        if item.get("layer", "outer") != "outer":
            raise ValueError("中间 Alpha 只能在显式外层区域声明")
        values = item.get("values")
        if not isinstance(values, list) or not values or any(type(a) is not int or not 0 < a < 255 for a in values):
            raise ValueError("允许的中间 Alpha 值必须在 1–254 范围")
        result.setdefault(global_xy(item, model), set()).update(values)
    return result


def validate_skin(image, model, templates=None, overrides=None, allowed_alpha=None, exceptions=None):
    errors = []
    if image.size != (64, 64):
        return {"passed": False, "errors": [{"code": "size", "actual": list(image.size)}]}
    image = image.convert("RGBA")
    base, outer = uv_masks(model)
    used = base | outer
    templates = templates or []
    declared = list(allowed_alpha or [])
    for template in templates:
        validate_template(template, model)
        declared.extend(template.get("allowed_alpha", []))
    permitted = alpha_rules(declared, model)
    exemptions = set()
    for item in exceptions or []:
        if not item.get("reason") or not item.get("authorization"):
            raise ValueError("遮挡例外必须有具体理由和用户授权记录")
        if item.get("layer", "outer") != "outer":
            raise ValueError("遮挡例外必须指向外层；基础层冲突应建立角色变体")
        exemptions.add(global_xy(item, model))
    for y in range(64):
        for x in range(64):
            xy = (x, y)
            color = image.getpixel(xy)
            alpha = color[3]
            code = None
            if xy in base and alpha != 255:
                code = "base_alpha"
            elif xy not in used and alpha != 0:
                code = "unused_uv"
            elif xy in outer and alpha not in (0, 255) and alpha not in permitted.get(xy, set()):
                code = "undeclared_alpha"
            if code:
                errors.append({"code": code, "xy": [x, y], "rgba": list(color)})
    faces = uv_faces(model)
    for template in templates:
        colors = palette_values(template, (overrides or {}).get(template["id"], {}))
        for surface in template["surfaces"]:
            for layer in ("base", "outer"):
                x, y, w, h = faces[surface["face"]][layer]
                for v, row in enumerate(normalized_rows(surface[layer], w, h)):
                    for u, token in enumerate(row):
                        # CLEAR 是组合时清理旧部件；后续刘海可覆盖非保护区。
                        if token in (".", "-"):
                            continue
                        xy = (x + u, y + v)
                        if layer == "outer" and xy in exemptions:
                            continue
                        if image.getpixel(xy) != colors[token]:
                            errors.append({"code": "template_pixel_changed", "template": template["id"],
                                           "layer": layer, "xy": list(xy), "expected": list(colors[token]),
                                           "actual": list(image.getpixel(xy))})
        for protected in template.get("protected_visible", []):
            xy = global_xy(protected, model)
            if xy not in exemptions and image.getpixel(xy)[3] != 0:
                errors.append({"code": "eye_occluded", "template": template["id"], "xy": list(xy),
                               "role": protected.get("role"), "rgba": list(image.getpixel(xy))})
    return {"passed": not errors, "model": model, "base_pixels": len(base), "outer_pixels": len(outer),
            "errors": errors, "game_runtime_verified": False}


def changed_pixels(before, after):
    if before.size != after.size:
        raise ValueError("差异比较要求尺寸一致")
    a, b = before.convert("RGBA"), after.convert("RGBA")
    return [[x, y] for y in range(a.height) for x in range(a.width) if a.getpixel((x, y)) != b.getpixel((x, y))]


def extract_template(image, face, model, template_id, provenance):
    image = image.convert("RGBA")
    if image.size != (64, 64):
        raise ValueError("精确提取要求 64×64 原始皮肤")
    faces = uv_faces(model)
    if face not in faces:
        raise ValueError("不存在的提取面")
    palette, tokens, surface, permitted = {}, {}, {"face": face}, []
    for layer in ("base", "outer"):
        x, y, width, height = faces[face][layer]
        rows = []
        for v in range(height):
            row = []
            for u in range(width):
                value = image.getpixel((x + u, y + v))
                if layer == "outer" and value[3] == 0:
                    row.append("-")
                    continue
                if value not in tokens:
                    key = f"p{len(tokens):03d}"
                    tokens[value] = key
                    palette[key] = {"rgba": list(value), "role": "unclassified"}
                row.append(tokens[value])
                if 0 < value[3] < 255:
                    permitted.append({"face": face, "layer": layer, "xy": [u, v], "values": [value[3]]})
            rows.append(row)
        surface[layer] = rows
    result = {"schema_version": 1, "id": template_id, "version": "1.0.0-extracted", "models": [model],
              "approval": {"status": "reference_only"}, "provenance": provenance, "palette": palette,
              "surfaces": [surface], "protected_visible": [], "allowed_alpha": permitted}
    validate_template(result, model)
    return result


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_png(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    with path.open("xb") as stream:
        stream.write(buffer.getvalue())


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixel_hash(image):
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def validate_catalog(index_path):
    index_path = Path(index_path).resolve()
    index = load_json(index_path)
    errors, seen, counts = [], set(), {}
    for entry in index.get("entries", []):
        template_id, state = entry.get("id"), entry.get("state")
        counts[state] = counts.get(state, 0) + 1
        if template_id in seen:
            errors.append({"code": "catalog_duplicate_id", "id": template_id})
        seen.add(template_id)
        if state == "not_reconstructed":
            if entry.get("path") is not None or entry.get("version") is not None:
                errors.append({"code": "unfinished_has_version", "id": template_id})
            continue
        if state not in ("candidate", "approved") or not entry.get("path"):
            errors.append({"code": "catalog_invalid_state", "id": template_id})
            continue
        target = (index_path.parent / entry["path"]).resolve()
        if not target.is_relative_to(index_path.parent) or not target.is_file():
            errors.append({"code": "catalog_missing_template", "id": template_id})
            continue
        template = load_json(target)
        for model in template.get("models", []):
            validate_template(template, model)
        if template.get("id") != template_id:
            errors.append({"code": "catalog_id_mismatch", "id": template_id})
        if template.get("version") != entry.get("version"):
            errors.append({"code": "catalog_version_mismatch", "id": template_id,
                           "catalog": entry.get("version"), "template": template.get("version")})
        expected_approval = "approved" if state == "approved" else "pending"
        if template.get("approval", {}).get("status") != expected_approval:
            errors.append({"code": "catalog_approval_mismatch", "id": template_id})
    if index.get("production_ready_count") != counts.get("approved", 0):
        errors.append({"code": "catalog_ready_count_mismatch"})
    return {"passed": not errors, "entries": len(seen), "counts": counts, "errors": errors}


def run_compose(args):
    source_path, output = Path(args.source).resolve(), Path(args.output).resolve()
    manifest = output.with_suffix(".manifest.json")
    if output == source_path or output.exists() or manifest.exists():
        raise FileExistsError("输出路径必须是新的候选文件，不能覆盖源文件或已有版本")
    template = load_json(args.template)
    palette = load_json(args.palette) if args.palette else {}
    exceptions = load_json(args.exceptions) if args.exceptions else []
    allowed_alpha = load_json(args.allowed_alpha) if args.allowed_alpha else []
    source_hash = file_hash(source_path)
    source = Image.open(source_path).convert("RGBA")
    result = compose_template(source, template, args.model, palette, args.purpose)
    validation = validate_skin(result, args.model, [template], {template["id"]: palette},
                               allowed_alpha, exceptions)
    if not validation["passed"]:
        raise ValueError("候选未通过验证：" + json.dumps(validation["errors"][:10], ensure_ascii=False))
    changes = changed_pixels(source, result)
    record = {"schema_version": 1, "purpose": args.purpose, "model": args.model,
              "source": str(source_path), "source_sha256": source_hash,
              "template": str(Path(args.template).resolve()), "template_sha256": file_hash(args.template),
              "template_id": template["id"], "template_version": template["version"],
              "palette_overrides": palette, "exceptions": exceptions, "allowed_alpha": allowed_alpha,
              "pixel_sha256": pixel_hash(result),
              "changed_pixels": changes, "unchanged_pixels": 4096 - len(changes), "validation": validation}
    write_png(output, result)
    reopened = Image.open(output).convert("RGBA")
    if pixel_hash(reopened) != pixel_hash(result) or file_hash(source_path) != source_hash:
        raise RuntimeError("PNG 回读或原文件保持验证失败")
    record["output_sha256"] = file_hash(output)
    record["png_readback_verified"] = True
    write_json(manifest, record)
    print(json.dumps({"output": str(output), "manifest": str(manifest), "changed": len(changes),
                      "purpose": args.purpose}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    catalog_command = sub.add_parser("catalog", help="检查目录与模板版本/状态是否一致")
    catalog_command.add_argument("--index", required=True)
    catalog_command.add_argument("--output")
    for name in ("inspect", "compose", "validate"):
        command = sub.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--model", required=True, choices=["slim", "classic"])
        command.add_argument("--output", required=name != "validate")
        if name == "inspect":
            command.add_argument("--face", default="head.front")
            command.add_argument("--id", default="extracted_reference")
        elif name == "compose":
            command.add_argument("--template", required=True)
            command.add_argument("--palette")
            command.add_argument("--purpose", choices=["production", "review"], default="production")
            command.add_argument("--allowed-alpha")
            command.add_argument("--exceptions")
        else:
            command.add_argument("--template", action="append", default=[])
            command.add_argument("--overrides", help="以模板 ID 为键的调色板覆盖 JSON")
            command.add_argument("--allowed-alpha")
            command.add_argument("--exceptions")
    args = parser.parse_args()
    if args.command == "catalog":
        result = validate_catalog(args.index)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False))
        if not result["passed"]:
            raise SystemExit(1)
        return
    if args.command == "compose":
        run_compose(args)
        return
    image = Image.open(args.source).convert("RGBA")
    if args.command == "inspect":
        provenance = {"kind": "exact_png", "source_name": Path(args.source).name,
                      "source_sha256": file_hash(args.source), "pixel_sha256": pixel_hash(image)}
        result = extract_template(image, args.face, args.model, args.id, provenance)
        write_json(args.output, result)
        print(json.dumps({"output": args.output, "source_unchanged": file_hash(args.source) == provenance["source_sha256"]}, ensure_ascii=False))
    else:
        result = validate_skin(image, args.model, [load_json(t) for t in args.template],
                               load_json(args.overrides) if args.overrides else None,
                               load_json(args.allowed_alpha) if args.allowed_alpha else None,
                               load_json(args.exceptions) if args.exceptions else None)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False))
        if not result["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
