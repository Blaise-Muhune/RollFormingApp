# Roll Forming App (Check roll)

Streamlit shop-floor app for Bertsch 4-roll: **Check roll** → start L/R → photo → pass/fail + correction guidance.

## Run locally

```powershell
cd C:\Users\blais\Desktop\LETMECOOK\RollFormingApp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Or: `.\run.ps1`

OpenAI (optional rim assist): copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

Test photos go in `uploads/` (not committed to git).

## Pages

| Page | Role |
|------|------|
| `app.py` | **Check roll** — job + photo → Ready / Not ready + L/R |
| `pages/1_Inspect.py` | Full CV tuning |
| `pages/2_Correct.py` | Full springback calculator |

## Deploy (summary)

| Option | Best for | Notes |
|--------|----------|--------|
| **Shop PC on LAN** | Production floor | Recommended. Same machine or a small tower on the network; first CV run downloads ~1GB model weights. |
| **Streamlit Community Cloud** | Demo / remote trial | Free tier may struggle with PyTorch + transformers RAM; set secrets for `OPENAI_API_KEY`. |
| **Docker on VPS** (Railway, Fly, Azure VM) | Remote access | Use 4GB+ RAM; build once, pin torch CPU wheels. |
| **Windows service / Task Scheduler** | Always-on LAN | Run `streamlit run app.py --server.port 8501 --server.address 0.0.0.0` at login. |

See [Deploy](#deploy-details) below for setup steps.

## Notes

- Guidance tool only — not calibrated machine control.
- First photo check with auto-crop downloads GroundingDINO weights (one-time, ~30s+ on CPU).

---

## Deploy details

### A. Shop LAN (recommended)

1. Install Python 3.10+ on a PC the floor can reach.
2. Clone repo, `pip install -r requirements.txt`.
3. Copy `.env.example` → `.env` if using OpenAI.
4. Run:

```powershell
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

5. Operators open `http://<that-pc-ip>:8501` on phone or tablet (same Wi‑Fi/VLAN).

### B. Streamlit Community Cloud

1. Push repo to GitHub (private or public).
2. [share.streamlit.io](https://share.streamlit.io) → New app → pick repo, main file `app.py`.
3. Advanced settings → Secrets:

```toml
OPENAI_API_KEY = "sk-..."
```

4. Expect cold starts and possible memory limits with torch; disable OpenAI auto-crop on free tier if builds fail.

### C. Docker (VPS / Railway)

Example start command after `pip install`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
```

Use at least **4 GB RAM**. Mount `.env` or inject env vars at runtime — never bake API keys into the image.

