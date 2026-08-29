# InterScribe

InterScribe turns interview recordings into polished, ready-to-use content. Upload an audio or video file, and it transcribes it, identifies who is speaking, pulls out the key themes and best quotes, and condenses them into short headlines — all on your own computer, with no data sent to the cloud.

---

## What it does

1. **Upload** your recording (audio or video, up to 2 GB / 3 hours)
2. **Transcribe** — InterScribe automatically transcribes the audio and separates speakers
3. **Review transcript** — correct any mis-heard words, assign names to speakers
4. **Extract themes** — the AI reads the transcript and surfaces the main topics and notable moments
5. **Review themes** — keep what's relevant, discard what isn't
6. **Extract quotes** — the AI pulls the best quotes from the transcript, grounded to the exact words spoken
7. **Review quotes** — approve or discard each quote
8. **Condense headlines** — approved quotes are condensed to ≤20 words, ready to use

Everything runs locally. No audio, transcripts, or content ever leaves your machine.

---

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — the only thing you need to install manually
- A free [HuggingFace account](https://huggingface.co/join) — setup will ask for a token once to download the speaker-identification models; it is not stored anywhere after that
- Windows 10/11, Mac (Apple Silicon or Intel), or Linux
- NVIDIA GPU strongly recommended for fast transcription (the app works without one, but transcription will be slow)

---

## Installation

### Windows

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) with WSL 2 enabled (the installer will prompt you)
2. Download and run **InterScribe-Setup.exe** from the [releases page](https://github.com/TJM-NZ/InterScribe/releases/latest)
3. The installer puts an InterScribe icon in your system tray and on your desktop
4. Double-click the tray icon (or use **Start services** from the right-click menu) to launch the app

The first launch downloads the AI models (~10 GB total). This takes 15–30 minutes depending on your internet connection and only happens once.

### Mac

1. Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Open Terminal and run:

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
./setup.sh
```

### Linux

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose)
2. Run:

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
./setup.sh
```

The script installs the NVIDIA Container Toolkit automatically if you have an NVIDIA GPU.

---

## Opening the app

Once running, open your browser and go to:

**http://localhost:3002**

---

## Windows system tray

After installation, InterScribe lives in your system tray (bottom-right of the taskbar). Right-click the icon for:

| Option | What it does |
|--------|-------------|
| Open InterScribe | Opens the app in your browser |
| Start services | Starts the Docker containers |
| Stop services | Stops everything cleanly |
| View logs | Opens a log window for troubleshooting |
| Run setup | Re-runs the initial setup (e.g. after a reinstall) |

The icon is **green** when InterScribe is running, **grey** when stopped. If a new version is available, a notification appears and an update link is added to the menu.

---

## Automation (StreamDeck and other launchers)

If you use a StreamDeck or any other launcher to start multiple apps in one go, use `start.bat` instead of calling Docker directly:

```
start.bat
```

It handles the full startup sequence safely:

- If InterScribe is already running, it skips straight to opening the browser
- Waits for Docker to be ready before doing anything (no fixed delays — loops until ready)
- Starts the containers
- Waits until the app is actually responding before opening the browser
- Exits with code `0` on success, `1` on failure — so your launcher can sequence other apps around it

Point your StreamDeck button at `start.bat` in the InterScribe folder. Safe to trigger at any time, including right after a reboot.

---

## Stopping InterScribe

**Windows:** Right-click the tray icon → Stop services.

**Mac / Linux:**

```bash
docker compose down        # stop containers, keep all your data
docker compose down -v     # stop and delete all data (cannot be undone)
```

---

## Troubleshooting

**Transcription is very slow** — InterScribe is running on CPU. Make sure your NVIDIA GPU drivers are installed and Docker Desktop has GPU access enabled (Settings → Resources → GPU).

**The app won't open** — check that Docker Desktop is running, then use Start services from the tray icon (Windows) or run `docker compose up -d` (Mac/Linux).

**View logs:**

```bash
docker compose logs -f worker     # transcription and AI jobs
docker compose logs -f backend
docker compose logs -f frontend
```

---

## First-run download sizes

| Component | Size | When |
|---|---|---|
| Qwen3.5:9b (AI model) | ~6 GB | During setup |
| WhisperX transcription model | ~3 GB | First transcription |
| Speaker diarization models | ~1 GB | First transcription |

All models are cached and do not re-download on restart.

---

<details>
<summary>Manual setup (advanced)</summary>

### HuggingFace token

Speaker identification (diarization) uses pyannote, which requires a free HuggingFace account:

1. Create an account at [huggingface.co](https://huggingface.co/join)
2. Accept the license for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Accept the license for [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
4. Generate a read token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

The token is only used once during the Docker build to download the models. It is not stored after that.

### Linux (NVIDIA GPU)

```bash
# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

# Clone and configure
git clone https://github.com/TJM-NZ/InterScribe.git && cd InterScribe
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, DATABASE_URL, INTERSCRIBE_API_KEY, and paste your HuggingFace token when prompted during build

# Start
docker compose up --build -d
docker compose exec ollama ollama pull qwen3.5:9b
```

### Mac (Apple Silicon)

```bash
# Install Ollama natively (uses Metal GPU)
brew install ollama
ollama pull qwen3.5:9b

# Clone and configure
git clone https://github.com/TJM-NZ/InterScribe.git && cd InterScribe
cp .env.example .env
# Edit .env:
#   POSTGRES_PASSWORD, DATABASE_URL, INTERSCRIBE_API_KEY
#   WHISPER_DEVICE=cpu
#   WHISPER_COMPUTE_TYPE=int8
#   WHISPER_MODEL_SIZE=small
#   OLLAMA_BASE_URL=http://host.docker.internal:11434

# Start
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build -d
```

</details>
