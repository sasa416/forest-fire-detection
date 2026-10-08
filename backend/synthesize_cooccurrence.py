#!/usr/bin/env python3
"""合成「火焰 + 烟雾共现」样本，填补数据集缺口

── 审计结论（本次诊断实测）──
    6940 张标注图：仅火 3679 (53.0%)、仅烟 2996 (43.2%)、
    火+烟共现 0 (0.0%)、空标注 265 (3.8%)
    烟雾框面积中位数仅 0.040（占画面 4%），而测试图烟雾占画面 60%+
    → 模型从未见过「火烟共存」场景，也没见过大范围烟雾，缩放尺度严重失配。
      这是"烟雾整类漏检 + 火焰置信度低"的数据层根因。

── 本脚本做法 ──
    用 copy-paste 合成（Simple Copy-Paste, Ghiasi et al., CVPR 2021）：
      1. 从「仅烟」图裁剪烟雾区域，按灰度相似度生成软 alpha 掩膜（羽化 → 扩散感）
      2. 贴到「仅火」图上，目标占画面 30%~70%（大范围）
      3. 混入浅灰底色 + 整体降 alpha（模拟浅色扩散型烟雾）
      4. 优先贴画面上半部，且不与火焰框大面积重叠（保证火仍可见）
      5. 标签 = 原火焰框 + 新粘贴的烟雾框（真值自动生成，无需人工标注）

── 输出 ──
    data/synth/{images,labels}/{train,val}，与原数据集物理隔离，不污染原始数据。
    由 data/yolo_format/fire_smoke_v4.yaml 引用。

用法：
    python synthesize_cooccurrence.py --train 1600 --val 400
"""

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC_IMG = ROOT / "data" / "yolo_format" / "images"
SRC_LBL = ROOT / "data" / "yolo_format" / "labels"
OUT = ROOT / "data" / "synth"

FIRE, SMOKE = 0, 1
# 浅灰底色，用于调出「浅色/白灰」烟雾（BGR）
LIGHT_GRAY = np.array([208.0, 213.0, 218.0], dtype=np.float32)


# ───────────────────────── I/O（兼容 Windows 中文路径） ─────────────────────────

def imread_u(path):
    """cv2.imread 在 Windows 下读不了含中文的绝对路径，改用 imdecode"""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def imwrite_u(path, img, quality=92):
    ext = Path(path).suffix or ".jpg"
    ok, buf = cv2.imencode(ext, img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return False
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))
    return True


def read_label(p):
    """读 YOLO 标签 -> [(cls, [cx,cy,w,h])]"""
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            out.append((int(float(parts[0])), [float(v) for v in parts[1:5]]))
        except ValueError:
            continue
    return out


def xywh2xyxy(b, W, H):
    cx, cy, w, h = b
    return [(cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H]


def xyxy2xywh(b, W, H):
    x1, y1, x2, y2 = b
    return [(x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H]


def box_area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter_area(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


# ───────────────────────── 数据集扫描 ─────────────────────────

def scan_split(split):
    """按类别组合归类某个 split 的样本"""
    img_dir, lbl_dir = SRC_IMG / split, SRC_LBL / split
    fire_only, smoke_only, both, empty = [], [], [], []
    combos = {"fire": 0, "smoke": 0, "both": 0, "empty": 0}

    for img_path in sorted(img_dir.glob("*")):
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            continue
        items = read_label(lbl_dir / f"{img_path.stem}.txt")
        cls_set = {c for c, _ in items}
        has_f, has_s = FIRE in cls_set, SMOKE in cls_set
        if has_f and has_s:
            both.append(img_path)
            combos["both"] += 1
        elif has_f:
            fire_only.append(img_path)
            combos["fire"] += 1
        elif has_s:
            smoke_only.append(img_path)
            combos["smoke"] += 1
        else:
            empty.append(img_path)
            combos["empty"] += 1
    return fire_only, smoke_only, both, empty, combos


# ───────────────────────── 掩膜与烟雾提取 ─────────────────────────

def soft_ellipse_mask(h, w):
    """椭圆羽化掩膜：中心 1，边缘平滑降到 0（烟团自然边界）"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    ry, rx = max(h / 2.0, 1e-3), max(w / 2.0, 1e-3)
    d = np.sqrt(((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2)
    return np.clip((1.0 - d) / 0.40, 0.0, 1.0).astype(np.float32)


def gray_likelihood(bgr):
    """低饱和 + 中高亮度 → 更像烟；模糊后作为软权重"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[..., 1].astype(np.float32) / 255.0
    val = hsv[..., 2].astype(np.float32) / 255.0
    g = (1.0 - sat) * np.clip(val * 1.5, 0.0, 1.0)
    g = cv2.GaussianBlur(g, (0, 0), 3)
    return np.clip(g, 0.0, 1.0)


def forest_score(bgr):
    """绿色植被像素占比，用于优先挑森林底图（原数据集混杂工业/城市场景）"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = hsv[..., 0]
    s = hsv[..., 1].astype(np.float32)
    v = hsv[..., 2].astype(np.float32)
    green = ((h >= 32) & (h <= 90) & (s > 40) & (v > 30))
    return float(green.mean())


def extract_smoke_patch(img, items):
    """裁剪最大的烟雾区域，返回 (patch_bgr, alpha)

    alpha = 椭圆羽化 × 归一化灰度相似度：
      - 椭圆羽化保证边缘自然消散，不出现方块硬边
      - 灰度权重**不做下限保底**，只把"像烟"的像素合成过去，
        否则源图的工业/建筑背景会一起渗进来，贴出来是一层灰白幕布
    """
    smokes = [xywh2xyxy(b, img.shape[1], img.shape[0])
              for c, b in items if c == SMOKE]
    if not smokes:
        return None, None
    smokes.sort(key=box_area, reverse=True)
    H, W = img.shape[:2]
    x1, y1, x2, y2 = smokes[0]
    # 略微外扩，保留烟的边缘
    bw, bh = x2 - x1, y2 - y1
    x1 = int(max(0, x1 - 0.10 * bw))
    y1 = int(max(0, y1 - 0.10 * bh))
    x2 = int(min(W, x2 + 0.10 * bw))
    y2 = int(min(H, y2 + 0.10 * bh))
    if x2 - x1 < 16 or y2 - y1 < 16:
        return None, None

    patch = img[y1:y2, x1:x2].copy()
    ph, pw = patch.shape[:2]

    g = gray_likelihood(patch)
    # 按 95 分位归一化，让烟雾主体达到接近 1 的合成强度
    g = np.clip(g / (float(np.percentile(g, 95)) + 1e-6), 0.0, 1.0)
    alpha = soft_ellipse_mask(ph, pw) * g
    return patch, alpha


def lighten(patch, strength):
    """向浅灰偏移，得到浅色扩散型烟雾"""
    return cv2.addWeighted(patch, 1.0 - strength,
                           np.full_like(patch, LIGHT_GRAY), strength, 0)


# ───────────────────────── 合成主逻辑 ─────────────────────────

def paste_one_patch(canvas, patch, alpha, target_ratio, light_strength,
                    global_alpha, prefer_top, fire_boxes, rng):
    """把烟雾贴到画布上；返回烟雾框或 None（放不下时）"""
    H, W = canvas.shape[:2]
    ph, pw = patch.shape[:2]
    if ph < 8 or pw < 8:
        return None

    # 按目标面积比反推缩放尺寸（保持长宽比，并做 ±25% 抖动）
    target_area = target_ratio * W * H
    scale = np.sqrt(target_area / float(pw * ph)) * rng.uniform(0.75, 1.25)
    nw, nh = int(pw * scale), int(ph * scale)
    nw, nh = max(8, min(nw, int(W * 1.4))), max(8, min(nh, int(H * 1.4)))

    rpatch = cv2.resize(patch, (nw, nh), interpolation=cv2.INTER_LINEAR)
    rpatch = lighten(rpatch, light_strength)
    ralpha = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_LINEAR) * global_alpha

    if rng.random() < 0.5:
        rpatch = rpatch[:, ::-1].copy()
        ralpha = ralpha[:, ::-1].copy()

    # 允许部分出画（更自然），但中心必须落在画面内
    for _ in range(12):
        x = int(rng.uniform(-0.15 * nw, W - 0.85 * nw))
        if prefer_top:
            y = int(rng.uniform(-0.15 * nh, max(1.0, H * 0.62 - nh)))
        else:
            y = int(rng.uniform(-0.15 * nh, H - 0.85 * nh))

        bx1, by1 = max(0, x), max(0, y)
        bx2, by2 = min(W, x + nw), min(H, y + nh)
        if bx2 - bx1 < 12 or by2 - by1 < 12:
            continue
        box = [bx1, by1, bx2, by2]

        # 与火焰框重叠不能太大，必须让火焰保持可见
        a_box = box_area(box)
        worst = 0.0
        for fb in fire_boxes:
            fa = box_area(fb)
            if fa <= 0:
                continue
            worst = max(worst, inter_area(box, fb) / fa)
        if worst > 0.45:
            continue

        # ── alpha 混合 ──
        sx1, sy1 = bx1 - x, by1 - y
        sub_p = rpatch[sy1:sy1 + (by2 - by1), sx1:sx1 + (bx2 - bx1)].astype(np.float32)
        sub_a = ralpha[sy1:sy1 + (by2 - by1), sx1:sx1 + (bx2 - bx1)]
        sub_a = cv2.GaussianBlur(np.clip(sub_a, 0.0, 1.0), (0, 0), 2)[..., None]
        roi = canvas[by1:by2, bx1:bx2].astype(np.float32)
        canvas[by1:by2, bx1:bx2] = np.clip(
            roi * (1.0 - sub_a) + sub_p * sub_a, 0, 255
        ).astype(np.uint8)
        return box
    return None


def synthesize(fire_list, smoke_sources, n_target, out_split, rng, sanity=None):
    """生成 n_target 张共现样本

    :param smoke_sources: 已缓存的烟雾模板 [(patch, alpha)]（按面积降序）
    :param sanity: (min_ratio, max_ratio) 只保留烟雾占比落在区间内的结果
    """
    if not fire_list or not smoke_sources:
        return {"generated": 0, "skipped": 0, "ratios": []}

    img_out = OUT / "images" / out_split
    lbl_out = OUT / "labels" / out_split
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    stats = {"generated": 0, "skipped": 0, "ratios": []}
    idx = 0
    attempts = 0
    max_attempts = n_target * 12

    while stats["generated"] < n_target and attempts < max_attempts:
        attempts += 1
        src = fire_list[idx % len(fire_list)]
        idx += 1

        img = imread_u(src)
        if img is None:
            stats["skipped"] += 1
            continue
        items = read_label(SRC_LBL / out_split / f"{src.stem}.txt")
        fire_items = [(c, b) for c, b in items if c == FIRE]
        if not fire_items:
            stats["skipped"] += 1
            continue

        H, W = img.shape[:2]
        canvas = img.copy()
        fire_boxes = [xywh2xyxy(b, W, H) for _, b in fire_items]

        # 主烟团：大范围（30%~70% 画面）
        patch, alpha = smoke_sources[rng.randrange(len(smoke_sources))]
        main_box = paste_one_patch(
            canvas, patch, alpha,
            target_ratio=rng.uniform(0.30, 0.70),
            light_strength=rng.uniform(0.10, 0.35),
            global_alpha=rng.uniform(0.70, 1.00),
            prefer_top=True,
            fire_boxes=fire_boxes,
            rng=rng,
        )
        if main_box is None:
            stats["skipped"] += 1
            continue

        new_boxes = [main_box]

        # 次烟团：30% 概率再加一小团，更接近真实火场
        if rng.random() < 0.30:
            patch2, alpha2 = smoke_sources[rng.randrange(len(smoke_sources))]
            sec = paste_one_patch(
                canvas, patch2, alpha2,
                target_ratio=rng.uniform(0.08, 0.25),
                light_strength=rng.uniform(0.10, 0.35),
                global_alpha=rng.uniform(0.60, 0.95),
                prefer_top=rng.random() < 0.7,
                fire_boxes=fire_boxes + new_boxes,
                rng=rng,
            )
            if sec is not None:
                new_boxes.append(sec)

        # 轻微整体扰动，避免合成痕迹过于一致
        if rng.random() < 0.5:
            beta = rng.uniform(-12, 12)
            canvas = cv2.convertScaleAbs(canvas, alpha=1.0, beta=beta)
        if rng.random() < 0.3:
            canvas = cv2.GaussianBlur(canvas, (3, 3), 0)

        # ── 写标签：原火焰框 + 新烟雾框 ──
        lines = []
        for c, b in fire_items:
            lines.append(f"{c} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}")
        ratios = []
        for nb in new_boxes:
            cx, cy, bw, bh = xyxy2xywh(nb, W, H)
            if bw <= 0 or bh <= 0:
                continue
            lines.append(f"{SMOKE} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            ratios.append(bw * bh)

        if sanity:
            main_ratio = max(ratios) if ratios else 0.0
            if not (sanity[0] <= main_ratio <= sanity[1]):
                stats["skipped"] += 1
                continue

        name = f"syn_{out_split}_{stats['generated']:05d}.jpg"
        if not imwrite_u(img_out / name, canvas):
            stats["skipped"] += 1
            continue
        (lbl_out / f"{Path(name).stem}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        stats["generated"] += 1
        stats["ratios"].append(max(ratios) if ratios else 0.0)

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=1600, help="训练集合成张数")
    ap.add_argument("--val", type=int, default=400, help="验证集合成张数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-sources", type=int, default=500,
                    help="烟雾模板池上限（越多越多样，越慢）")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    np.random.seed(args.seed)

    print("=" * 70)
    print("数据集现状扫描")
    print("=" * 70)
    all_fire, all_smoke = {}, {}
    for split in ("train", "val"):
        fo, so, both, empty, combos = scan_split(split)
        all_fire[split], all_smoke[split] = fo, so
        n = sum(combos.values())
        print(f"[{split}] 共 {n} 张  仅火={combos['fire']} 仅烟={combos['smoke']} "
              f"火+烟共现={combos['both']} 空={combos['empty']}")
        print(f"        仅火 {len(fo)} 张 / 仅烟 {len(so)} 张 可用于合成")

    # ── 构建烟雾模板池（优先森林场景，避免把工业/城市背景贴进去）──
    print("\n提取烟雾模板...")
    smoke_dir = all_smoke["train"] + all_smoke["val"]
    scored_smoke = []
    for p in smoke_dir:
        img = imread_u(p)
        if img is None:
            continue
        scored_smoke.append((forest_score(img), p))
    scored_smoke.sort(key=lambda t: -t[0])
    print(f"  烟雾源森林度 最高={scored_smoke[0][0]:.3f} "
          f"中位={scored_smoke[len(scored_smoke) // 2][0]:.3f} "
          f"最低={scored_smoke[-1][0]:.3f}" if scored_smoke else "  无可用烟雾源")

    # 从森林度前 70% 中随机取样，兼顾场景相关性与多样性
    top_smoke = [p for _, p in scored_smoke[: max(1, int(len(scored_smoke) * 0.70))]]
    rng.shuffle(top_smoke)
    pool = []
    for p in top_smoke[: args.max_sources * 3]:
        if len(pool) >= args.max_sources:
            break
        img = imread_u(p)
        if img is None:
            continue
        split = "train" if p.parent.name == "train" else "val"
        items = read_label(SRC_LBL / split / f"{p.stem}.txt")
        patch, alpha = extract_smoke_patch(img, items)
        if patch is not None and patch.shape[0] >= 24 and patch.shape[1] >= 24:
            pool.append((patch, alpha))
    print(f"烟雾模板池: {len(pool)} 个")
    if not pool:
        print("错误: 未能提取到任何烟雾模板，终止")
        sys.exit(1)

    # ── 森林场景优先：原数据集混杂工业/城市场景，按绿色植被占比排序底图 ──
    print("\n按森林场景程度排序火焰底图...")
    ranked_fire = {}
    for split in ("train", "val"):
        arr = []
        for p in all_fire[split]:
            img = imread_u(p)
            if img is None:
                continue
            arr.append((forest_score(img), p))
        arr.sort(key=lambda t: -t[0])
        ranked_fire[split] = [p for _, p in arr]
        if arr:
            print(f"  [{split}] {len(arr)} 张，森林度 最高={arr[0][0]:.3f} "
                  f"中位={arr[len(arr) // 2][0]:.3f} 最低={arr[-1][0]:.3f}")

    # ── 合成 ──
    report = {}
    for split, n_target in (("train", args.train), ("val", args.val)):
        print(f"\n合成 [{split}] {n_target} 张...")
        st = synthesize(ranked_fire[split], pool, n_target, split, rng,
                        sanity=(0.28, 0.80))
        ratios = st["ratios"]
        report[split] = {
            "generated": st["generated"],
            "skipped": st["skipped"],
            "smoke_ratio_median": round(float(np.median(ratios)), 4) if ratios else 0.0,
            "smoke_ratio_min": round(min(ratios), 4) if ratios else 0.0,
            "smoke_ratio_max": round(max(ratios), 4) if ratios else 0.0,
        }
        print(f"  生成 {st['generated']} 张，跳过 {st['skipped']} 次尝试")
        if ratios:
            print(f"  烟雾面积占比  中位数={np.median(ratios):.3f}  "
                  f"最小={min(ratios):.3f}  最大={max(ratios):.3f}")

    (OUT / "synth_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 70)
    print("完成。报告: data/synth/synth_report.json")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    sys.exit(main())
