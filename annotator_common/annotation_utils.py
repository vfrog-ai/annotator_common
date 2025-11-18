"""
Annotation utilities independent of Supabase.
"""

from typing import Dict, List


def calculate_bbox_overlap(bbox1: List, bbox2: List) -> float:
    """Calculate IoU (Intersection over Union) between two bounding boxes."""
    x1_1, y1_1, x2_1, y2_1 = bbox1
    x1_2, y1_2, x2_2, y2_2 = bbox2

    # Calculate intersection
    x_left = max(x1_1, x1_2)
    y_top = max(y1_1, y1_2)
    x_right = min(x2_1, x2_2)
    y_bottom = min(y2_1, y2_2)

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union_area = area1 + area2 - intersection_area

    if union_area == 0:
        return 0.0

    return intersection_area / union_area


def filter_overlapping_bboxes(
    annotations: List[Dict], overlap_threshold: float = 0.5
) -> List[Dict]:
    """Filter out overlapping bounding boxes, keeping only the first occurrence."""
    if len(annotations) <= 1:
        return annotations

    keep_bbox = [True] * len(annotations)

    for i in range(1, len(annotations)):
        if not keep_bbox[i]:
            continue

        current_bbox = annotations[i].get("bbox", [0, 0, 0, 0])
        if len(current_bbox) != 4:
            continue

        for j in range(i):
            if not keep_bbox[j]:
                continue

            previous_bbox = annotations[j].get("bbox", [0, 0, 0, 0])
            if len(previous_bbox) != 4:
                continue

            overlap_ratio = calculate_bbox_overlap(current_bbox, previous_bbox)

            if overlap_ratio >= overlap_threshold:
                keep_bbox[i] = False
                break

    return [ann for i, ann in enumerate(annotations) if keep_bbox[i]]


def transform_annotations_for_supabase(
    annotations: List[Dict], overlap_threshold: float = 0.5
) -> List[Dict]:
    """
    Transform annotations from [x1, y1, x2, y2] to [x, y, width, height] format.
    Name preserved for backward compatibility with callers.
    """
    filtered = filter_overlapping_bboxes(annotations, overlap_threshold)

    transformed = []
    for ann in filtered:
        bbox = ann.get("bbox", [0, 0, 0, 0])
        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            transformed.append(
                {
                    "label": ann.get("label", "Unknown"),
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "color": "#0018F9",
                }
            )
    return transformed

