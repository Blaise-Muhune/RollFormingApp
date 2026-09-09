"""Opening-mask refine + rim geometry seed (SAM → GrabCut → ellipse).

Used after GroundingDINO crop to estimate a better center/radius before the
radial multistart rim tracker runs. SAM is optional/lazy; OpenCV GrabCut always
works offline.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

_SAM_MODEL = None
_SAM_PROCESSOR = None
_SAM_DEVICE = None
_SAM_LOAD_ATTEMPTED = False
_SAM_LOAD_ERROR: str | None = None

# Lighter than vit-huge — still a first-time download (~375MB).
DEFAULT_SAM_MODEL_ID = "facebook/sam-vit-base"


def prompt_box_from_crop(
    height: int,
    width: int,
    inner_size: tuple[int, int] | None = None,
    *,
    inset_frac: float = 0.08,
) -> list[float]:
    """Box prompt in crop coordinates ``[x1, y1, x2, y2]``.

    When DINO reported an inner size, the crop includes pad — reconstruct the
    inner opening box. Otherwise use an inset of the full crop.
    """
    h, w = int(height), int(width)
    if inner_size is not None:
        iw, ih = float(inner_size[0]), float(inner_size[1])
        cx, cy = w * 0.5, h * 0.5
        x1 = max(0.0, cx - 0.5 * iw)
        y1 = max(0.0, cy - 0.5 * ih)
        x2 = min(float(w - 1), cx + 0.5 * iw)
        y2 = min(float(h - 1), cy + 0.5 * ih)
        if x2 - x1 >= 16 and y2 - y1 >= 16:
            return [x1, y1, x2, y2]

    pad_x = inset_frac * w
    pad_y = inset_frac * h
    return [
        pad_x,
        pad_y,
        max(pad_x + 1, w - 1 - pad_x),
        max(pad_y + 1, h - 1 - pad_y),
    ]


def grabcut_mask_from_box(crop_rgb: np.ndarray, box: list[float]) -> np.ndarray:
    """Foreground mask via GrabCut seeded by the detection box (no extra deps)."""
    h, w = crop_rgb.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1 = max(0, min(w - 2, x1))
    y1 = max(0, min(h - 2, y1))
    x2 = max(x1 + 1, min(w - 1, x2))
    y2 = max(y1 + 1, min(h - 1, y2))
    rect = (x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    img = np.ascontiguousarray(crop_rgb)
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        out = np.zeros((h, w), np.uint8)
        out[y1:y2, x1:x2] = 1
        return out

    return np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(
        np.uint8
    )


def _load_sam(model_id: str = DEFAULT_SAM_MODEL_ID):
    """Lazy-load SAM; returns (processor, model, device) or raises."""
    global _SAM_MODEL, _SAM_PROCESSOR, _SAM_DEVICE, _SAM_LOAD_ATTEMPTED, _SAM_LOAD_ERROR
    if _SAM_MODEL is not None and _SAM_PROCESSOR is not None:
        return _SAM_PROCESSOR, _SAM_MODEL, _SAM_DEVICE
    if _SAM_LOAD_ATTEMPTED and _SAM_LOAD_ERROR:
        raise RuntimeError(_SAM_LOAD_ERROR)

    _SAM_LOAD_ATTEMPTED = True
    try:
        import torch
        from transformers import SamModel, SamProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        processor = SamProcessor.from_pretrained(model_id)
        model = SamModel.from_pretrained(model_id).to(device)
        model.eval()
        _SAM_PROCESSOR = processor
        _SAM_MODEL = model
        _SAM_DEVICE = device
        return processor, model, device
    except Exception as exc:
        _SAM_LOAD_ERROR = str(exc)
        raise


def sam_mask_from_box(
    crop_rgb: np.ndarray,
    box: list[float],
    *,
    model_id: str = DEFAULT_SAM_MODEL_ID,
) -> np.ndarray:
    """Binary mask from SAM with a single box prompt (crop-local coords)."""
    import torch
    from PIL import Image

    processor, model, device = _load_sam(model_id=model_id)
    image = Image.fromarray(np.ascontiguousarray(crop_rgb).astype(np.uint8))
    input_boxes = [[[float(box[0]), float(box[1]), float(box[2]), float(box[3])]]]
    inputs = processor(image, input_boxes=input_boxes, return_tensors="pt")
    inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    masks = processor.image_processor.post_process_masks(
        outputs.pred_masks.cpu(),
        inputs["original_sizes"].cpu(),
        inputs["reshaped_input_sizes"].cpu(),
    )
    scores = outputs.iou_scores.cpu().numpy()
    mask_batch = masks[0]
    if hasattr(mask_batch, "numpy"):
        mask_batch = mask_batch.numpy()
    mask_batch = np.asarray(mask_batch)
    while mask_batch.ndim > 3:
        mask_batch = mask_batch[0]
    if mask_batch.ndim == 2:
        best = mask_batch
    else:
        score_row = np.asarray(scores).reshape(-1)
        if score_row.size == mask_batch.shape[0]:
            best = mask_batch[int(np.argmax(score_row))]
        else:
            areas = [float(m.sum()) for m in mask_batch]
            best = mask_batch[int(np.argmax(areas))]

    binary = (best > 0.5).astype(np.uint8)
    if binary.shape[:2] != crop_rgb.shape[:2]:
        binary = cv2.resize(
            binary,
            (crop_rgb.shape[1], crop_rgb.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
    return binary


def ellipse_seed_from_mask(mask: np.ndarray) -> dict[str, Any] | None:
    """Fit an ellipse to the largest external contour of a binary mask."""
    if mask is None or mask.size == 0:
        return None
    binary = (mask > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < 200 or len(contour) < 5:
        return None

    try:
        (cx, cy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
    except cv2.error:
        return None

    radius = 0.25 * (float(axis_a) + float(axis_b))
    if radius < 8:
        return None

    h, w = binary.shape[:2]
    return {
        "center_x": float(np.clip(cx, 0, w - 1)),
        "center_y": float(np.clip(cy, 0, h - 1)),
        "expected_radius": float(radius),
        "ellipse": {
            "center": (float(cx), float(cy)),
            "axes": (float(axis_a), float(axis_b)),
            "angle": float(angle),
        },
        "contour_area": area,
        "coverage": float(area) / float(max(1, h * w)),
    }


def ransac_circle_from_edges(
    edges: np.ndarray,
    box: list[float],
    *,
    max_samples: int = 2500,
) -> dict[str, Any] | None:
    """RANSAC circle on Canny edge pixels inside the prompt box (fallback)."""
    h, w = edges.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    roi = edges[y1:y2, x1:x2]
    ys, xs = np.where(roi > 0)
    if xs.size < 40:
        return None
    xs = xs.astype(np.float64) + x1
    ys = ys.astype(np.float64) + y1
    if xs.size > max_samples:
        idx = np.random.default_rng(0).choice(xs.size, size=max_samples, replace=False)
        xs, ys = xs[idx], ys[idx]

    pts = np.column_stack([xs, ys]).astype(np.float32)
    best = None
    best_inliers = 0
    rng = np.random.default_rng(1)
    n = pts.shape[0]
    for _ in range(80):
        sample_idx = rng.choice(n, size=3, replace=False)
        circle = _circle_from_3_points(pts[sample_idx])
        if circle is None:
            continue
        cx, cy, r = circle
        if r < 8 or r > 0.6 * max(h, w):
            continue
        dist = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r)
        inliers = int(np.count_nonzero(dist < 3.0))
        if inliers > best_inliers:
            best_inliers = inliers
            best = (cx, cy, r, inliers)

    if best is None or best[3] < 30:
        return None
    cx, cy, r, inliers = best
    return {
        "center_x": float(cx),
        "center_y": float(cy),
        "expected_radius": float(r),
        "ellipse": None,
        "contour_area": float(np.pi * r * r),
        "coverage": float(np.pi * r * r) / float(max(1, h * w)),
        "inliers": int(inliers),
    }


def _circle_from_3_points(pts: np.ndarray) -> tuple[float, float, float] | None:
    """Return (cx, cy, r) for three points, or None if collinear."""
    (x1, y1), (x2, y2), (x3, y3) = pts
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-6:
        return None
    ux = (
        (x1 * x1 + y1 * y1) * (y2 - y3)
        + (x2 * x2 + y2 * y2) * (y3 - y1)
        + (x3 * x3 + y3 * y3) * (y1 - y2)
    ) / d
    uy = (
        (x1 * x1 + y1 * y1) * (x3 - x2)
        + (x2 * x2 + y2 * y2) * (x1 - x3)
        + (x3 * x3 + y3 * y3) * (x2 - x1)
    ) / d
    r = float(np.hypot(x1 - ux, y1 - uy))
    return float(ux), float(uy), r


def seed_rim_geometry(
    crop_rgb: np.ndarray,
    *,
    edges: np.ndarray | None = None,
    inner_size: tuple[int, int] | None = None,
    use_sam: bool = True,
) -> dict[str, Any]:
    """Estimate rim center/radius from mask (SAM or GrabCut) + ellipse fit.

    Always returns a usable seed dict. ``mask_source`` records which path won.
    """
    h, w = crop_rgb.shape[:2]
    box = prompt_box_from_crop(h, w, inner_size)
    mask = None
    source = "fallback"

    if use_sam:
        try:
            mask = sam_mask_from_box(crop_rgb, box)
            source = "sam"
        except Exception:
            mask = None

    if mask is None or int(mask.sum()) < 200:
        try:
            mask = grabcut_mask_from_box(crop_rgb, box)
            source = "grabcut"
        except Exception:
            mask = None

    seed = ellipse_seed_from_mask(mask) if mask is not None else None
    if seed is None and edges is not None:
        seed = ransac_circle_from_edges(edges, box)
        if seed is not None:
            source = f"{source}+ransac" if source != "fallback" else "ransac"

    if seed is None:
        if inner_size is not None:
            radius = 0.5 * float(min(inner_size[0], inner_size[1]))
        else:
            radius = 0.45 * float(min(h, w))
        seed = {
            "center_x": float(w) * 0.5,
            "center_y": float(h) * 0.5,
            "expected_radius": float(max(10.0, radius)),
            "ellipse": None,
            "contour_area": 0.0,
            "coverage": 0.0,
        }
        source = "fallback"

    seed["mask_source"] = source
    seed["prompt_box"] = box
    seed["mask"] = mask
    return seed
