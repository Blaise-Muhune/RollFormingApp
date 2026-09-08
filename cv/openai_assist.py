"""OpenAI vision assistant for shop-floor guidance around the CV pipeline.

Classical OpenCV / curvature math remains the measurement source of truth.
These helpers interpret images and metrics for operators: photo QA, failure
troubleshooting, plain-language force guidance, zone sanity checks, shift
reports, and Q&A chat.

Uses GPT-5.6 Terra by default (vision + balanced cost). Override with
``OPENAI_MODEL`` or the Streamlit sidebar.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_dotenv() -> None:
    """Load RollFormingApp/.env so OPENAI_API_KEY is available without cwd luck."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_PROJECT_ROOT / ".env", override=False)


def resolve_api_key(user_key: str | None = None) -> str | None:
    """Use a key the operator typed, otherwise .env / Streamlit secrets.

    Priority: typed field → session override → secrets.toml → OPENAI_API_KEY.
    """
    load_project_dotenv()

    typed = (user_key or "").strip()
    if typed:
        return typed

    try:
        import streamlit as st

        session_key = str(st.session_state.get("user_openai_api_key") or "").strip()
        if session_key:
            return session_key
        if "openai" in st.secrets and st.secrets["openai"].get("api_key"):
            return str(st.secrets["openai"]["api_key"]).strip()
        if st.secrets.get("OPENAI_API_KEY"):
            return str(st.secrets["OPENAI_API_KEY"]).strip()
    except Exception:
        pass

    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    return env_key or None


def api_key_source(user_key: str | None = None) -> str:
    """Where the active key came from (never returns the key itself)."""
    if (user_key or "").strip():
        return "typed"
    load_project_dotenv()
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "env"
    try:
        import streamlit as st

        if "openai" in st.secrets and st.secrets["openai"].get("api_key"):
            return "env"
        if st.secrets.get("OPENAI_API_KEY"):
            return "env"
    except Exception:
        pass
    return "none"

DEFAULT_MODEL = "gpt-5.6-terra"
FALLBACK_MODELS = (
    "gpt-5.6-terra",
    "gpt-5.6",
    "gpt-5.6-sol",
    "gpt-4.1",
    "gpt-4o",
)

SYSTEM_PROMPT = """You are a roll-forming shop-floor assistant for a computer-vision
rim-analysis tool. The classical CV pipeline (edge detection, radial rim
search, curvature math) is the source of truth for measurements and force %.

Rules:
- Never invent new force percentages, radii, or zone percentages. Only use
  numbers provided in the metrics JSON or clearly visible in the images.
- Be concise and practical for operators and process engineers.
- Prefer clock-face directions (e.g. 3 o'clock) when describing angular zones.
  θ = 0 rad is typically to the right; angles increase counterclockwise.
- Correction zone colors on overlays: green = within tolerance, blue = too flat
  (increase force), red = too tight (decrease force).
- Force correction % is geometry-based guidance, not a calibrated machine
  controller. Say so when recommending actions.
- If an image is unsuitable, say what to fix (lighting, angle, framing, glare).
"""


def resolve_model(sidebar_model: str | None = None) -> str:
    model = (sidebar_model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
    return model or DEFAULT_MODEL


def get_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def image_to_data_url(image: Image.Image, max_side: int = 1280, quality: int = 85) -> str:
    """Encode a PIL image as a JPEG data URL for vision requests."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        rgb = rgb.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def ndarray_to_pil(arr) -> Image.Image:
    import numpy as np

    if isinstance(arr, Image.Image):
        return arr.convert("RGB")
    a = np.asarray(arr)
    if a.ndim == 2:
        return Image.fromarray(a).convert("RGB")
    return Image.fromarray(a.astype("uint8")).convert("RGB")


def fig_to_pil(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def content_hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, (bytes, bytearray)):
            h.update(part)
        else:
            h.update(json.dumps(part, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:24]


def _user_content(text: str, images: list[Image.Image] | None = None) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": text}]
    for img in images or []:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": image_to_data_url(img), "detail": "auto"},
            }
        )
    return parts


def chat_completion(
    api_key: str,
    user_text: str,
    *,
    images: list[Image.Image] | None = None,
    model: str | None = None,
    system: str = SYSTEM_PROMPT,
    history: list[dict] | None = None,
    max_completion_tokens: int = 4096,
) -> str:
    """Send a vision/text chat request and return assistant text."""
    client = get_client(api_key)
    model_name = resolve_model(model)

    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": _user_content(user_text, images)})

    kwargs = {
        "model": model_name,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }

    # Prefer low reasoning so shop-floor prompts don't burn the whole token
    # budget on hidden chain-of-thought and return an empty message body.
    for extra in (
        {"reasoning_effort": "low"},
        {"reasoning": {"effort": "low"}},
        {},
    ):
        try:
            response = client.chat.completions.create(**kwargs, **extra)
            break
        except TypeError:
            continue
        except Exception as exc:
            msg = str(exc).lower()
            if extra and ("reasoning" in msg or "unexpected" in msg or "unknown" in msg):
                continue
            # Fall through to max_tokens compatibility, then re-raise.
            try:
                legacy = dict(kwargs)
                legacy.pop("max_completion_tokens", None)
                legacy["max_tokens"] = max_completion_tokens
                response = client.chat.completions.create(**legacy, **extra)
                break
            except Exception:
                raise exc
    else:
        response = client.chat.completions.create(**kwargs)

    text = _extract_message_text(response)
    if not text:
        # One retry with a larger budget — common failure mode on reasoning models.
        kwargs["max_completion_tokens"] = max(max_completion_tokens, 8192)
        try:
            response = client.chat.completions.create(
                **kwargs,
                **{"reasoning_effort": "low"},
            )
        except Exception:
            response = client.chat.completions.create(**kwargs)
        text = _extract_message_text(response)

    if not text:
        raise RuntimeError(
            "OpenAI returned an empty response. Try again, or switch model "
            "(gpt-5.6-terra / gpt-4.1) in the sidebar."
        )
    return text


def _extract_message_text(response) -> str:
    """Pull visible text from Chat Completions (and nested content blocks)."""
    choice = response.choices[0]
    message = choice.message
    content = message.content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text") or "")
            elif hasattr(block, "text"):
                texts.append(getattr(block, "text") or "")
            elif isinstance(block, str):
                texts.append(block)
        content = "\n".join(t for t in texts if t)

    if content and str(content).strip():
        return str(content).strip()

    # Some SDK/model combos put usable text on refusal or other fields.
    refusal = getattr(message, "refusal", None)
    if refusal and str(refusal).strip():
        return str(refusal).strip()

    return ""

def check_photo_quality(api_key: str, image: Image.Image, model: str | None = None) -> str:
    """Legacy markdown-only photo QA (kept for callers that want text only)."""
    result = check_photo_and_calibrate(
        api_key,
        image,
        current_settings={},
        model=model,
    )
    return result.get("quality_markdown") or result.get("verdict", "")


# Allowed sidebar calibration knobs the vision model may recommend.
CALIBRATION_SPECS = {
    "use_auto_crop": {"type": "bool", "default": True},
    "detection_threshold": {
        "type": "float",
        "min": 0.05,
        "max": 0.90,
        "step": 0.05,
        "default": 0.25,
    },
    "canny_low": {"type": "int", "min": 0, "max": 255, "step": 1, "default": 40},
    "canny_high": {"type": "int", "min": 0, "max": 255, "step": 1, "default": 120},
    "blur_kernel": {
        "type": "choice",
        "choices": [3, 5, 7, 9, 11, 13],
        "default": 9,
    },
    "num_points": {
        "type": "int",
        "min": 180,
        "max": 1440,
        "step": 180,
        "default": 720,
    },
    "search_band": {
        "type": "int",
        "min": 20,
        "max": 300,
        "step": 10,
        "default": 120,
    },
    "max_step_change": {
        "type": "int",
        "min": 5,
        "max": 100,
        "step": 5,
        "default": 30,
    },
    "window_size": {
        "type": "int",
        "min": 3,
        "max": 75,
        "step": 2,
        "default": 21,
    },
    "curvature_tolerance": {
        "type": "float",
        "min": 0.5,
        "max": 15.0,
        "step": 0.5,
        "default": 3.0,
    },
}

SETTING_WIDGET_KEYS = {
    "use_auto_crop": "setting_use_auto_crop",
    "detection_threshold": "setting_detection_threshold",
    "canny_low": "setting_canny_low",
    "canny_high": "setting_canny_high",
    "blur_kernel": "setting_blur_kernel",
    "num_points": "setting_num_points",
    "search_band": "setting_search_band",
    "max_step_change": "setting_max_step_change",
    "window_size": "setting_window_size",
    "curvature_tolerance": "setting_curvature_tolerance",
}

SETTING_LABELS = {
    "use_auto_crop": "Use Auto-Crop",
    "detection_threshold": "Detection Threshold",
    "canny_low": "Low Gradient Threshold",
    "canny_high": "High Gradient Threshold",
    "blur_kernel": "Blur Kernel Size",
    "num_points": "Angular Samples",
    "search_band": "Search Band [pixels]",
    "max_step_change": "Max Step Change [pixels]",
    "window_size": "Smoothing Window",
    "curvature_tolerance": "Curvature Tolerance [%]",
}


def _snap_value(key: str, value):
    """Clamp / snap a suggested value to what the Streamlit widget allows."""
    spec = CALIBRATION_SPECS[key]
    if spec["type"] == "bool":
        return bool(value)

    if spec["type"] == "choice":
        choices = spec["choices"]
        try:
            iv = int(round(float(value)))
        except (TypeError, ValueError):
            return spec["default"]
        return min(choices, key=lambda c: abs(c - iv))

    try:
        num = float(value)
    except (TypeError, ValueError):
        return spec["default"]

    num = max(spec["min"], min(spec["max"], num))
    step = spec.get("step", 1)
    # Snap to nearest step from min.
    snapped = spec["min"] + round((num - spec["min"]) / step) * step
    snapped = max(spec["min"], min(spec["max"], snapped))
    if spec["type"] == "int":
        # Keep odd smoothing windows usable.
        iv = int(round(snapped))
        if key == "window_size" and iv % 2 == 0:
            iv = min(spec["max"], iv + 1)
        return iv
    # Float: keep one or two decimals depending on step.
    return round(snapped, 2)


def sanitize_suggestions(raw: dict | None, current: dict | None = None) -> dict:
    """Return only valid calibration keys, snapped to widget ranges."""
    current = current or {}
    raw = raw or {}
    out = {}
    for key in CALIBRATION_SPECS:
        if key in raw and raw[key] is not None:
            out[key] = _snap_value(key, raw[key])
        elif key in current:
            out[key] = _snap_value(key, current[key])
        else:
            out[key] = CALIBRATION_SPECS[key]["default"]

    # Canny high should stay above low.
    if out["canny_high"] <= out["canny_low"]:
        out["canny_high"] = min(255, out["canny_low"] + 40)
    return out


# Pass/fail and rim density must stay shop rules (AI must not loosen / explode cost).
CHECK_ROLL_LOCKED_SETTINGS = (
    "curvature_tolerance",
    "target_mode",
    "num_points",
)


def merge_check_roll_settings(base: dict, suggestions: dict | None) -> dict:
    """Apply vision calibration to Check roll without changing pass/fail tightness."""
    merged = dict(base)
    for key, value in (suggestions or {}).items():
        if key in CHECK_ROLL_LOCKED_SETTINGS:
            continue
        if key in merged:
            merged[key] = value
    return merged


def review_rim_tracking(
    api_key: str,
    *,
    original: Image.Image,
    overlay: Image.Image,
    current_settings: dict,
    model: str | None = None,
) -> dict:
    """Ask whether the colored dots sit on the real opening rim.

    Returns rim_ok, issue, suggestions (may be empty).
    """
    prompt = f"""Two images: (1) original shop photo of a tacked cylinder opening,
(2) the same crop with colored dots: green = OK, blue = add bend (too flat),
red = ease off (too tight). Those dots are the CV rim tracker.

Current CV settings:
{json.dumps(current_settings, indent=2)}

Allowed suggestion keys:
{json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "default"} for k, v in CALIBRATION_SPECS.items() if k not in CHECK_ROLL_LOCKED_SETTINGS}, indent=2)}

Return ONLY JSON:
{{
  "rim_ok": true/false,
  "confidence": "low" | "medium" | "high",
  "issue": "short note if dots are on glare, inner shadow, weld fixture, or wrong circle; empty if ok",
  "suggestions": {{ }}
}}

Rules:
- rim_ok true if dots follow the actual metal opening.
- If false, suggest small Canny/blur/search_band/detection tweaks to lock onto the rim.
- Do not invent radii, inches, or force %.
- Do not change curvature_tolerance.
"""

    raw_text = chat_completion(
        api_key,
        prompt,
        images=[original, overlay],
        model=model,
        max_completion_tokens=2048,
        system=(
            SYSTEM_PROMPT
            + "\nFor this task reply with a single JSON object only. No markdown fences."
        ),
    )
    try:
        data = parse_json_object(raw_text)
    except Exception:
        return {
            "rim_ok": True,
            "confidence": "low",
            "issue": "",
            "suggestions": {},
        }

    suggestions = sanitize_suggestions(data.get("suggestions"), current_settings)
    return {
        "rim_ok": bool(data.get("rim_ok", True)),
        "confidence": str(data.get("confidence") or "medium"),
        "issue": str(data.get("issue") or "").strip(),
        "suggestions": suggestions,
    }


def suggestions_to_widget_state(suggestions: dict) -> dict:
    """Map logical setting names to Streamlit widget session_state keys."""
    return {
        SETTING_WIDGET_KEYS[k]: v
        for k, v in suggestions.items()
        if k in SETTING_WIDGET_KEYS
    }


def parse_json_object(text: str) -> dict:
    """Extract a JSON object from model text (raw or fenced)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty JSON response")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("Could not parse JSON object from model response")


def check_photo_and_calibrate(
    api_key: str,
    image: Image.Image,
    current_settings: dict,
    model: str | None = None,
) -> dict:
    """Photo QA plus suggested sidebar calibration values.

    Returns a dict with quality_markdown, verdict, suggestions, reasons, notes.
    """
    prompt = f"""You are calibrating a roll-forming rim CV analyzer from one photo.

Current sidebar settings (JSON):
{json.dumps(current_settings, indent=2)}

Allowed suggestion keys and constraints:
{json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "default"} for k, v in CALIBRATION_SPECS.items()}, indent=2)}

Look at the photo (glare, blur, contrast, framing, clutter, rim visibility) and
recommend sidebar values that will likely produce a clean rim edge map.

Return ONLY a JSON object with this shape:
{{
  "verdict": "Pass" | "Caution" | "Retake",
  "ok_to_analyze": true/false,
  "quality_markdown": "short markdown: verdict, issues, what to fix, ok to analyze",
  "suggestions": {{
    "use_auto_crop": true,
    "detection_threshold": 0.25,
    "canny_low": 40,
    "canny_high": 120,
    "blur_kernel": 9,
    "num_points": 720,
    "search_band": 120,
    "max_step_change": 30,
    "window_size": 21,
    "curvature_tolerance": 3.0
  }},
  "reasons": {{
    "canny_low": "one short reason",
    "blur_kernel": "one short reason"
  }},
  "notes": "one short overall calibration tip"
}}

Rules:
- Always include every key under suggestions.
- Stay inside the allowed ranges / choices.
- Prefer small, practical tweaks over extreme values.
- If the photo is bad, still suggest best-effort settings but set Retake / Caution.
- Do not invent rim measurements or force percentages.
- Reasons only for settings you meaningfully changed vs current (others can be omitted).
"""

    raw_text = chat_completion(
        api_key,
        prompt,
        images=[image],
        model=model,
        max_completion_tokens=4096,
        system=(
            SYSTEM_PROMPT
            + "\nFor this task reply with a single JSON object only. No markdown fences."
        ),
    )

    try:
        data = parse_json_object(raw_text)
    except Exception:
        # Fallback: treat whole reply as markdown QA with unchanged settings.
        data = {
            "verdict": "Caution",
            "ok_to_analyze": True,
            "quality_markdown": raw_text,
            "suggestions": dict(current_settings),
            "reasons": {},
            "notes": "Model did not return structured JSON; settings left unchanged.",
        }

    suggestions = sanitize_suggestions(data.get("suggestions"), current_settings)
    reasons = data.get("reasons") or {}
    if not isinstance(reasons, dict):
        reasons = {}

    quality_md = data.get("quality_markdown") or ""
    if not str(quality_md).strip():
        verdict = data.get("verdict", "Caution")
        quality_md = (
            f"**Verdict:** {verdict}\n\n"
            f"**OK to analyze?** {'yes' if data.get('ok_to_analyze', True) else 'no'}\n\n"
            f"{data.get('notes') or ''}"
        ).strip()

    return {
        "verdict": data.get("verdict", "Caution"),
        "ok_to_analyze": bool(data.get("ok_to_analyze", True)),
        "quality_markdown": quality_md,
        "suggestions": suggestions,
        "reasons": {k: str(v) for k, v in reasons.items() if k in CALIBRATION_SPECS},
        "notes": str(data.get("notes") or "").strip(),
    }


def troubleshoot_failure(
    api_key: str,
    *,
    original: Image.Image,
    crop: Image.Image | None = None,
    edges: Image.Image | None = None,
    issue: str,
    settings: dict | None = None,
    model: str | None = None,
) -> str:
    images = [original]
    if crop is not None:
        images.append(crop)
    if edges is not None:
        images.append(edges)

    prompt = f"""The CV pipeline hit a problem.

Issue: {issue}

Current settings (JSON):
{json.dumps(settings or {}, indent=2)}

Images (in order): original photo, then optional analysis crop, then optional edge map.

Explain likely causes and give concrete sidebar tweaks (auto-crop, detection
threshold, Canny, blur, center X/Y, expected radius, search band). Keep it
operator-friendly. Do not invent measurement numbers."""
    return chat_completion(
        api_key,
        prompt,
        images=images,
        model=model,
        max_completion_tokens=2048,
    )


def operator_summary(
    api_key: str,
    *,
    metrics: dict,
    zone_image: Image.Image,
    original: Image.Image | None = None,
    model: str | None = None,
) -> str:
    images = [zone_image]
    if original is not None:
        images.append(original)

    prompt = f"""Write plain-language operator guidance from these CV results.

Metrics JSON (source of truth — do not change the numbers):
{json.dumps(metrics, indent=2)}

First image: correction-zone overlay (green=OK, blue=too flat / increase force,
red=too tight / decrease force). Second image if present: original photo.

Include:
1. **Overall status** (one sentence)
2. **Where to increase force** (clock positions + use provided %)
3. **Where to decrease force** (clock positions + use provided %)
4. **Priority action** (single best next step)
5. One-line reminder that % is geometry guidance, not calibrated machine control

Be concise. Do NOT include headings like "Zone second opinion" or "Shift handoff note".
Only write the operator guidance body."""
    return chat_completion(
        api_key,
        prompt,
        images=images,
        model=model,
        max_completion_tokens=4096,
    )


def zone_second_opinion(
    api_key: str,
    *,
    metrics: dict,
    zone_image: Image.Image,
    model: str | None = None,
) -> str:
    prompt = f"""Sanity-check this correction-zone overlay against the metrics.

Metrics JSON:
{json.dumps(metrics, indent=2)}

Image: zone overlay (green=OK, blue=too flat, red=too tight).

Return:
1. **Plausible?** yes / mixed / no
2. **What looks consistent**
3. **What looks suspicious** (crop, glare, rim lock onto wrong edge, etc.)
4. **Confidence** low/medium/high for trusting these zones today

Do not invent new force percentages."""
    return chat_completion(
        api_key,
        prompt,
        images=[zone_image],
        model=model,
        max_completion_tokens=4096,
    )


def shift_report(
    api_key: str,
    *,
    metrics: dict,
    operator_guidance: str | None = None,
    model: str | None = None,
) -> str:
    prompt = f"""Write a short shift handoff note for process engineers.

Metrics JSON:
{json.dumps(metrics, indent=2)}

Existing operator guidance (may be empty):
{operator_guidance or "(none)"}

Format as markdown:
- Part / opening summary
- Tolerance status
- Key force increase / decrease callouts (use provided numbers only)
- Suggested follow-up / re-measure notes
- Disclaimer: geometry-based guidance

Keep under ~200 words."""
    return chat_completion(
        api_key,
        prompt,
        images=None,
        model=model,
        max_completion_tokens=4096,
    )


def answer_question(
    api_key: str,
    question: str,
    *,
    metrics: dict | None = None,
    images: list[Image.Image] | None = None,
    history: list[dict] | None = None,
    model: str | None = None,
) -> str:
    context = json.dumps(metrics or {}, indent=2)
    prompt = f"""Answer the operator/engineer question using only the provided
metrics and images. If something is unknown, say so.

Metrics JSON:
{context}

Question: {question}"""
    return chat_completion(
        api_key,
        prompt,
        images=images,
        model=model,
        history=history,
        max_completion_tokens=4096,
    )


def build_result_metrics(
    *,
    target_radius_inches: float,
    target_radius_pixels: float,
    within_tolerance_percent: float,
    too_flat_percent: float,
    too_tight_percent: float,
    pixels_per_inch: float,
    curvature_tolerance: float,
    target_mode: str,
    max_force_increase: float,
    max_force_increase_angle: float,
    max_force_decrease: float,
    max_force_decrease_angle: float,
    rim_rmse_px: float,
) -> dict:
    """Operator-facing metrics dict for prompts (uses displayed sign convention)."""
    return {
        "target_radius_inches": round(float(target_radius_inches), 3),
        "target_radius_pixels": round(float(target_radius_pixels), 2),
        "smooth_bend_percent": round(float(within_tolerance_percent), 2),
        "within_tolerance_percent": round(float(within_tolerance_percent), 2),
        # Display convention in the dashboard: flat vs tight labels for operators.
        "too_flat_percent_display": round(float(too_tight_percent), 2),
        "too_tight_percent_display": round(float(too_flat_percent), 2),
        "pixels_per_inch": round(float(pixels_per_inch), 3),
        "curvature_tolerance_percent": float(curvature_tolerance),
        "target_mode": target_mode,
        "largest_force_increase_percent": round(float(max_force_increase), 2),
        "largest_force_increase_theta_rad": round(float(max_force_increase_angle), 4),
        "largest_force_decrease_percent": round(float(max_force_decrease), 2),
        "largest_force_decrease_theta_rad": round(float(max_force_decrease_angle), 4),
        "rim_fit_rmse_pixels": round(float(rim_rmse_px), 2),
        "angle_convention": "theta=0 at right of image; increases counterclockwise",
        "zone_colors": {
            "green": "smooth bend / within tolerance",
            "blue": "too flat — increase force",
            "red": "too tight — decrease force",
        },
    }
