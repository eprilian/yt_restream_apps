# 🎥 YouTube 24/7 Restream App

This is a **self-hosted web application** that streams a YouTube video or playlist **24/7** to a local HLS stream.  
It includes a clean **web UI** with a `video.js` player and controls to skip videos, rewind, and adjust playback.

---

## 🚀 Features

- 🔁 **24/7 Streaming:** Loops a YouTube playlist or single video indefinitely.  
- 🖥️ **Web UI:** Clean, responsive interface using `video.js`.  
- ⏭️ **Playlist Control:** “Next” and “Previous” buttons to skip through videos.   
- ⚙️ **Configurable:** Change YouTube URL, quality, and port easily.

---

## 🧱 Tech Stack

| Component | Technology |
|------------|-------------|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) |
| **Server** | [Uvicorn](https://www.uvicorn.org/) |
| **Streaming Engine** | [FFmpeg](https://ffmpeg.org/) |
| **YouTube Downloader** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| **Frontend** | HTML, CSS, JavaScript |
| **Player** | [Video.js](https://videojs.com/) |

---

## 📂 Project Structure

```
/youtube_restream/
├── app.py              # FastAPI web server and REST API
├── stream_manager.py   # Stream manager (handles ffmpeg + yt-dlp)
├── config.py           # User configuration (URL, Port, Quality)
├── requirements.txt    # Python dependencies
├── README.md           # You are here
├── .gitignore          # Ignore cache, temp, and HLS output files
└── /static/
    ├── index.html      # Web interface
    ├── style.css       # Styling
    └── script.js       # Frontend logic
```

---

## ⚙️ Setup & Installation

### 1️⃣ Prerequisites

Ensure **FFmpeg** is installed and available in your system's PATH.

#### 🐧 Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

#### 🏹 Arch Linux
```bash
sudo pacman -S ffmpeg
```

#### 🪟 Windows
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to your **PATH**.

---

### 2️⃣ Install Python Dependencies

Clone the repository (or download the project) and install requirements:

```bash
pip install -r requirements.txt
```

---

## 🧰 How to Use

### 1. Configure the Stream

Open the file `config.py` and edit your settings:

```python
# config.py

# Paste the full YouTube video or playlist URL you want to restream.
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# The port your web server will run on.
PORT = 8081

# Choose from: "1080p", "720p", "480p", "360p"
QUALITY = "720p"
```
Add Cookies.txt into directory for bypass youtube auth, cookies can get in browser like Chrome, Edge, or Firefox using addons

---

### 2. Run the Application

Run the FastAPI server with:

```bash
python app.py
```

---

### 3. View Your Stream

Open your browser and go to:

👉 [http://localhost:8081](http://localhost:8081)

(or the port you configured).

---


## 💡 Tips

- The app **automatically loops** videos for 24/7 playback.  
- To stream a playlist, just paste the playlist URL — it will cycle through videos.  
- Make sure **FFmpeg** is installed and accessible globally.

---

## 🧾 License

MIT License © 2025 — You are free to use, modify, and distribute this software.

---
