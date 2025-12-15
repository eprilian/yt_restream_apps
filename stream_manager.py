import os
import subprocess
import yt_dlp
import time
import signal
import shutil
import threading
import logging
from queue import Queue

# --- Configuration ---
HLS_DIR = os.path.join(os.getcwd(), "hls")

# --- Quality Presets ---
QUALITY_PRESETS = {
    "1080p": {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "resolution": "1920x1080", "bitrate": "4000k",
    },
    "720p": {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "resolution": "1280x720", "bitrate": "2500k",
    },
    "480p": {
        "format": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "resolution": "854x480", "bitrate": "1000k",
    },
    "360p": {
        "format": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "resolution": "640x360", "bitrate": "700k",
    },
}

class StreamManager:
    """
    Manages the entire 24/7 restreaming process in a background thread.
    This class handles playlist fetching, ffmpeg processes, and state.
    """
    def __init__(self, url, quality_key="720p"):
        print(f"Initializing StreamManager for URL: {url}")
        
        # --- Stream State ---
        self.ffmpeg_proc = None
        self.playlist = []
        self.current_index = -1
        
        # --- Threading & Comms ---
        self.command_queue = Queue()
        self.stop_event = threading.Event()
        self.stream_ready = threading.Event()
        
        # --- Configuration ---
        if quality_key not in QUALITY_PRESETS:
            print(f"Warning: Quality '{quality_key}' not found. Defaulting to 720p.")
            quality_key = "720p"
            
        self.config = {
            "url": url,
            **QUALITY_PRESETS[quality_key]
        }
        
        # --- File Paths ---
        self.m3u8_file = os.path.join(HLS_DIR, "stream.m3u8")
        os.makedirs(HLS_DIR, exist_ok=True)
        
        # --- Cookie Check ---
        self.cookie_file = os.path.join(os.getcwd(), "cookies.txt")
        if os.path.exists(self.cookie_file):
            print(f"✅ Found cookies.txt at: {self.cookie_file}")
        else:
            print(f"⚠️ WARNING: cookies.txt NOT found at {self.cookie_file}")
            print("   You may get 'Sign in to confirm you're not a bot' errors.")
            self.cookie_file = None # Disable if not found to prevent crash

        # --- Start the Worker ---
        self.worker_thread = threading.Thread(target=self._stream_worker, daemon=True)
        self.worker_thread.start()

    def stop(self):
        """Public method to safely shut down the stream manager."""
        print("Shutting down StreamManager...")
        self.stop_event.set()
        
        # Send a 'stop' command to wake the worker if it's sleeping
        self.command_queue.put("stop") 
        
        if self.ffmpeg_proc:
            print("Terminating ffmpeg process...")
            self.ffmpeg_proc.terminate()
            self.ffmpeg_proc.wait()
            
        self.worker_thread.join(timeout=5)
        print("StreamManager shut down gracefully.")

    # --- Public API (Called by Flask/FastAPI) ---

    def next(self):
        """Tells the worker to skip to the next video."""
        print("API: Received 'next' command.")
        self.command_queue.put("next")

    def prev(self):
        """Tells the worker to skip to the previous video."""
        print("API: Received 'prev' command.")
        self.command_queue.put("prev")

    def skip(self, video_num):
        """Tells the worker to skip to a specific video number (1-based)."""
        print(f"API: Received 'skip' command to video {video_num}.")
        self.command_queue.put(("skip", video_num))

    def get_status(self):
        """Returns the current status for the API."""
        status = "ready" if self.stream_ready.is_set() else "loading"
        return {
            "status": status,
            "video": self.current_index + 1 if self.current_index >= 0 else 0,
            "total": len(self.playlist)
        }

    # --- Private Methods (Internal Worker Logic) ---

    def _get_common_opts(self):
        """Returns common yt-dlp options including cookies if available."""
        opts = {
            "quiet": True,
            "ignoreerrors": True,
            # We removed 'source_address' here. 
            # This allows yt-dlp to use IPv6 if that is all you have,
            # or IPv4 if you have that. It won't crash either way.
        }
        if self.cookie_file:
            opts["cookiefile"] = self.cookie_file
        return opts

    def _get_playlist_videos(self, url):
        """Gets a list of video PAGE URLs from a playlist or single video URL."""
        playlist_ydl_opts = self._get_common_opts()
        playlist_ydl_opts.update({
            "extract_flat": True, 
            "skip_download": True,
            "playlistreverse": False
        })

        print(f"🔎 Finding videos in: {url} (Top-to-Bottom)")
        with yt_dlp.YoutubeDL(playlist_ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if "_type" in info and info["_type"] == "playlist":
                    return [entry["url"] for entry in info["entries"] if entry]
                else:
                    return [url] # Return as a list of one
            except Exception as e:
                print(f"❌ Error getting playlist: {e}")
                return []

    def _get_media_url(self, video_url, video_format):
        """Gets the raw video and audio stream URLs."""
        print(f" extracting media URLs for: {video_url}")
        media_ydl_opts = self._get_common_opts()
        media_ydl_opts.update({
            "format": video_format, 
            "extractor_args": {"youtube": {"client": "android"}}
        })

        with yt_dlp.YoutubeDL(media_ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                # Handle combined formats (like some non-DASH streams)
                if 'url' in info and 'requested_formats' not in info:
                    print("...found single media URL.")
                    return info['url'], info['url']
                
                # Handle separate video/audio (DASH)
                if 'requested_formats' in info and len(info['requested_formats']) >= 2:
                    print("...found separate video and audio URLs.")
                    # Assume [0] is video, [1] is audio. This is typical.
                    return info['requested_formats'][0]['url'], info['requested_formats'][1]['url']
                
                # Handle single-URL formats (fallback)
                if 'url' in info:
                    print("...found single media URL (fallback).")
                    return info['url'], info['url']

                raise KeyError("'requested_formats' or 'url' key not found.")
            except Exception as e:
                print(f"⚠️ Could not get media URL: {e}")
                return None, None

    def _stream_video(self, video_url, audio_url, resolution, bitrate):
            """Launches the ffmpeg subprocess."""
            print(f"🎥 Starting ffmpeg stream ({resolution} @ {bitrate})...")

            cmd_input = []
            cmd_map = []

            if video_url == audio_url:
                # Handle single-URL streams
                cmd_input = ["-i", video_url]
                cmd_map = ["-map", "0:v:0", "-map", "0:a:0"]
            else:
                # Handle separate video/audio streams
                cmd_input = ["-i", video_url, "-i", audio_url]
                cmd_map = ["-map", "0:v:0", "-map", "1:a:0"]
                
            cmd = [
                "ffmpeg", "-re",
                *cmd_input,
                *cmd_map,
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p",
                "-s", resolution,
                "-b:v", bitrate,
                "-c:a", "aac", "-b:a", "128k",
                "-f", "hls",
                "-hls_time", "2",
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", f"{HLS_DIR}/stream%03d.ts",
                f"{HLS_DIR}/stream.m3u8"
            ]
            
            # We now redirect stderr to stdout to see errors
            return subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.DEVNULL)

    def _wait_for_stream(self, m3u8_path, timeout=20):
        """Waits for both the m3u8 and the first .ts segment to appear."""
        ts_path = os.path.join(HLS_DIR, "stream000.ts")
        start_time = time.time()
        print("...Waiting for ffmpeg to create stream files (m3u8 & ts)...")
        
        m3u8_ready = False
        ts_ready = False
        
        while time.time() - start_time < timeout:
            if not m3u8_ready and os.path.exists(m3u8_path) and os.path.getsize(m3u8_path) > 0:
                print("...m3u8 found...")
                m3u8_ready = True
            
            if not ts_ready and os.path.exists(ts_path) and os.path.getsize(ts_path) > 0:
                print("...stream000.ts found...")
                ts_ready = True
                
            if m3u8_ready and ts_ready:
                print("✅ m3u8 and .ts found! Stream is starting.")
                return True
            
            # Check if ffmpeg died prematurely
            if self.ffmpeg_proc and self.ffmpeg_proc.poll() is not None:
                print("❌ ffmpeg terminated unexpectedly while waiting for files.")
                return False
                
            time.sleep(0.5)
            
        print("❌ ffmpeg timed out waiting for stream files.")
        if not m3u8_ready: print("    - m3u8 was missing.")
        if not ts_ready: print("    - stream000.ts was missing.")
        return False

    def _clean_hls_directory(self):
        """Deletes all .m3u8 and .ts files from the HLS directory."""
        print("🧹 Cleaning HLS directory of old segments...")
        try:
            for f in os.listdir(HLS_DIR):
                if f.endswith((".m3u8", ".ts")):
                    os.remove(os.path.join(HLS_DIR, f))
        except Exception as e:
            print(f"⚠️ Error cleaning HLS directory: {e}")

    def _stream_worker(self):
        """The main 24/7 loop, runs in a separate thread."""
        
        while not self.stop_event.is_set():
            command = None # Clear command
            try:
                # --- 1. Check for commands first ---
                if not self.command_queue.empty():
                    cmd_data = self.command_queue.get()
                    
                    if cmd_data == "stop":
                        break # Exit the while loop

                    if isinstance(cmd_data, tuple) and cmd_data[0] == "skip":
                        command = "skip"
                        # -1 because user sees "1" but index is "0"
                        self.current_index = cmd_data[1] - 1 
                        print(f"Worker: Processing 'skip' to index {self.current_index}")
                    
                    elif cmd_data == "next":
                        command = "next"
                        self.current_index += 1
                        print(f"Worker: Processing 'next' to index {self.current_index}")

                    elif cmd_data == "prev":
                        command = "prev"
                        self.current_index -= 1
                        print(f"Worker: Processing 'prev' to index {self.current_index}")
                
                # --- 2. Playlist & Index Validation ---
                if not self.playlist:
                    print("🔄 Fetching new playlist...")
                    self.playlist = self._get_playlist_videos(self.config["url"])
                    
                    if not self.playlist:
                        print("❌ Playlist empty. Retrying in 60s...")
                        time.sleep(60)
                        continue
                    
                    # Only set index to 0 if this is the *first* load
                    if self.current_index == -1:
                        print(f"✅ Playlist found with {len(self.playlist)} videos. Starting at 1.")
                        self.current_index = 0
                
                # Handle index boundaries
                if not (0 <= self.current_index < len(self.playlist)):
                    if self.current_index >= len(self.playlist):
                        print("...Looping playlist to beginning...")
                        self.current_index = 0
                    elif self.current_index < 0:
                        print("...Looping playlist to end...")
                        self.current_index = len(self.playlist) - 1
                
                # --- 3. Get Video & Start Stream ---
                page_url = self.playlist[self.current_index]
                print(f"\n▶️ Starting video {self.current_index + 1}/{len(self.playlist)}: {page_url}")

                video_url, audio_url = self._get_media_url(page_url, self.config["format"])
                if not video_url or not audio_url:
                    print("❌ Skipping video (could not get media URL).")
                    command = 'next'
                    continue # Go to 'finally' block, which will increment index

                self._clean_hls_directory()
                self.stream_ready.clear() # Set status to "loading"

                self.ffmpeg_proc = self._stream_video(video_url, audio_url,
                                                        self.config["resolution"], self.config["bitrate"])

                if not self._wait_for_stream(self.m3u8_file):
                    print("❌ ffmpeg failed to start. Skipping.")
                    if self.ffmpeg_proc: self.ffmpeg_proc.terminate()
                    command = 'next'
                    continue
                
                self.stream_ready.set() # Set status to "ready"
                print("✅ Stream is live. Monitoring process...")

                # --- 4. Wait for ffmpeg to finish (or command) ---
                while self.ffmpeg_proc.poll() is None:
                    if self.stop_event.is_set():
                        self.ffmpeg_proc.terminate()
                        break
                    
                    if not self.command_queue.empty():
                        print("...Command received, terminating current stream...")
                        self.ffmpeg_proc.terminate()
                        break 
                        
                    time.sleep(0.5) # Poll loop

            except Exception as e:
                print(f"Error in stream worker: {e}")
                if self.ffmpeg_proc: self.ffmpeg_proc.terminate()
                time.sleep(10) # Wait before retrying

            finally:
                # --- 5. Cleanup & Index Logic ---
                self.ffmpeg_proc = None
                
                # If the loop ended *naturally* (not by command), move to next video
                if not command and self.command_queue.empty() and not self.stop_event.is_set():
                    print("...Video finished naturally, moving to next...")
                    self.current_index += 1

                if self.stop_event.is_set():
                    print("...Stop event detected, exiting worker loop...")

                # Don't sleep if a command is waiting
                if self.command_queue.empty():
                    print("...Waiting 3s before next cycle...")
                    time.sleep(3)

        self.stream_ready.set() # Set to ready on exit so API doesn't hang
        print("🛑 Stream worker loop finished.")
