#!/usr/bin/env python3
"""
多尺度融合推理工具（所有推理入口共用）

实测结论（fire_smoke_v3.pt + 森林火灾测试图）：
- 单尺度推理必然丢类：
    imgsz=960  → fire_max=0.341 / smoke_max=0.090  （烟雾几乎漏检）
    imgsz=1280 → fire_max=0.129 / smoke_max=0.302  （火焰置信度塌陷）
  原因是不同缩放比下，感受野与下采样步长对"大范围低对比烟雾"与"小面积高亮火焰"
  的响应不同，单尺度只能偏向其中一类。
- 融合 960+1280 后 fire_max=0.341 / smoke_max=0.302，两类同时恢复。
- 浅色扩散型烟雾的绝对置信度天然偏低（0.20~0.35），需按类别放宽阈值。

因此统一走三步：多尺度候选 → 类内 NMS 去重 → 分类别阈值过滤。
"""

import cv2
import numpy as np

# 严格白名单：只允许 fire / smoke，其他类别一律丢弃
VALID_CLASSES = ("fire", "smoke")

# 类别配色 (BGR)：火焰红色、烟雾橙色（与 stream_service 保持一致）
CLASS_COLORS = {
    "fire": (48, 68, 239),
    "smoke": (11, 158, 245),
}


def raw_detect(model, image, imgsz, conf, iou, device=None,
               valid_classes=VALID_CLASSES):
    """单尺度推理，返回 [{'cls', 'conf', 'xyxy'}]"""
    results = model(
        image, conf=conf, iou=iou, imgsz=imgsz, verbose=False, device=device,
    )
    names = getattr(model, "names", {}) or {}
    out = []
    for r in results:
        boxes = getattr(r, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            cls_id = int(box.cls[0])
            cls_name = names.get(cls_id, str(cls_id))
            if cls_name not in valid_classes:
                continue
            out.append({
                "cls": cls_name,
                "conf": float(box.conf[0]),
                "xyxy": [float(v) for v in box.xyxy[0].tolist()],
            })
    return out


def iou_xyxy(a, b):
    """两个 [x1,y1,x2,y2] 框的 IOU"""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms_per_class(dets, iou_thr=0.5):
    """类内 NMS：按 conf 降序贪心保留，抑制跨尺度重复框

    必须按类别分别做，否则大范围烟雾框会吃掉内部的小火焰框
    （烟/火框天然高度重叠，类别间 NMS 会把火焰误删）。
    """
    kept = []
    for cls in VALID_CLASSES:
        group = sorted([d for d in dets if d["cls"] == cls], key=lambda d: -d["conf"])
        while group:
            best = group.pop(0)
            kept.append(best)
            group = [d for d in group
                     if iou_xyxy(best["xyxy"], d["xyxy"]) < iou_thr]
    return kept


def fuse_multiscale(model, image, scales, confidence, iou, device=None,
                    class_relax=None, valid_classes=VALID_CLASSES,
                    candidate_conf=0.05, final_threshold=True):
    """多尺度融合推理

    :param scales: 参与融合的 imgsz 列表，如 [960, 1280]
    :param confidence: 基准置信度阈值
    :param class_relax: 分类别阈值系数，如 {'smoke': 0.7} 表示烟雾阈值 = confidence*0.7
    :param candidate_conf: 送入模型的候选下限。取低值，避免融合前就把弱目标滤掉
    :param final_threshold: False 时只做 NMS 去重、不下最终阈值
                            （视频低置信候选池 / 跨帧跟踪场景需要保留弱框）
    :return: [{'cls', 'conf', 'xyxy'}]
    """
    class_relax = class_relax or {}
    scales = [int(s) for s in (scales or [])] or [960]
    candidate_conf = min(float(candidate_conf), float(confidence))

    merged = []
    for imgsz in scales:
        merged.extend(raw_detect(model, image, imgsz, candidate_conf, iou,
                                 device=device, valid_classes=valid_classes))

    fused = nms_per_class(merged, iou_thr=0.5)

    if not final_threshold:
        return fused

    out = []
    for d in fused:
        thr = float(confidence) * float(class_relax.get(d["cls"], 1.0))
        if d["conf"] >= thr:
            out.append(d)
    return out


def draw_detections(image, dets):
    """把融合结果画到图上（替代 results.plot()，融合后没有单一 results 对象）"""
    canvas = image.copy()
    for item in dets:
        x1, y1, x2, y2 = (int(v) for v in item["xyxy"])
        color = CLASS_COLORS.get(item["cls"], (200, 200, 200))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)

        label = f'{item["cls"]} {item["conf"] * 100:.1f}%'
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = y1 - 6 if y1 - th - 8 > 0 else y2 + th + 8
        cv2.rectangle(canvas, (x1, ty - th - 4), (x1 + tw + 6, ty + 4), color, -1)
        cv2.putText(canvas, label, (x1 + 3, ty - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def warmup(model, device=None, imgsz=960, rounds=2):
    """模型预热：消除 CUDA 首次推理的 cuDNN autotune 开销

    实测：冷启动单张 4861ms / 用户观测 3586ms，稳态仅 11~28ms。
    多跑几轮把这段开销前移到服务启动阶段。
    """
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    for _ in range(max(1, rounds)):
        try:
            model(dummy, imgsz=imgsz, conf=0.25, verbose=False, device=device)
        except Exception:  # noqa: BLE001
            # 预热失败不影响功能，交给调用方记录日志
            raise
    return True
