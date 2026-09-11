# NST Roll Forming Check System
## Engineering Handoff Documentation

### Links
- **GitHub (private):** https://github.com/Blaise-Muhune/RollFormingApp
- **Streamlit Cloud:** https://nst-check-roll.streamlit.app
- **Local / shop LAN:** run `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`, then open `http://localhost:8501` or `http://<host-ip>:8501`

Streamlit Cloud needs GitHub access to this private repo. Optional: put `OPENAI_API_KEY` in App settings → Secrets. For daily floor use, a shop PC on the LAN is the better host.

---

### What this project is

**Goal:** Help Bertsch 4-roll operators check a rolled tank opening with a phone photo before full weld. The app should say clearly if the roll looks good, and if not, what L/R move to try next.

**Day-to-day page:** Check roll  
**Advanced pages (MENU):** Inspect (CV knobs), Correct (full calculator)

**Already built**
- Job size / thickness / material inputs
- Start L/R from the shop chart (Verified) or filled-in estimates
- Photo → rim track → Smooth + Round pass/fail cards
- Fix guidance in Jog language (set L / R, or spot list)
- Bad-crop “retake” messages (so a wrong green circle is not trusted)
- Optional OpenAI assist (off by default; toggle in MENU)
- Tolerances and chart numbers kept in code for easy handoff

This document, the app itself, and `README.md` are the main handoff package.

---

### Why it was needed

Before this, the floor mostly used hanging templates and operator experience. There was no shared digital check that turned a photo into a clear pass/fail and concrete L/R moves. That made results uneven and training harder. The project had to be a real shop tool, not only a CV demo.

---

### Operator flow

1. Pick job (diameter / thickness / material)  
2. Read start L/R (Verified, Chart, or Estimate)  
3. Roll and tack  
4. Take an upright, centered photo of the opening  
5. Check roll runs (auto after photo when the job is set)  
6. **Smooth + Round look good** → send to weld (if template fits)  
7. **Not good** → set next L/R (or follow spot list) → roll again → photo again  
8. Use Inspect / Correct only when engineering needs deeper tools  

---

### What we used

**Shop gear**
- Bertsch 4-roll (L / R / B2-B4 / Drive on the HMI)
- Phone or tablet camera
- Shop PC running Streamlit (recommended)

**Software**
- This Streamlit app
- Camera vision (crop + rim track)
- Springback math for L/R when the chart does not fully match
- Handwritten Bertsch chart table in code
- Optional OpenAI (not the measurement source of truth)

---

### Pass / fail percents (simple)

After a photo, Check roll shows **two** cards:

| Card | Plain-English question |
|------|------------------------|
| **Smooth** | Is the bend consistent all the way around? (a mild oval can still pass) |
| **Round** | Is it close to a **perfect circle**? |

Same scoring rules for both.

#### In plain words
1. The app looks at many points around the rim.  
2. Each point is **OK**, **too flat**, or **too tight**.  
3. **±2%** is the OK band (`SPOT_TOLERANCE_PCT`). Inside that band = green / OK.  
4. **“95% smooth”** (or “% within circle”) means: 95% of those points were OK.  
5. **“Worst spot 2%”** means: the single worst point was 2% off.  

**Pass (Smooth or Round)** needs both:
- At least **95%** of the rim OK, and  
- Worst spot no worse than **2%**

So these percents are not “weld quality.” They mean: *how much of the rim stays close to the target shape, and how bad the worst bump is.*

#### Where to edit (shop knobs)
**File:** `operator_display.py` (top of the file)

| Name in code | Current | Easy meaning |
|--------------|---------|--------------|
| `SPOT_TOLERANCE_PCT` | **2.0** | How far off a spot can be and still count as OK (±2%) |
| `SMOOTH_PASS_MIN_PCT` | **95.0** | How much of the rim must be OK to pass |
| `SMOOTH_BORDERLINE_MIN_PCT` | **75.0** | Lower bar for “Mostly smooth / Mostly round” |
| `BORDERLINE_WORST_MAX_PCT` | **2.0** | Worst-spot limit for that “mostly” case |
| `WORST_SPOT_VISUAL_MIN_PCT` | **3.0** | Old photo-pin setting (not the main pass rule now) |

Check roll also uses the 2% value as `curvature_tolerance` in `pipeline.py`. Do not let OpenAI or Inspect permanently loosen floor pass/fail without shop agreement.

Inspect (`pages/1_Inspect.py`) can change tolerance live for tests. That does **not** change Check roll until you edit `operator_display.py`.

---

### Verified vs unverified start L/R (simple)

When you pick a job, the app shows start **L** and **R** (mm) for the Bertsch Jog screen. The badge tells you how trustworthy that number is.

| Badge | Trust level | Plain meaning |
|-------|-------------|---------------|
| **Verified** | Highest | Exact match to a handwritten shop chart line (size + thickness + material) |
| **Chart** | Medium | No exact line, so we **fill the blank** from nearby chart sizes |
| **Estimate** | Lowest | Chart could not fill it, so we use the springback **calculator** (often nudged toward the nearest chart size) |

#### Verified
Only when diameter, thickness, **and** material all match a chart row that lists those fields.

Examples:
- 36" · 3/16" · Carbon Steel → L **123** / R **75**
- 36" · 5/16" · 304 Stainless → L **135** / R **74**

Some chart rows only have a diameter (28", 30", 42"…). Those are real shop numbers in the table, but the badge is still **not** Verified unless thickness and material match too.

#### Chart (filling blanks)
If there is no Verified hit, the app guesses L/R from nearby confirmed sizes:

1. Prefer other rows with the **same thickness** (if there are at least two).  
2. Otherwise use the general size-only list.  
3. **Blend** between the two nearest sizes.

Easy example: job is **48"**. Chart has 46" (L 137 / R 95) and 54" (L 145 / R 100).  
48" is one quarter of the way from 46 to 54, so:

- L ≈ 139  
- R ≈ 96  

If the size is outside the table, it stretches a bit from the end. If only one nearby size exists, it copies that size.

#### Estimate (calculator)
Last resort:
1. Run the springback calculator for your job.  
2. Run it again at the nearest chart size.  
3. Shift your answer so it lines up with that chart size.  

**Chart** and **Estimate** are both “unverified.” Prefer Verified when the floor has confirmed a full line. Add new confirmed lines in `shop_recipes.py`.

**Code:** chart table = `shop_recipes.py`; badge ladder = `bertsch_chart.py` (`resolve_start_lr`).

General size-only diameters in the table today include: 28, 30, 36, 42, 46, 54, 60, 72, 84 (plus some thickness-specific rows at 36 and 70).

---

### Lessons learned
- A good photo beats a smarter model. Upright, centered, opening fills the frame.  
- Smooth tracking can hide sharp dents if it smooths too hard.  
- Never show a fake green “pass” on a bad crop. Fail loud and ask for a retake.  
- Pass/fail numbers are shop rules. Keep them in `operator_display.py`.  
- Keep Check roll fast. Put OpenAI and deep knobs in MENU / Inspect.  
- Short shop language (Smooth, Round, Ease off, set L/R) works better than equation dumps.

---

### Still to do
- Tune on more real shop photos (pass, fail, dent, glare)  
- Better dent catch without making checks noisy or slow  
- More full chart lines so more jobs get **Verified**  
- Always-on shop PC deploy (weights cached, offline-friendly)  
- Short floor card: photo rules + what Smooth / Round / Verified mean  
- Optional later: train a detector on NST photos only  

---

### Future ideas
- Log photo + job + L/R + next check outcome  
- On-screen framing guide before Check runs  
- Stronger Bertsch link if IT allows  
- Related checks after this one is trusted on the floor  

---

### Handoff notes
1. Open the links above.  
2. Read `README.md` and run the app.  
3. Try one known-good photo and one known-fail photo on Check roll.  

Reminders:
- Confirm diameter / thickness / material before trusting start L/R.  
- The photo check is a coach, not locked machine control.  
- Change pass/fail only in `operator_display.py` with shop agreement.  
- Prefer classical CV over OpenAI for the rim measurement.  
- Never commit API keys (`.env` / Streamlit secrets only).

**Useful files**
- `app.py` — Check roll screen  
- `pipeline.py` — photo check pipeline  
- `operator_display.py` — pass/fail % and cards  
- `shop_recipes.py` — handwritten chart numbers  
- `bertsch_chart.py` — Verified / Chart / Estimate logic  
- `pages/1_Inspect.py` — CV tuning  
- `pages/2_Correct.py` — full calculator  
- `cv/correction.py` — how the % error is computed  
- `cv/` — crop, rim track, optional AI assist  

---

### Status

**Done**
- Check roll / Inspect / Correct app  
- NST shop UI  
- Rim check with retake fail-safes  
- Smooth + Round cards (currently ±2% band, 95% pass)  
- Chart + calculator start L/R  
- This handoff + README  

**Open**
- More shop photo validation  
- Floor training card  
- Stronger always-on hosting  
- More Verified chart rows  
- Plant IT decision for permanent floor deploy  
