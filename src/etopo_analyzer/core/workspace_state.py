"""工作状态 JSON 的版本校验与原子保存，不复制原始栅格。"""

import json
import os
from pathlib import Path
import tempfile
import math
from datetime import datetime


FORMAT = "etopo-workspace"
VERSION = 1


def validate_state(state):
    if not isinstance(state, dict) or state.get("format") != FORMAT or state.get("version") != VERSION:
        raise ValueError("不是支持的 ETOPO 工作状态文件，或文件版本过新。")
    if not isinstance(state.get("layers"), list) or not isinstance(state.get("history"), list):
        raise ValueError("工作状态缺少图层或成果历史。")
    ids = set()
    for layer in state["layers"]:
        if not isinstance(layer, dict) or not all(key in layer for key in ("id", "source", "name", "group", "style", "signature", "type")):
            raise ValueError("图层记录不完整。")
        if any(not isinstance(layer[key], str) for key in ("id", "source", "name", "group", "style", "type")):
            raise ValueError("图层字段类型无效。")
        signature = layer["signature"]
        if not isinstance(signature, dict) or not isinstance(signature.get("path"), str) or any(
                not isinstance(signature.get(key), int) for key in ("size_bytes", "mtime_ns")):
            raise ValueError("图层来源版本无效。")
        if layer["id"] in ids or layer["type"] not in ("raster", "vector"):
            raise ValueError("图层记录重复或类型无效。")
        if layer["group"] not in ("源数据", "裁剪结果", "派生栅格", "等值线", "辅助数据"):
            raise ValueError("图层分组无效。")
        if not isinstance(layer.get("processing", ""), str):
            raise ValueError("图层处理记录无效。")
        ids.add(layer["id"])
    view = state.get("view", {})
    bounds = view.get("extent", [])
    if len(bounds) != 4 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in bounds):
        raise ValueError("地图范围无效。")
    if not isinstance(view.get("crs"), str) or not isinstance(state.get("parameters"), dict):
        raise ValueError("地图坐标系或分析参数无效。")
    for key in ("visible", "order"):
        values = state.get(key)
        if not isinstance(values, list) or any(v not in ids for v in values) or len(values) != len(set(values)):
            raise ValueError("图层顺序或显隐记录无效。")
    if set(state["order"]) != ids:
        raise ValueError("图层顺序记录不完整。")
    references = state.get("references", {})
    if not isinstance(references, dict) or any(value is not None and value not in ids for value in references.values()):
        raise ValueError("成果图层引用无效。")
    if state.get("active") is not None and state["active"] not in ids:
        raise ValueError("分析源记录无效。")
    if state.get("active") is not None:
        active = next(layer for layer in state["layers"] if layer["id"] == state["active"])
        if active["type"] != "raster" or active["group"] not in ("源数据", "裁剪结果"):
            raise ValueError("分析源必须是原始或裁剪 DEM。")
    if not isinstance(state.get("results"), dict):
        raise ValueError("分析结果记录无效。")
    if any(key not in ("profile", "statistics", "comparison") or (value is not None and not isinstance(value, dict))
           for key, value in state["results"].items()):
        raise ValueError("分析结果类型无效。")
    rotation = view.get("rotation", 0)
    if not isinstance(rotation, (int, float)) or not math.isfinite(rotation):
        raise ValueError("地图旋转角度无效。")
    p = state["parameters"]
    roi = state.get("roi", {})
    if not isinstance(roi, dict) or not isinstance(roi.get("polygons", {}), dict) or not isinstance(roi.get("enabled", {}), dict):
        raise ValueError("多边形统计范围记录无效。")
    from .polygon_roi import normalize_polygon
    for key, polygon in roi.get("polygons", {}).items():
        if key not in ("statistics", "a", "b"):
            raise ValueError("未知的多边形区域。")
        if polygon is not None:
            normalize_polygon(polygon)
    for key, enabled in roi.get("enabled", {}).items():
        if key not in ("statistics", "comparison") or not isinstance(enabled, bool):
            raise ValueError("多边形范围启用状态无效。")
    for key in ("hillshade_azimuth_spin", "hillshade_altitude_spin", "contour_interval_spin",
                "contour_base_spin", "profile_interval_spin", "statistics_bins_spin", "comparison_bins"):
        if key in p and (not isinstance(p[key], (float, int)) or not math.isfinite(p[key])):
            raise ValueError("数值参数无效。")
    for key in ("statistics_thresholds", "comparison_thresholds"):
        if key in p and not isinstance(p[key], str):
            raise ValueError("分级阈值格式无效。")
    for key in ("statistics_bins_spin", "comparison_bins"):
        if key in p and (not isinstance(p[key], int) or not 1 <= p[key] <= 200):
            raise ValueError("统计分箱数无效。")
    for key in ("a", "b", "clip_source"):
        if p.get(key) is not None and p[key] not in ids:
            raise ValueError("参数引用了未知图层。")
    clip = p.get("clip_bounds", {})
    if not isinstance(clip, dict) or any(key not in ("west", "south", "east", "north") or
            not isinstance(value, (float, int)) or not math.isfinite(value) for key, value in clip.items()):
        raise ValueError("裁剪参数无效。")
    for entry in state["history"]:
        if (not isinstance(entry, dict) or entry.get("kind") not in ("layer", "export", "profile", "statistics", "comparison")
                or any(not isinstance(entry.get(key), str) for key in ("id", "label", "time"))
                or not isinstance(entry.get("sources"), list) or not isinstance(entry.get("files"), list)
                or not isinstance(entry.get("parameters"), dict)):
            raise ValueError("成果历史记录无效。")
        try:
            datetime.fromisoformat(entry["time"])
        except ValueError as exc:
            raise ValueError("成果历史时间无效。") from exc
        for signature in entry["sources"] + entry["files"]:
            if not isinstance(signature, dict) or not isinstance(signature.get("path"), str) or any(
                    not isinstance(signature.get(key), int) for key in ("size_bytes", "mtime_ns")):
                raise ValueError("成果历史来源记录无效。")
    return state


def read_state(path):
    with Path(path).open(encoding="utf-8") as stream:
        return validate_state(json.load(stream))


def write_state(path, state):
    validate_state(state)
    path = Path(path).resolve()
    if not path.name.endswith(".etopo.json"):
        raise ValueError("工作状态文件须使用 .etopo.json 扩展名。")
    # 先完成序列化，失败时不触碰原文件。
    data = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)
    descriptor, temporary = tempfile.mkstemp(prefix=".etopo-state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
