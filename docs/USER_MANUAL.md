# PULSEGUARD — User Manual

### How to Run Your Webpage (Windows, Beginner-Friendly)

This manual explains **everything you need to do** to run the PulseGuard machine
health monitoring system on your Windows laptop — from a cold start to a live
demo. No prior setup knowledge assumed.

---

## 1. What PulseGuard Is (30-second recap)

```
ESP32 + sensors  →  Firebase  →  Flask API  →  ML model  →  Web Dashboard
 (your machine)     (cloud)     (port 5000)              (port 8000)
```

The ESP32 pushes temperature + vibration readings to Firebase every ~5 seconds.
The Flask API watches Firebase, runs the machine-learning model on each new
reading, saves the result (NORMAL / WARNING / CRITICAL), and the webpage shows
everything live.

---

## 2. One-Time Setup (already done — check only)

You only ever need to do this section **once**. Everything below is already
configured on your laptop; this is here in case you move to a new computer.

| Check | How | Status |
|---|---|---|
| Python installed | open Command Prompt, type `python --version` | ✅ Done (3.10) |
| Packages installed | `pip install -r requirements.txt` from the `PulseGuard\PulseGuard` folder | ✅ Done |
| Email credentials | file `flask_api\.env` has real `MAIL_PASSWORD` | ✅ Done |
| `.env` file exists | `flask_api\.env` (copied from `.env.example`) | ✅ Done |

> The `.env` file holds your email password. **Never upload it to GitHub** —
> the project's `.gitignore` already blocks it.

---

## 3. Daily Start — 3 Steps

### Step 1 — Start the Flask API (the "brain")

1. Open **File Explorer** → go to
   `C:\Users\msmoo\Desktop\PulseGuard\PulseGuard\flask_api`
2. Click the address bar, type `cmd` and press **Enter**
   (a black window opens in that folder)
3. Type:

```cmd
python app.py
```

4. Wait until you see:

```
INFO:__main__:Starting PulseGuard API on 127.0.0.1:5000
 * Running on http://127.0.0.1:5000
```

✅ **Keep this window open.** Closing it stops the system.
This window also shows a live log every time a reading is predicted —
great for the demo.

### Step 2 — Start the webpage server

1. Open a **second** Command Prompt the same way, but in the `web` folder:
   `C:\Users\msmoo\Desktop\PulseGuard\PulseGuard\web`
2. Type:

```cmd
python -m http.server 8000
```

3. Wait until you see:

```
Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ...
```

✅ **Keep this window open too.**

### Step 3 — Open the webpage

In Chrome/Edge, open:

> **http://localhost:8000**

Press **Ctrl + Shift + R** once (hard refresh) so the browser loads the
latest dashboard code.

**You're done.** The dashboard updates itself every 5 seconds.

---

## 4. Shortcut — One Double-Click

Instead of Steps 1–2, double-click:

```
C:\Users\msmoo\Desktop\PulseGuard\PulseGuard\run_pulseguard.bat
```

It opens both windows for you automatically. You still open the browser
yourself (Step 3).

---

## 5. Reading the Dashboard

| Element | Meaning |
|---|---|
| **LIVE** (pulsing dot, top-right) | New sensor data arrived in the last 30 s — data is flowing |
| **DATA 4m OLD** (amber dot) | API works, but the ESP32 stopped sending — check the device / Wi-Fi |
| **OFFLINE** (dim dot) | Flask API isn't running — redo Step 1 |
| **TEMP / VIB readouts** | Latest values, updated every ~5 s |
| **MACHINE STATE badge** | Model's verdict: NORMAL (green) / WARNING (amber) / CRITICAL (red, blinking) |
| **Historical Trends** | Live charts of the last readings |
| **Recent Readings table** | Newest 20 readings with their status |

**Turning the ESP32 on/off:** power it on → within ~10 s the dot turns green
LIVE. Power it off → after 30 s it turns amber with the data age. That's
expected behaviour, not a fault.

### 5b. The Other Pages (Login, Admin, Technical)

| Page | URL | Who uses it |
|---|---|---|
| Public live monitor | http://localhost:8000 | Everyone (demo hero page) |
| Login | http://localhost:8000/login.html | Admin + Technical Team |
| Owner dashboard | http://localhost:8000/admin/ | Admin/Owner — one big answer: MACHINE NORMAL / ATTENTION / PROBLEM, plus service requests & history |
| Technical dashboard | http://localhost:8000/technical/ | Technical Team — machine registration, live detail, RAW/CLEAN Excel, service queue, maintenance reports, PDF/Excel reports |

**Login setup (one time):**
1. Firebase Console → Authentication → Sign-in method → enable **Email/Password**
2. Authentication → Users → **Add user** (e.g. `admin@123gmail.com` + a password)
3. Get the **Web API key**: Project settings (gear) → General → Web API key
4. Put it in `flask_api\.env` as `FIREBASE_WEB_API_KEY=...` and restart Flask
5. List admin emails in `.env` as `ADMIN_EMAILS=admin@123gmail.com`
   (everyone else becomes Technical Team on first login)

### 5c. Set Up Your Mails (Admin dashboard - no .env editing needed)

On the Admin dashboard there is a **"Set Up Your Mails"** panel. Fill in:

| Field | What it is |
|---|---|
| Gmail / Sender Account | the Gmail that SENDS the alerts |
| App Password | 16-character Google App Password (not the normal password) |
| Your Email (Owner) | where YOU receive critical alerts + service updates |
| Technical Team Email | where the team receives critical alerts |
| SMTP Server / Port | leave as `smtp.gmail.com` / `587` for Gmail |

Click **Save Settings** (applies immediately, no restart), then
**Verify Connection** (checks the login) or **Send Test Email** (real
email to your inbox). The saved settings override `flask_api\.env` -
you never have to edit that file by hand. The password is stored
write-only: nobody can view it back through the app.

**Service workflow on the dashboards:**
Owner sees a problem → admin dashboard → *Request Service* →
technical dashboard → **Accept** (owner gets an email) → **Visited /
In Progress / Fixed** → file the **Maintenance Report** → request shows
COMPLETED for both.

---

## 6. Stopping Everything

- Click each black window, press **Ctrl + C** (or just close the windows)
- Refreshing the webpage afterwards will show **OFFLINE** — that's normal

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Page shows **OFFLINE** | Flask window is closed or shows an error. Rerun Step 1. |
| `Address already in use` (port 5000) | Flask is already running somewhere — close the old window, or run `taskkill /IM python.exe /F` and start again |
| Page shows **NO DATA** | ESP32 is off or Wi-Fi is down. Power the ESP32 and check the hotspot `OPPO A38` is on |
| Dot says **DATA … OLD** | Device stopped sending recently — same fix as above |
| Values never change | Hard-refresh the browser (Ctrl + Shift + R); confirm the Flask window shows `NEW READING DETECTED` lines |
| `ModuleNotFoundError: flask` | Run: `pip install -r requirements.txt` in the `PulseGuard\PulseGuard` folder |
| Emails not arriving | CRITICAL alerts only, max 1 per hour (cooldown). Check `MAIL_PASSWORD` in `flask_api\.env` |
| Two black windows flash and vanish | Run the commands from Section 3 manually — the error text will stay visible |

---

## 8. Retrain the Model with Live Data

After recording new sessions (e.g. the motor-heating run already in Firebase):

```cmd
cd C:\Users\msmoo\Desktop\PulseGuard\PulseGuard\ml
python retrain_from_firebase.py
```

Then **restart the Flask API** (close its window, rerun Step 1) so it loads
the new model.

> Honest note: labels are rule-generated, so accuracy means "learned the
> thresholds well", not real-world failure prediction.

---

## 9. Demo Day Cheat-Sheet

**30 minutes before:**
1. Turn on the motor + ESP32, confirm the dot turns 🟢 LIVE
2. Start Flask (Step 1) — watch one `Predicted condition: NORMAL` line appear
3. Start the webpage server (Step 2), open the page, Ctrl + Shift + R

**Show the audience:**
- The dashboard updating by itself (no refresh needed)
- The Flask window logging every prediction live
- Firebase console (`pulseguard-7ae33`) → `readings_only` and `prediction`
  nodes filling up in real time
- Touch the motor/sensor → vibration spikes → WARNING/CRITICAL appears

**If something breaks mid-demo:** the page keeps the last values and the dot
turns amber — narrate it as the data-freshness indicator doing its job.

---

*PulseGuard — Machine Health Monitoring | College Project*
