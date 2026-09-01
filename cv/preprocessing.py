"""Image preprocessing for rim detection.

The downstream radial search expects a binary edge map where nonzero pixels are
candidate rim edges. This module keeps the preprocessing small and tunable from
the Streamlit sidebar: grayscale, Gaussian blur, then Canny.
"""

import cv2
import numpy as np


def generate_edge_map(
    crop_rgb,
    blur_kernel=9,
    canny_low=40,
    canny_high=120
):
    """Convert an RGB crop into grayscale, blurred image, and Canny edges."""
    if blur_kernel % 2 == 0:
        # OpenCV Gaussian kernels must be odd. Coerce here so callers can pass
        # programmatic values without crashing the app.
        blur_kernel += 1

    # OpenCV expects explicit color-space conversion; the app stores images as
    # RGB arrays because PIL/Streamlit use RGB ordering.
    crop_gray = cv2.cvtColor(
        crop_rgb,
        cv2.COLOR_RGB2GRAY
    )

    crop_blur = cv2.GaussianBlur(
        crop_gray,
        (blur_kernel, blur_kernel),
        0
    )

    edges = cv2.Canny(
        crop_blur,
        threshold1=canny_low,
        threshold2=canny_high
    )

    return {
        "gray": crop_gray,
        "blurred": crop_blur,
        "edges": edges
    }
