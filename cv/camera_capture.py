"""Optional Streamlit camera-capture UI.

The main upload workflow does not currently import this module, but it is kept
as a reusable component for future live-capture workflows. It stores camera
state in ``st.session_state`` because Streamlit reruns the script after every
button click.
"""

import time
import cv2
import streamlit as st
from PIL import Image


@st.cache_resource
def get_camera(camera_index=0):
    """Open a camera once and reuse it across Streamlit reruns."""
    return cv2.VideoCapture(camera_index)


def draw_alignment_circle(
    frame,
    guide_radius_ratio=0.38,
    guide_color=(96, 165, 250),
    guide_thickness=3
):
    """Overlay a centered guide that helps operators frame the tank opening."""
    height, width = frame.shape[:2]

    center_x = width // 2
    center_y = height // 2

    radius = int(min(width, height) * guide_radius_ratio)

    cv2.circle(
        frame,
        (center_x, center_y),
        radius,
        guide_color,
        guide_thickness
    )

    cv2.circle(
        frame,
        (center_x, center_y),
        5,
        guide_color,
        -1
    )

    return frame


def render_camera_capture(
    guide_radius_ratio=0.38,
    guide_color=(96, 165, 250),
    guide_thickness=3
):
    """Render controls for live preview and return the latest captured frame.

    Return type is either a PIL ``Image`` ready for the analysis pipeline or
    ``None`` if no frame has been captured yet.
    """
    st.subheader("Camera Capture")

    # These keys survive Streamlit reruns and act like a minimal camera state
    # machine: stopped, running preview, or captured image available.
    if "camera_running" not in st.session_state:
        st.session_state.camera_running = False

    if "captured_camera_image" not in st.session_state:
        st.session_state.captured_camera_image = None

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Start Camera"):
            st.session_state.camera_running = True

    with col2:
        capture_clicked = st.button("Capture Frame")

    with col3:
        if st.button("Stop Camera"):
            st.session_state.camera_running = False

    camera_placeholder = st.empty()

    if st.session_state.camera_running:
        cap = get_camera(0)

        ret, frame = cap.read()

        if not ret:
            # Usually means no camera is attached, another app owns it, or the
            # requested index is wrong on this machine.
            st.warning("Could not read from camera.")
            return st.session_state.captured_camera_image

        # cv2 captures BGR; Streamlit/PIL expect RGB.
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Keep an unannotated copy for analysis. The alignment circle is only a
        # preview overlay and must not become part of the measured rim.
        raw_frame = frame.copy()

        preview_frame = draw_alignment_circle(
            frame=frame.copy(),
            guide_radius_ratio=guide_radius_ratio,
            guide_color=guide_color,
            guide_thickness=guide_thickness
        )

        camera_placeholder.image(
            preview_frame,
            caption="Live camera feed with alignment guide",
            use_container_width=True
        )

        if capture_clicked:
            st.session_state.captured_camera_image = Image.fromarray(raw_frame)
            st.session_state.camera_running = False
            st.success("Frame captured.")

        # Streamlit does not provide a true video loop here, so rerunning the
        # script with a tiny delay creates a simple live preview.
        time.sleep(0.05)
        st.rerun()

    if st.session_state.captured_camera_image is not None:
        st.image(
            st.session_state.captured_camera_image,
            caption="Captured frame for analysis",
            width=800
        )

    return st.session_state.captured_camera_image
