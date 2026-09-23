"""F08/F09/F10 数值表；UTF-8 BOM，单位与百分比明确。"""

import csv
import json
from .export_service import check_cancelled


def _write(folder, filename, headers, rows, cancelled):
    path = folder / filename
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            check_cancelled(cancelled)
            writer.writerow(row)
            count += 1
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader) != headers or sum(1 for row in reader if len(row) == len(headers)) != count:
            raise ValueError("CSV 重新读取验证失败。")


def _bounds(item):
    return ["-inf" if item["lower_m"] is None else item["lower_m"],
            "+inf" if item["upper_m"] is None else item["upper_m"],
            bool(item.get("lower_inclusive", item["lower_m"] is not None)),
            bool(item.get("upper_inclusive", False))]


BOUND_HEADERS = ["下界(m)", "上界(m)", "包含下界", "包含上界"]
METRICS = [("total_count", "总像元数", "个"), ("valid_count", "有效像元数", "个"),
           ("invalid_count", "无效像元数", "个"), ("min_m", "最小高程", "m"),
           ("max_m", "最大高程", "m"), ("mean_m", "平均高程", "m"),
           ("std_m", "总体标准差", "m")]


def export_csv(folder, kind, result, cancelled=None):
    write = lambda filename, headers, rows: _write(folder, filename, headers, rows, cancelled)
    regions = result.get("regions", {"statistics": result})
    features = []
    for key, region in regions.items():
        polygon = region.get("parameters", {}).get("roi")
        if polygon is not None:
            from .polygon_roi import normalize_polygon
            features.append(dict(type="Feature", geometry=normalize_polygon(polygon),
                properties=dict(region=key, raster_path=region["raster_path"],
                                inclusion="pixel_center", area="selected_whole_pixels")))
    if features:
        check_cancelled(cancelled)
        (folder / "regions.geojson").write_text(json.dumps(dict(type="FeatureCollection", features=features),
            ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if kind == "profile":
        rows = ([i + 1, d / 1000, lon, lat, None if missing else elev,
                 None if missing else depth, missing]
                for i, (d, lon, lat, elev, depth, missing) in enumerate(zip(
                    *(result[k] for k in ("distance_m", "longitude", "latitude", "elevation_m", "depth_m", "is_nodata")), strict=True)))
        write("profile.csv", ["序号", "累计距离(km)", "经度(°)", "纬度(°)", "高程(m)", "水深(m)", "是否无效"], rows)
    elif kind == "statistics":
        rows = [[label, unit, result["statistics"][key]] for key, label, unit in METRICS]
        rows += [[label, "km²", result["area"][key] / 1e6] for key, label in
                 (("footprint_m2", "多边形入选格网面积" if features else "完整格网面积"),
                  ("valid_m2", "有效面积"), ("invalid_m2", "无效面积"))]
        for item in result["sign_summary"]:
            rows.extend([[f"{item['label']} 像元数", "个", item["count"]],
                         [f"{item['label']} 面积", "km²", item["area_m2"] / 1e6]])
        write("summary.csv", ["指标", "单位", "值"], rows)
        histogram = result["histogram"]
        edges, counts = histogram["bin_edges_m"], histogram["counts"]
        write("histogram.csv", BOUND_HEADERS + ["像元数"],
              ([edges[i], edges[i + 1], True, i == len(counts) - 1, count] for i, count in enumerate(counts)))
        write("classes.csv", BOUND_HEADERS + ["像元数", "像元占比(%)", "面积(km²)", "面积占比(%)"],
              (_bounds(c) + [c["count"], c["pixel_fraction"] * 100, c["area_m2"] / 1e6, c["area_fraction"] * 100]
               for c in result["classes"]))
    elif kind == "comparison":
        a, b = (result["regions"][k] for k in ("a", "b"))
        rows = [[label, unit, a["statistics"][key], b["statistics"][key], result["differences"][key], unit]
                for key, label, unit in METRICS]
        rows.append(["有效面积", "km²", a["area"]["valid_m2"] / 1e6, b["area"]["valid_m2"] / 1e6,
                     result["differences"]["valid_area_m2"] / 1e6, "km²"])
        for key, diff, label in (("valid_coverage_fraction", "valid_coverage_pp", "有效面积覆盖率"),
                                 ("negative_fraction", "negative_pp", "负高程面积占比")):
            rows.append([label, "%", a["area"][key] * 100, b["area"][key] * 100, result["differences"][diff], "百分点"])
        write("summary.csv", ["指标", "单位", "A", "B", "B−A", "差值单位"], rows)
        edges = result["parameters"]["bin_edges_m"]
        write("distribution.csv", BOUND_HEADERS + ["A像元数", "B像元数", "A像元占比(%)", "B像元占比(%)"],
              ([edges[i], edges[i + 1], True, i == len(edges) - 2,
                a["histogram"]["counts"][i], b["histogram"]["counts"][i],
                a["histogram"]["frequencies"][i] * 100, b["histogram"]["frequencies"][i] * 100]
               for i in range(len(edges) - 1)))
        write("classes.csv", BOUND_HEADERS + ["A面积(km²)", "B面积(km²)", "A面积占比(%)", "B面积占比(%)", "B−A面积(km²)", "B−A面积占比(百分点)"],
              (_bounds(c) + [c["a"]["area_m2"] / 1e6, c["b"]["area_m2"] / 1e6,
                             c["a"]["area_fraction"] * 100, c["b"]["area_fraction"] * 100,
                             c["area_difference_m2"] / 1e6, c["area_difference_pp"]] for c in result["classes"]))
    else:
        raise ValueError("不支持的 CSV 结果类型。")
