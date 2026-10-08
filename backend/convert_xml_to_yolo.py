#!/usr/bin/env python3
"""
XML 标注 → YOLO 格式转换（含数据清洗）
- 解析 train_list.txt / val_list.txt 的两列格式
- 过滤无效框（宽高<=0）、极小框（<3px）
- 保留空标注图片（YOLO 允许无标签的背景图做负样本）
- 复制图片 + 生成 YOLO txt 标签
"""

import os
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

CLASS_NAMES = ['fire', 'smoke']
DATA_ROOT = Path('D:/xiaofang/fire_smoke')
OUTPUT_ROOT = Path('D:/workbody/消防/forest-fire-detection/data/yolo_format')


def parse_list_file(list_path: Path):
    """解析 train_list.txt / val_list.txt，返回 (image_name, xml_name) 对"""
    pairs = []
    with open(list_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                img = Path(parts[0]).name   # images/xxx.jpg → xxx.jpg
                xml = Path(parts[1]).name   # annotations/xxx.xml → xxx.xml
                pairs.append((img, xml))
    return pairs


def convert_one(xml_path: Path, output_dir: Path):
    """转换单个 XML → YOLO txt，返回有效框数"""
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return 0

    root = tree.getroot()
    size = root.find('size')
    if size is None:
        return 0
    w = int(size.find('width').text)
    h = int(size.find('height').text)
    if w <= 0 or h <= 0:
        return 0

    lines = []
    for obj in root.findall('object'):
        name = obj.find('name').text
        if name not in CLASS_NAMES:
            continue
        class_id = CLASS_NAMES.index(name)

        bb = obj.find('bndbox')
        xmin = float(bb.find('xmin').text)
        ymin = float(bb.find('ymin').text)
        xmax = float(bb.find('xmax').text)
        ymax = float(bb.find('ymax').text)

        bw = xmax - xmin
        bh = ymax - ymin
        if bw <= 0 or bh <= 0 or bw < 3 or bh < 3:
            continue

        # 裁剪到图像范围
        xmin = max(0, xmin)
        ymin = max(0, ymin)
        xmax = min(w, xmax)
        ymax = min(h, ymax)

        x_center = (xmin + xmax) / 2.0 / w
        y_center = (ymin + ymax) / 2.0 / h
        box_w = (xmax - xmin) / w
        box_h = (ymax - ymin) / h

        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}")

    txt_path = output_dir / (xml_path.stem + '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return len(lines)


def process_split(pairs, split_name):
    """处理一个数据集划分"""
    label_dir = OUTPUT_ROOT / 'labels' / split_name
    image_dir = OUTPUT_ROOT / 'images' / split_name
    label_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    valid = 0
    skipped = 0
    total_boxes = 0

    for img_name, xml_name in pairs:
        xml_path = DATA_ROOT / 'annotations' / xml_name
        img_path = DATA_ROOT / 'images' / img_name

        if not xml_path.exists() or not img_path.exists():
            skipped += 1
            continue

        box_count = convert_one(xml_path, label_dir)
        shutil.copy2(img_path, image_dir / img_name)
        total_boxes += box_count
        valid += 1

    print(f"  {split_name}: {valid} 张图片, {total_boxes} 个框, 跳过 {skipped}")


def main():
    print(f"数据源: {DATA_ROOT}")
    print(f"输出到: {OUTPUT_ROOT}")

    train_pairs = parse_list_file(DATA_ROOT / 'train_list.txt')
    val_pairs = parse_list_file(DATA_ROOT / 'val_list.txt')

    print(f"训练集列表: {len(train_pairs)}")
    print(f"验证集列表: {len(val_pairs)}")

    print("开始转换...")
    process_split(train_pairs, 'train')
    process_split(val_pairs, 'val')

    # 生成 data.yaml
    yaml_content = f"""# 森林火灾烟雾检测数据集
path: {OUTPUT_ROOT.as_posix()}
train: images/train
val: images/val

nc: {len(CLASS_NAMES)}
names: {CLASS_NAMES}
"""
    yaml_path = OUTPUT_ROOT / 'data.yaml'
    yaml_path.write_text(yaml_content, encoding='utf-8')
    print(f"data.yaml → {yaml_path}")
    print("完成！")


if __name__ == '__main__':
    main()