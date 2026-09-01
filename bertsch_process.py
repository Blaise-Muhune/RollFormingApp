"""Bertsch 4-roll double-pinch process and HMI mapping.

Grounded in:
- Bertsch four-roll operator/owner manual (production rolling, pinch, tilt, hinge)
- MegaFab / Piranha-Bertsch 4-roll double-pinch description (plate stays pinched;
  rotation encoder = how much plate was fed)
- This shop's HMI photo: L/R Axis + tilt, B2/B4, Drive Roll D Axis, LEFT/BOTTOM/RIGHT
  rockers, MAIN DRIVE

On the photographed screen, the large L/R/B numbers match millimetres and the
smaller numbers match inches (e.g. 213.5 mm ≈ 8.41 in). Use INCH/METRIC MODE
or read the small inch values when comparing to this app.
"""

BERTSCH_STEPS = [
    {
        "id": "load",
        "title": "1. Square, pinch, and park at the pinch point",
        "do": (
            "Top roll stays fixed. Jog BOTTOM (B2/B4) open enough for the plate, hoist it in, "
            "and square the leading edge (against the far side roll if there is no squaring arm). "
            "Pinch between top and bottom — never closer than plate thickness. "
            "Drop the far side roll off the plate, put MAIN DRIVE in reverse, and bring the "
            "leading edge back to the pinch point. Keep the drop-end hinge UP while rolling."
        ),
        "watch": (
            "MAIN DRIVE must be in neutral to jog LEFT / RIGHT / BOTTOM — the lower-roll "
            "hydraulics do not move while the drive is running."
        ),
    },
    {
        "id": "first_curve",
        "title": "2. Pre-bend the leading edge, then check the template",
        "do": (
            "Raise the entry side roll (LEFT or RIGHT, whichever the plate entered) to a radius "
            "slightly larger than the job. MAIN DRIVE forward at least as far as the bottom-roll "
            "to side-roll contact. Stop. Check the curve on the hanging template for this size "
            "(same number you picked above). If it is wrong, neutral the drive, jog the side roll, "
            "reverse back to the pinch, and take another short pre-bend — do not roll past the "
            "first-pass mark or you will make a tight spot."
        ),
        "watch": "Do not try to hit finished diameter on the first pass. Bertsch: first pass slightly oversized, then close in later passes.",
    },
    {
        "id": "sixty",
        "title": "3. Closing pass — about 60%, then support",
        "do": (
            "Drop the entry side roll fully off the plate. Raise the far side roll onto the "
            "pre-bent edge. MAIN DRIVE forward so the plate feeds through the pinch and over "
            "the far side roll. At about 60% formed, put the chain hoist (and OVERHEAD SUPPORT "
            "if used) on so the front cannot drop. Watch D Axis — that is plate feed, not radius."
        ),
        "watch": "Support before the overhang gets heavy. Trailing edge will pre-bend as it enters the pinch (short flat ≈ 1–1½ × thickness).",
    },
    {
        "id": "close",
        "title": "4. Close, check template, tack",
        "do": (
            "Keep MAIN DRIVE until the ends meet, then a little more. Template-check again. "
            "If still large, reverse, raise the forming side roll a little, and take another pass. "
            "Align the seam and tack-weld. For a true cylinder keep L/R tilt near zero and B2≈B4 "
            "(LEVEL AXIS). Tilt is for cones, not round shells."
        ),
        "watch": "Do not overlap the butt joint in the pinch. Keep the hoist on until tacks hold the roll.",
    },
    {
        "id": "remove",
        "title": "5. Unload and inspect",
        "do": (
            "Release pinch pressure first, then drop the hinge (key OPEN / hinge) and hoist the "
            "cylinder out. Inspect. If it fails, return to the Bertsch and use the photo check "
            "for where L Axis vs R Axis needs to add bend or ease off."
        ),
        "watch": "The hinge will not drop if pinch is still loaded. E-stop cuts power and the pump.",
    },
]
