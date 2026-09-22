"""F11 成果目录事务与来源校验。"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile


class ExportCancelled(RuntimeError):
    pass


def check_cancelled(cancelled=None):
    if cancelled and cancelled():
        raise ExportCancelled("导出已取消。")


def file_signature(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def result_sources(result):
    regions = result.get("regions")
    if regions:
        return [source for key in ("a", "b") for source in result_sources(regions[key])]
    source = result.get("source", {})
    if "size_bytes" not in source or "mtime_ns" not in source:
        raise ValueError("结果缺少来源版本，请重新计算后导出。")
    return [{"path": result["raster_path"], "size_bytes": source["size_bytes"],
             "mtime_ns": source["mtime_ns"]}]


def validate_sources(sources):
    for expected in sources:
        actual = file_signature(expected["path"])
        if any(actual[key] != expected[key] for key in ("size_bytes", "mtime_ns")):
            raise ValueError("来源文件已变化，请重新计算或重新加载后导出。")


def result_metadata(result):
    """保存可复核参数，不在清单中重复大型样本数组。"""
    if "regions" in result:
        return {"parameters": result["parameters"], "compatibility": result["compatibility"],
                "regions": {k: result_metadata(v) for k, v in result["regions"].items()},
                "warnings": result.get("warnings", []), "completed_at": result.get("completed_at")}
    return {key: result[key] for key in ("raster_path", "source", "parameters", "completed_at", "name", "histogram_mode",
            "vertices", "vertex_distance_m", "sample_interval_m", "total_distance_m",
            "sample_count", "warnings") if key in result}


def record_processing(layer, source_path, operation, parameters):
    """记录本次会话生成成果的真实参数，不从文件名推测历史处理过程。"""
    record = {"operation": operation, "input": file_signature(source_path),
              "parameters": parameters, "created_at": datetime.now(timezone.utc).isoformat()}
    layer.setCustomProperty("etopo/export_processing", json.dumps(record, ensure_ascii=False))


def layer_processing(layer):
    record = layer.customProperty("etopo/export_processing", "")
    return json.loads(record) if record else {"note": "此图层未保留历史处理参数；本次按已有成果原样导出。"}


@contextmanager
def export_package(parent, name, kind, sources, metadata, cancelled=None):
    parent = Path(parent).resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("请选择有效的输出目录。")
    if (not name or name != name.strip() or name in (".", "..") or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(".") or
            re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I)):
        raise ValueError("成果名称含无效字符或 Windows 保留名称。")
    target = parent / name
    if target.exists():
        raise FileExistsError("同名成果已存在，请修改成果名称。")
    validate_sources(sources)
    check_cancelled(cancelled)
    staging = Path(tempfile.mkdtemp(prefix=".etp-export-", dir=parent))
    try:
        yield staging
        check_cancelled(cancelled)
        validate_sources(sources)
        files = [{"name": p.name, "size_bytes": p.stat().st_size}
                 for p in sorted(staging.iterdir()) if p.is_file()]
        if not files:
            raise ValueError("没有生成可发布的成果。")
        manifest = {"schema_version": 1, "kind": kind,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "sources": sources, "metadata": metadata, "files": files}
        with (staging / "manifest.json").open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        if target.exists():
            raise FileExistsError("同名成果已存在，请修改成果名称。")
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
