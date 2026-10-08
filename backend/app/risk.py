#!/usr/bin/env python3
"""图像火灾风险分级

图像检测只有单帧，拿不到视频那套「跨帧持续时长」证据，
所以改用**可见证据强度**打分，四个维度：

    1. 目标类别   明火(50) > 仅有烟雾(30)     —— 明火是已燃烧的确定性证据
    2. 共现关系   火+烟同时出现(+15)          —— 符合火场典型特征
    3. 置信度     最高置信度 ≥80%(+10) / ≥50%(+5)
    4. 覆盖面积   火焰占画面 ≥10%(+10) / 烟雾占画面 ≥25%(+10)
                  —— 大范围扩散意味着火势已蔓延

分数 → 等级 → 处置建议，前端按等级上色。
"""

LEVEL_HIGH = "高风险 - 确认火灾"
LEVEL_MID = "中风险 - 疑似火灾"
LEVEL_LOW = "低风险 - 需人工确认"
LEVEL_NONE = "无风险 - 未检测到异常"

ADVICE_HIGH = "立即启动应急预案，就近核查火点并上报；同步持续监控该区域。"
ADVICE_MID = "尽快安排人员现场核查，并加密该区域巡检频次。"
ADVICE_LOW = "建议人工复核该图像，必要时调取同点位视频流交叉验证。"
ADVICE_NONE = "无需处置，保持常规巡检。"

# 面积阈值：低于这个占比说明只是局部小目标，不构成扩散证据
FIRE_AREA_ALERT = 0.10
SMOKE_AREA_ALERT = 0.25
MULTI_TARGET_MIN = 3


def assess_image_risk(detections, image_width, image_height):
    """对单帧检测结果做风险分级

    :param detections: [{'cls': 'fire'|'smoke', 'conf': float, 'xyxy': [x1,y1,x2,y2]}]
    :return: dict，可直接喂给 pydantic 的 RiskAssessment
    """
    frame_area = max(1.0, float(image_width) * float(image_height))

    def area_ratio(item):
        x1, y1, x2, y2 = item["xyxy"]
        return max(0.0, x2 - x1) * max(0.0, y2 - y1) / frame_area

    fires = [d for d in detections if d.get("cls") == "fire"]
    smokes = [d for d in detections if d.get("cls") == "smoke"]

    max_fire_conf = max((d["conf"] for d in fires), default=0.0)
    max_smoke_conf = max((d["conf"] for d in smokes), default=0.0)
    max_conf = max(max_fire_conf, max_smoke_conf)
    max_fire_ratio = max((area_ratio(d) for d in fires), default=0.0)
    max_smoke_ratio = max((area_ratio(d) for d in smokes), default=0.0)

    score = 0
    reasons = []

    # 1. 类别
    if fires:
        score += 50
        reasons.append(f"检出 {len(fires)} 处明火（最高 {max_fire_conf:.0%}）(+50)")
    elif smokes:
        score += 30
        reasons.append(f"仅检出烟雾、未见明火（最高 {max_smoke_conf:.0%}）(+30)")

    # 2. 共现
    if smokes:
        score += 15
        if fires:
            reasons.append(f"火焰与烟雾共现 {len(smokes)} 处，符合已燃烧特征(+15)")
        else:
            reasons.append(f"检出 {len(smokes)} 处烟雾(+15)")

    # 3. 置信度
    if max_conf >= 0.80:
        score += 10
        reasons.append(f"最高置信度 {max_conf:.0%} ≥ 80%(+10)")
    elif max_conf >= 0.50:
        score += 5
        reasons.append(f"最高置信度 {max_conf:.0%} ≥ 50%(+5)")

    # 4. 覆盖面积
    if max_fire_ratio >= FIRE_AREA_ALERT:
        score += 10
        reasons.append(f"火焰覆盖画面 {max_fire_ratio:.0%} ≥ 10%，火势范围较大(+10)")
    if max_smoke_ratio >= SMOKE_AREA_ALERT:
        score += 10
        reasons.append(f"烟雾覆盖画面 {max_smoke_ratio:.0%} ≥ 25%，扩散范围大(+10)")

    # 5. 多点燃烧
    if len(detections) >= MULTI_TARGET_MIN:
        score += 5
        reasons.append(f"共 {len(detections)} 个目标，疑似多点燃烧(+5)")

    score = min(score, 100)

    if score >= 70:
        level, advice = LEVEL_HIGH, ADVICE_HIGH
    elif score >= 45:
        level, advice = LEVEL_MID, ADVICE_MID
    elif score >= 20:
        level, advice = LEVEL_LOW, ADVICE_LOW
    else:
        # 没有任何有效证据时清零，避免出现「0 分却低风险」的自相矛盾输出
        score, level, advice, reasons = 0, LEVEL_NONE, ADVICE_NONE, []

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "advice": advice,
        "fire_count": len(fires),
        "smoke_count": len(smokes),
        "max_confidence": round(max_conf, 4),
        "max_fire_area_ratio": round(max_fire_ratio, 4),
        "max_smoke_area_ratio": round(max_smoke_ratio, 4),
    }
