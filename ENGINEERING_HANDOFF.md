# NST Roll Forming Check System
## Engineering Handoff Documentation

### Links
- **GitHub (private):** https://github.com/Blaise-Muhune/RollFormingApp
- **Streamlit Cloud:** https://nst-check-roll.streamlit.app
- **Local / shop LAN:** `streamlit run app.py --server.address 0.0.0.0 --server.port 8501` then open `http://localhost:8501` or `http://<host-ip>:8501`

*Streamlit Cloud needs GitHub OAuth access to this private repo, and optional `OPENAI_API_KEY` in App settings → Secrets. Shop LAN host is preferred for production floor use.*

### Project Overview

#### Objective
Design, implement, document, and validate a shop-floor software workstation that helps Bertsch 4-roll operators verify rolled tank openings before full weld. The system should cut reliance on individual eye judgment, shorten training time for new operators, and improve consistency of L/R guidance and pass/fail decisions from a phone photo.

#### Completed
- Streamlit shop-floor app (Check roll, Inspect, Correct)
- Niles Steel Tank branded operator UI (Check roll first, advanced pages in MENU)
- Job inputs tied to shop hanging-template sizes / Bertsch chart start L/R
- Photo check pipeline: detect/crop opening, track rim, pass/fail, worst-spot overlay
- Correction guidance in Jog language (next L / R, or section list when spots conflict)
- Rim seed path (SAM with GrabCut / ellipse fallback) and crop fail-safes
- Optional OpenAI rim assist (off by default for speed; toggle in MENU)
- Local run path and Streamlit Cloud deploy path for the private GitHub repo
- Operator-facing tolerances centralized in code (`operator_display.py`)

*This handoff document, the in-app Check roll / Correct flow, and the repository README are the primary knowledge-transfer resources for future operators and engineers.*

---

### Problem Statement
Prior to this project, roll quality before weld relied heavily on hanging templates and individual operator experience on the Bertsch 4-roll. There was no shared digital check that turned a photo of the opening into a clear Ready / Not ready decision and concrete L/R moves. Variability in judgment, longer rework loops, and limited transfer of “what good looks like” made onboarding harder. Building a usable tool required more than CV demos: a production-minded operator UI, chart-aware start setpoints, springback-aware L/R guidance, fail-loud photo handling so bad crops do not look like green passes, and enough documentation for engineers to continue the work.

---

### Solution Overview
The project established a repeatable production workflow:

Operator  
↓  
Select job (diameter / thickness / material)  
↓  
Read start L/R (Verified chart or Estimate)  
↓  
Roll and tack  
↓  
Photo of opening (upright, centered, rim fills frame)  
↓  
Check roll  
↓  
Ready → send to weld  
or  
Not ready → set next L/R (or follow section list) → roll again → re-check  
↓  
Inspect / Correct only when engineering needs deeper CV or calculator work  
↓  
Documentation / handoff

This workflow is supported by the Check roll page for daily use, Inspect for CV tuning, Correct for starting and adjustment calculator detail, and optional OpenAI assist when a difficult photo needs help.

---

### Scope of Work

#### Hardware (shop context)
- Bertsch 4-roll plate roll (shop HMI: L Axis, R Axis, B2/B4, Drive)
- Operator phone or tablet camera (same LAN or deploy target as the app PC)
- Shop PC or host machine running Streamlit (recommended for floor use)

#### Software
- RollFormingApp (Python / Streamlit)
- Computer vision stack: GroundingDINO crop, rim tracker, optional SAM / GrabCut seed
- Springback / geometry solvers for loaded radius and L/R
- Bertsch chart recipes for Verified start setpoints
- Optional OpenAI API for photo QA / rim calibration (not the measurement source of truth)
- GitHub private repo; local LAN or Streamlit Community Cloud hosting

#### Manufacturing Focus
- Pre-weld check of rolled / tacked tank openings on the Bertsch line
- Pass/fail against smooth-bend tolerances
- Operator guidance for L/R corrections when the opening is not Ready

---

### Major Accomplishments
1. Operator Check roll flow: job → photo → Ready / Not ready + L/R coaching
2. Unified app with Inspect (full CV) and Correct (calculator) behind MENU
3. Chart-aware start L/R with Verified vs Estimate labeling
4. Rim detection pipeline with seed refine and retake messaging for bad crops
5. Worst-spot visual overlay and shop-language fix cards
6. Performance controls: OpenAI off by default, schedule skipped on Ready, crop caching
7. Branding and layout aimed at floor use (not an engineering dashboard as the home screen)

---

### Lessons Learned
- Photo quality dominates CV quality. Upright, centered openings that fill the frame beat clever model tweaks.
- Smooth trackers can bridge sharp dents. Higher sample density and less smoothing help, with a noise tradeoff.
- Fail loud beats a pretty green circle on a wrong crop. Operators will trust the overlay.
- Pass/fail rules must stay locked shop values, not something an AI assist can loosen.
- Keep daily Check roll fast. Optional OpenAI and advanced knobs belong in MENU / Inspect.
- Visual, short operator language (Ready, Ease off, Add bend, set L/R) transfers better than equation dumps.

---

### Remaining Work

#### Technical
- Tune Check roll CV defaults against a larger set of real shop photos (pass, fail, dent, glare).
- Improve dent following without making checks too slow or noisy.
- Reduce false retake / crop failures on legitimate tight close-ups while still blocking floor/rack misfits.
- Expand and verify chart coverage so fewer jobs fall to Estimate-only start L/R.
- Harden deploy for shop LAN (always-on host, model weight caching, offline-friendly path).
- Collect labeled shop images for future fine-tuning of detection / rim models on NST lighting and openings.

#### Training
- Short floor card: how to take the photo and what Ready / Not ready means
- Walk-through for Verified vs Estimate start numbers
- When to use Inspect vs staying on Check roll
- When (if ever) to enable OpenAI improve-rim on the floor

---

### Suggested Future Projects
- Closed-loop logging: photo + job + L/R set + next check outcome for continuous improvement
- Guided capture UI (framing guides / upright prompts) before Check runs
- Shop-specific fine-tuned opening detector trained on NST photos
- Deeper Bertsch integration (readback or recipe push) if controls and IT allow
- Extension toward related forming or weld-prep checks once Check roll is trusted on the floor

---

### Handoff Notes
Start with the links above, then review `README.md`, run the app locally, and walk Check roll with a known good shop photo and a known fail photo.

Always verify job diameter, thickness, and material before trusting start L/R. Treat photo guidance as a coach, not calibrated machine control. Do not loosen pass/fail tolerances in `operator_display.py` without shop agreement. Prefer classical CV measurement over OpenAI for rim geometry. Keep API keys in `.env` / Streamlit secrets and never commit them.

Key code anchors:
- `app.py` : Check roll UI
- `pipeline.py` : end-to-end photo check
- `operator_display.py` : tolerances, overlays, Ready rules
- `pages/1_Inspect.py` : CV knobs
- `pages/2_Correct.py` : L/R calculator
- `bertsch_chart.py` : Verified chart recipes
- `cv/` : detection, rim track, seed, optional OpenAI assist

---

### Project Status

#### Completed
- Core Check roll / Inspect / Correct application
- Operator UI and NST branding for daily check use
- Rim pipeline with fail-safes and optional AI assist
- Chart + springback start / correction path
- Local and Cloud run documentation
- Knowledge transfer via this handoff and the repo README

#### Remaining
- Broader shop photo validation and default tuning
- Floor training materials and photo SOP
- Reliability and speed hardening for always-on shop use
- Optional future model training on NST-specific imagery
- Any plant IT / hosting decisions for permanent floor deployment
