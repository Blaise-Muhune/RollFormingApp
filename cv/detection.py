"""Object-detection utilities for locating the tank/rim region.

The app uses a zero-shot detector so the project can recognize likely tank
openings without training a custom model. If accuracy becomes inconsistent in
production, this is the module to replace with a fine-tuned detector or a more
controlled segmentation pipeline.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from io import BytesIO

import cv2
import numpy as np
from PIL import Image


DEFAULT_TANK_LABELS = [
    # GroundingDINO is sensitive to wording. Keep several near-synonyms so one
    # weak phrase does not prevent a usable crop on shop-floor photos.
    "large circular metal tank opening",
    "steel cylinder opening",
    "round metal shell",
    "metal tank rim",
]

_DETECTOR = None


def load_detector():
    """Create the Hugging Face zero-shot detector (lazy singleton)."""
    global _DETECTOR
    if _DETECTOR is None:
        from transformers import pipeline

        _DETECTOR = pipeline(
            model="IDEA-Research/grounding-dino-base",
            task="zero-shot-object-detection",
        )
    return _DETECTOR


def detect_tank_region(
    image,
    detector,
    candidate_labels=None,
    threshold=0.25
):
    """Return raw detector boxes for candidate tank-opening labels.

    Expected ``results`` item shape from transformers:
    ``{"score": float, "label": str, "box": {"xmin", "ymin", "xmax", "ymax"}}``.
    Downstream helpers rely on that structure, so update them together if the
    detector/model API changes.
    """
    if candidate_labels is None:
        candidate_labels = DEFAULT_TANK_LABELS

    results = detector(
        image,
        candidate_labels=candidate_labels,
        threshold=threshold
    )

    return results


def draw_detection_boxes(image, results):
    """Draw detector output for the optional UI expander."""
    image_np = np.array(image).copy()

    for result in results:
        box = result["box"]
        label = result["label"]
        score = result["score"]

        x_min = int(box["xmin"])
        y_min = int(box["ymin"])
        x_max = int(box["xmax"])
        y_max = int(box["ymax"])

        cv2.rectangle(
            image_np,
            (x_min, y_min),
            (x_max, y_max),
            (0, 255, 0),
            4
        )

        cv2.putText(
            image_np,
            f"{label}: {score:.2f}",
            (x_min, max(y_min - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    return image_np


def crop_best_detection(image, results, *, pad_ratio=0.18, min_pad_px=48):
    """Crop to the highest-confidence detection, with margin around the roll.

    The detector box is usually tight on the metal. Extra pad keeps the rim
    (and the overlay ring) inside the crop so search and display are not clipped.
    """
    if len(results) == 0:
        return image, None, None

    best = max(results, key=lambda r: r["score"])
    box = best["box"]

    x_min = int(box["xmin"])
    y_min = int(box["ymin"])
    x_max = int(box["xmax"])
    y_max = int(box["ymax"])

    inner_w = max(1, x_max - x_min)
    inner_h = max(1, y_max - y_min)
    pad = max(int(min_pad_px), int(round(pad_ratio * max(inner_w, inner_h))))

    img_w, img_h = image.size
    x_min = max(0, x_min - pad)
    y_min = max(0, y_min - pad)
    x_max = min(img_w, x_max + pad)
    y_max = min(img_h, y_max + pad)

    crop = image.crop((x_min, y_min, x_max, y_max))
    return crop, best, (inner_w, inner_h)


def detect_and_crop_tank(
    image,
    detector,
    candidate_labels=None,
    threshold=0.25
):
    """Run detection, produce the annotated preview, and crop the best region."""
    results = detect_tank_region(
        image=image,
        detector=detector,
        candidate_labels=candidate_labels,
        threshold=threshold
    )

    annotated_image = draw_detection_boxes(
        image=image,
        results=results
    )

    crop, best_detection, inner_size = crop_best_detection(
        image=image,
        results=results
    )

    return {
        "results": results,
        "annotated_image": annotated_image,
        "crop": crop,
        "best_detection": best_detection,
        "inner_size": inner_size,
    }


@lru_cache(maxsize=24)
def _cached_detect_and_crop_tank(image_sha: str, threshold: float, image_bytes: bytes):
    """Cache DINO crop by image content (bytes kept for reconstruction)."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    return detect_and_crop_tank(
        image=image,
        detector=load_detector(),
        threshold=float(threshold),
    )


def detect_and_crop_tank_cached(image_bytes: bytes, *, threshold: float = 0.25):
    """Shop-floor helper: auto-crop with LRU cache keyed by image hash."""
    sha = hashlib.sha1(image_bytes).hexdigest()
    return _cached_detect_and_crop_tank(sha, float(threshold), image_bytes)
