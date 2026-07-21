# InterScribe

AI-powered audio/video editor for interview workflows. Upload a recording, get a diarized transcript, review narrative clusters, extract and edit quotes, and condense headlines — all running locally.

**Pipeline:**
1. Upload audio/video → WhisperX transcribes + diarizes speakers
2. Review transcript, fix low-confidence words, assign speaker roles
3. Qwen3.5:9b extracts narrative themes and notable moments
4. Review and rank themes; Qwen extracts candidate quotes grounded to transcript segments
5. Review quotes; Qwen condenses approved headlines to ≤20 words

Everything runs on your own hardware. No cloud APIs required after setup.

---

## Platform Support

| Platform | Transcription (WhisperX) | LLM (Qwen / Ollama) | Notes |
|---|---|---|---|
| Linux + NVIDIA GPU | GPU (fast) | GPU in Docker | Recommended |
| Windows + NVIDIA GPU | GPU (fast) | GPU in Docker (via WSL2) | See Windows setup below |
| Mac (Apple Silicon) | CPU in Docker (slow) | Metal GPU, run natively | See Mac setup below |

---

## Prerequisites (all platforms)

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or Docker Engine + Compose (Linux)
- A [HuggingFace](https://huggingface.co) account and access token — required for pyannote speaker diarization models

---

## HuggingFace Setup

1. Create a [HuggingFace account](https://huggingface.co/join) if you don't have one
2. Accept the license for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Accept the license for [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
4. Generate an access token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (read access is sufficient)

---

## Linux Setup (NVIDIA GPU)

**1. Install NVIDIA Container Toolkit**

If you haven't already set up GPU access for Docker:

```bash
# Add NVIDIA package repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker to use the NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify:

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

You should see your GPU listed. If this fails, check that `nvidia-smi` works on the host first.

**2. Clone and configure**

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
cp .env.example .env
```

Edit `.env` and set:

```
POSTGRES_PASSWORD=yourpassword
DATABASE_URL=postgresql://interscribe:yourpassword@postgres:5432/interscribe
HUGGINGFACE_TOKEN=hf_your_token_here
```

**3. Start**

```bash
docker compose up --build -d
docker compose exec ollama ollama pull qwen3.5:9b   # first run only — ~6 GB
```

---

## Windows Setup (NVIDIA GPU)

Docker on Windows uses a WSL2 backend, and NVIDIA GPU passthrough works through WSL2.

**1. Install prerequisites**

- Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) and enable the WSL2 backend during setup
- Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) if not already installed: open PowerShell as Administrator and run `wsl --install`
- Install the [NVIDIA drivers for Windows](https://www.nvidia.com/Download/index.aspx) (do this on Windows, not inside WSL)

**2. Install NVIDIA Container Toolkit inside WSL2**

Open your WSL2 terminal (e.g. Ubuntu from the Start menu) and run:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
```

Then restart Docker Desktop.

Verify inside WSL2:

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

**3. Clone and configure (inside WSL2)**

Run all the following commands in your WSL2 terminal:

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
cp .env.example .env
```

Edit `.env` and set:

```
POSTGRES_PASSWORD=yourpassword
DATABASE_URL=postgresql://interscribe:yourpassword@postgres:5432/interscribe
HUGGINGFACE_TOKEN=hf_your_token_here
```

**4. Start**

```bash
docker compose up --build -d
docker compose exec ollama ollama pull qwen3.5:9b   # first run only — ~6 GB
```

Access the app at http://localhost:3002 in your Windows browser.

---

## Mac Setup (Apple Silicon)

Docker on Mac runs in a Linux VM and cannot access the Apple GPU. The workaround:

- **Ollama** runs natively on Mac and uses the Metal GPU — fast LLM inference
- **WhisperX** runs inside Docker on CPU — slower than GPU, but functional

For a short interview (under 30 minutes), expect transcription to take a few minutes with the `small` model. For longer recordings, consider running overnight.

**1. Install Ollama natively**

```bash
brew install ollama
```

Or download the app from [ollama.com](https://ollama.com).

Start Ollama and pull the model (~6 GB):

```bash
ollama serve &   # skip this if you installed the Ollama app (it runs automatically)
ollama pull qwen3.5:9b
```

Ollama must be running before you start the Docker stack.

**2. Install Docker Desktop**

Download and install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/). Make sure it's running.

**3. Clone and configure**

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
cp .env.example .env
```

Edit `.env` and set these values (the CPU/model changes are important on Mac):

```
POSTGRES_PASSWORD=yourpassword
DATABASE_URL=postgresql://interscribe:yourpassword@postgres:5432/interscribe
HUGGINGFACE_TOKEN=hf_your_token_here

WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_MODEL_SIZE=small

OLLAMA_BASE_URL=http://host.docker.internal:11434
```

**4. Start**

Use the Mac-specific Compose override, which removes the Ollama container (since Ollama runs natively) and the NVIDIA GPU requirements from the worker:

```bash
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build -d
```

WhisperX downloads the `small` model (~500 MB) and pyannote diarization models (~1 GB) on first use. These are cached in Docker volumes.

Once everything is up:

- **Frontend:** http://localhost:3002
- **Backend API:** http://localhost:8002
- **API docs:** http://localhost:8002/docs

---

## First-Run Download Sizes

| Component | Size | When |
|---|---|---|
| Qwen3.5:9b (Ollama model) | ~6 GB | Pulled manually before first job |
| WhisperX `large-v2` (Linux/Windows) | ~3 GB | Downloaded on first transcription job |
| WhisperX `small` (Mac) | ~500 MB | Downloaded on first transcription job |
| pyannote diarization models | ~1 GB | Downloaded on first transcription job |

All models are cached in Docker volumes (or Ollama's local store on Mac) and don't re-download on restart.

---

## Usage

Once the app is running at http://localhost:3002:

1. Upload an audio or video file (up to 2 GB / 3 hours)
2. The worker transcribes it in the background — progress shown in the UI
3. **Gate 1:** Review the transcript, correct low-confidence words (highlighted in amber), and assign speaker roles (interviewer / interviewee)
4. **Gate 2:** Review narrative themes and notable moments extracted by Qwen; reject any that don't fit
5. **Gate 3:** Review extracted quotes grounded to the transcript; approve or discard
6. **Gate 4:** Edit Qwen-condensed headlines (≤20 words) for approved headline-type quotes

---

## Usage

1. Open http://localhost:3002 and upload an audio or video file (up to 2 GB / 3 hours)
2. The worker transcribes it in the background — progress shown in the UI
3. **Gate 1:** Review the transcript, correct low-confidence words (highlighted in amber), and assign speaker roles (interviewer / interviewee)
4. **Gate 2:** Review narrative themes and notable moments extracted by Qwen; reject any that don't fit
5. **Gate 3:** Review extracted quotes grounded to the transcript; approve or discard
6. **Gate 4:** Edit Qwen-condensed headlines (≤20 words) for approved headline-type quotes

---

## Logs

```bash
docker compose logs -f worker    # transcription + LLM jobs
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Stopping

```bash
docker compose down              # stop containers, keep volumes (data preserved)
docker compose down -v           # stop and delete all data
```
