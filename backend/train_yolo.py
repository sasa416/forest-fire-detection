#!/usr/bin/env python3
"""
YOLOv8 森林火灾烟雾检测 - 训练 + 评估脚本
数据集: D:/xiaofang/fire_smoke (含 265 张空标注负样本)
新划分: train 5552 (含 212 负样本) / val 1388 (含 53 负样本)
过滤退化框 (宽或高 <= 0) 已在 convert_xml_to_yolo.py 中处理
"""

from ultralytics import YOLO
import os
import yaml
from pathlib import Path


# ── 配置 ──────────────────────────────────────────────
DATASET_CONFIG = r"D:\workbody\消防\forest-fire-detection\data\yolo_format\data.yaml"
MODEL_SAVE_DIR = r"D:\workbody\消防\forest-fire-detection\models"
YOLO_ROOT = Path(r"D:\workbody\消防\forest-fire-detection\data\yolo_format")

# 续训权重路径（从上次中断的 last.pt 继续）
RESUME_WEIGHTS = r"D:\workbody\消防\forest-fire-detection\models\fire_smoke_v3-2\weights\last.pt"

# 负样本图（空标签）列表，用于评估误检
VAL_LABEL_DIR = YOLO_ROOT / "labels" / "val"
VAL_IMAGE_DIR = YOLO_ROOT / "images" / "val"


def load_dataset_config(config_path):
    """加载数据集配置"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_negative_samples(label_dir: Path) -> list:
    """获取空标签文件对应的图片文件名列表"""
    neg = []
    for txt in sorted(label_dir.glob("*.txt")):
        if txt.stat().st_size == 0:
            neg.append(txt.stem + ".jpg")
    return neg


def train_model():
    """训练 YOLOv8 模型（支持续训）"""

    # ── 检查数据集 ──
    if not os.path.exists(DATASET_CONFIG):
        print(f"错误: 数据集配置不存在 {DATASET_CONFIG}")
        print("请先运行 convert_xml_to_yolo.py")
        return None

    config = load_dataset_config(DATASET_CONFIG)
    print(f"数据集路径: {config['path']}")
    print(f"类别数量: {config['nc']}")
    print(f"类别名称: {config['names']}")

    data_path = Path(config['path'])
    if not data_path.exists():
        print(f"错误: 数据集路径不存在 {data_path}")
        return None

    # 统计负样本
    neg_train = get_negative_samples(YOLO_ROOT / "labels" / "train")
    neg_val = get_negative_samples(VAL_LABEL_DIR)
    print(f"训练集负样本(空标注): {len(neg_train)} 张")
    print(f"验证集负样本(空标注): {len(neg_val)} 张")

    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)

    # ── 判断续训 vs 从头训练 ──
    if os.path.exists(RESUME_WEIGHTS):
        print(f"检测到上次训练权重: {RESUME_WEIGHTS}")
        print("从 last.pt 续训...")
        model = YOLO(RESUME_WEIGHTS)
        resume = True
    else:
        print("未找到续训权重，从 YOLOv8s 预训练模型开始...")
        model = YOLO('yolov8s.pt')
        resume = False

    # ── 训练参数 ──
    train_params = {
        'data': DATASET_CONFIG,
        'epochs': 100,
        'imgsz': 640,
        'batch': 16,
        'name': 'fire_smoke_v3-2',  # 与上次一致，续训写入同一目录
        'project': MODEL_SAVE_DIR,
        'patience': 20,
        'save': True,
        'save_period': 10,
        'cache': False,
        'device': 0,
        'workers': 8,
        'pretrained': True,
        'optimizer': 'AdamW',
        'lr0': 0.001,
        'lrf': 0.01,
        'momentum': 0.937,
        'weight_decay': 0.0005,
        'warmup_epochs': 3,
        'warmup_momentum': 0.8,
        'warmup_bias_lr': 0.1,
        'box': 7.5,
        'cls': 0.5,
        'dfl': 1.5,
        'close_mosaic': 10,
        'amp': True,
        'resume': resume,
    }

    print("开始训练...")
    print(f"训练参数: {train_params}")
    results = model.train(**train_params)

    best_path = os.path.join(MODEL_SAVE_DIR, "fire_smoke_v3-2", "weights", "best.pt")
    last_path = os.path.join(MODEL_SAVE_DIR, "fire_smoke_v3-2", "weights", "last.pt")
    print(f"\n训练完成！")
    print(f"best.pt: {best_path}")
    print(f"last.pt: {last_path}")

    return best_path


def evaluate(best_pt_path: str):
    """评估 best.pt 在 val 集上的 mAP + 负样本误检统计"""
    print("\n" + "=" * 60)
    print("评估阶段")
    print("=" * 60)

    if not os.path.exists(best_pt_path):
        print(f"错误: best.pt 不存在 {best_pt_path}")
        return

    model = YOLO(best_pt_path)

    # ── 1. 标准 mAP 评估 ──
    print("\n[1/2] 在 val 集上计算 mAP ...")
    val_results = model.val(
        data=DATASET_CONFIG,
        imgsz=640,
        batch=16,
        device=0,
        conf=0.25,
        iou=0.45,
        verbose=True,
    )

    print(f"\n--- Val 集 mAP 结果 ---")
    print(f"mAP50    : {val_results.box.map50:.4f}")
    print(f"mAP50-95 : {val_results.box.map:.4f}")
    for i, name in model.names.items():
        ap50 = val_results.box.ap50[i] if i < len(val_results.box.ap50) else 0
        print(f"  {name:8s} AP50 = {ap50:.4f}")

    # ── 2. 负样本误检统计 ──
    print(f"\n[2/2] 负样本误检统计 ...")
    neg_samples = get_negative_samples(VAL_LABEL_DIR)
    print(f"验证集负样本数: {len(neg_samples)}")

    conf_thresholds = [0.25, 0.35, 0.5]

    for conf_thresh in conf_thresholds:
        total_fp = 0
        fp_by_class = {"fire": 0, "smoke": 0}
        images_with_fp = 0

        for img_name in neg_samples:
            img_path = VAL_IMAGE_DIR / img_name
            if not img_path.exists():
                continue

            results = model.predict(
                source=str(img_path),
                conf=conf_thresh,
                iou=0.45,
                verbose=False,
                device=0,
            )

            for r in results:
                if len(r.boxes) > 0:
                    images_with_fp += 1
                for box in r.boxes:
                    cls_name = model.names[int(box.cls[0])]
                    if cls_name in fp_by_class:
                        fp_by_class[cls_name] += 1
                    total_fp += 1

        print(f"\n  conf={conf_thresh}:")
        print(f"    误检框总数: {total_fp}")
        print(f"    fire误检: {fp_by_class['fire']}, smoke误检: {fp_by_class['smoke']}")
        print(f"    产生误检的图片: {images_with_fp}/{len(neg_samples)}")
        if total_fp == 0:
            print(f"    ✓ 零误检！")

    print("\n评估完成。")


if __name__ == "__main__":
    best_path = train_model()
    if best_path:
        evaluate(best_path)