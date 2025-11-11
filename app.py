# app.py (FastAPI Version)
import os
import atexit
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from stream_manager import StreamManager
import config

# --- App Setup ---
app = FastAPI()
HLS_DIR = os.path.join(os.getcwd(), "hls")

# --- 1. Create StreamManager and Shutdown Hook ---
print("Starting stream manager...")
stream_manager = StreamManager(url=config.YOUTUBE_URL, quality_key=config.QUALITY)

@atexit.register
def shutdown():
    stream_manager.stop()

# --- 2. API Routes (now with async/await!) ---
@app.get("/api/control/{command}")
async def control_stream(command: str):
    if command == 'next':
        stream_manager.next()
    elif command == 'prev':
        stream_manager.prev()
    else:
        raise HTTPException(status_code=400, detail="Invalid command")
    return {"status": "ok", "command": command}

@app.get("/api/control/skip/{video_num}")
async def control_skip(video_num: int):
    if video_num < 1:
        raise HTTPException(status_code=400, detail="Invalid video number")
    stream_manager.skip(video_num)
    return {"status": "ok", "command": "skip", "video": video_num}

@app.get("/api/status")
async def stream_status():
    return stream_manager.get_status()

# --- 3. File Serving ---
# Serve HLS files
@app.get("/hls/{path:path}")
async def hls_files(path: str):
    return FileResponse(os.path.join(HLS_DIR, path))

# Serve the static frontend (index.html, etc.)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# --- 4. Main (requires 'uvicorn' to run) ---
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Server starting on http://0.0.0.0:{config.PORT}")
    print(f"    View automatic API docs at http://localhost:{config.PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
