document.addEventListener('DOMContentLoaded', () => {
    const player = videojs('my-video', {
        autoplay: true,
        muted: true, // Autoplay must be muted in most browsers
    });

    // Unmute after user interacts or 1s
    setTimeout(() => {
        if (player.paused()) player.play();
        player.muted(false);
    }, 1000);

    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const title = document.querySelector('h1');

    let isPolling = false;
    let currentVideoId = null; // Store the ID of the video in the player

    /**
     * Polls the /api/status endpoint until the stream is "ready".
     * expectedVideoId ensures we wait for the *correct* video.
     */
    function pollForStreamReady(expectedVideoId = null) {
        if (isPolling) return; // Don't start multiple polls
        isPolling = true;
        console.log(`Polling for new stream... (Expecting: ${expectedVideoId || 'any'})`);

        let pollCount = 0;
        const maxPolls = 30; // 30 * 500ms = 15 seconds timeout

        const poll = async () => {
            if (pollCount++ > maxPolls) {
                console.error('Stream status poll timed out.');
                title.textContent = 'Stream Error (Timeout)';
                isPolling = false;
                return;
            }

            try {
                const response = await fetch(`/api/status?t=${new Date().getTime()}`);
                const data = await response.json();

                if (data.status === 'ready') {
                    let loadThisVideo = false;
                    
                    if (expectedVideoId !== null) {
                        // --- We are waiting for a specific video ---
                        if (data.video === expectedVideoId) {
                            console.log(`Poller: Expected video ${expectedVideoId} is ready.`);
                            loadThisVideo = true;
                        } else {
                            // Server is ready, but on the wrong video.
                            console.log(`Poller: Waiting for video ${expectedVideoId}, but server is on ${data.video}. Retrying...`);
                            setTimeout(poll, 500); // Keep polling
                            return; // Don't proceed
                        }
                    } else {
                        // --- We are not waiting for a specific video ---
                        if (data.video !== currentVideoId) {
                            console.log(`Poller: New video ${data.video} is ready (natural advance or initial load).`);
                            loadThisVideo = true;
                        } else {
                            // --- THIS IS THE FIX for errors/refreshes ---
                            // Same video. Only reload the source if the player is broken.
                            if (player.error() || player.paused()) {
                                console.log('Poller: Stream is ready (same video). Player is broken, reloading source.');
                                loadThisVideo = true; // Force reload
                            } else {
                                console.log('Poller: Stream is ready (same video). Player is fine. Doing nothing.');
                                isPolling = false; // We're done
                                title.textContent = `Restream Video (${data.video} / ${data.total})`;
                                return; // Exit
                            }
                        }
                    }
                    
                    // --- Common logic to load the video ---
                    if (loadThisVideo) {
                        console.log(`Reloading player with video ${data.video}.`);
                        isPolling = false; // Stop polling
                        title.textContent = `Restream Video (${data.video} / ${data.total})`;
                        
                        const newSource = `/hls/stream.m3u8?t=${new Date().getTime()}`;
                        player.src({ src: newSource, type: 'application/x-mpegURL' });
                        player.play();
                        currentVideoId = data.video; 
                        
                        const newUrl = `${window.location.pathname}?video=${currentVideoId}`;
                        window.history.pushState({ path: newUrl }, '', newUrl);
                    }
                    
                } else {
                    // --- Status is 'loading' ---
                    let loadingMsg = `Stream Loading... (${data.video} / ${data.total})`;
                    if (expectedVideoId !== null && data.video !== expectedVideoId) {
                        loadingMsg = `Waiting for Video ${expectedVideoId} (Server is loading ${data.video})...`;
                    }
                    title.textContent = loadingMsg;
                    setTimeout(poll, 500); // Keep polling
                }
            } catch (error) {
                console.warn('Poll error:', error, 'Retrying...');
                setTimeout(poll, 1000); // Wait longer on error
            }
        };
        
        poll(); // Start polling
    }

    /**
     * Sends a control command ('next' or 'prev') to the server.
     */
    async function sendControl(command) {
        try {
            console.log(`Sending command: ${command}`);
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            
            player.pause();
            player.src({ src: '', type: 'application/x-mpegURL' }); // Blank the source

            await fetch(`/api/control/${command}`);
            
            pollForStreamReady();
            
        } catch (error) {
            console.error('Error sending control command:', error);
        } finally {
            setTimeout(() => {
                prevBtn.disabled = false;
                nextBtn.disabled = false;
            }, 1000);
        }
    }

    /**
     * Sends a 'skip' command to the server.
     */
    async function sendSkip(videoNum) {
         try {
            console.log(`Sending command: skip to ${videoNum}`);
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            
            player.pause();
            player.src({ src: '', type: 'application/x-mpegURL' }); // Blank source

            await fetch(`/api/control/skip/${videoNum}`);
            
            pollForStreamReady(videoNum);

         } catch (error) {
            console.error('Error sending skip command:', error);
         } finally {
            setTimeout(() => {
                prevBtn.disabled = false;
                nextBtn.disabled = false;
            }, 1000);
         }
    }

    prevBtn.addEventListener('click', () => sendControl('prev'));
    nextBtn.addEventListener('click', () => sendControl('next'));

    player.on('error', () => {
        const error = player.error();
        if (!isPolling) {
            console.warn('Player error detected. Retrying...', error);
            pollForStreamReady();
        }
    });
    
    // --- NEW: Initial Load Logic ---
    async function initialLoad() {
        const urlParams = new URLSearchParams(window.location.search);
        const videoToLoad = urlParams.get('video');
        
        if (videoToLoad && !isNaN(videoToLoad)) {
            // URL has a video number. Let's check the server's status first.
            const videoNum = parseInt(videoToLoad);
            console.log(`URL requests video ${videoNum}. Checking server status...`);
            
            try {
                const response = await fetch(`/api/status?t=${new Date().getTime()}`);
                const data = await response.json();

                if (data.video === videoNum) {
                    // Server is *already* on this video. This is a simple refresh.
                    console.log(`Server is already on video ${videoNum}. Loading player normally.`);
                    pollForStreamReady(); // Just poll for readiness
                } else {
                    // Server is on a different video. We need to send a skip command.
                    console.log(`Server is on ${data.video}. Sending skip command for ${videoNum}.`);
                    sendSkip(videoNum);
                }
            } catch (e) {
                // API might be down, just try to skip.
                console.warn("Couldn't check status, sending skip command anyway.", e);
                sendSkip(videoNum);
            }
        } else {
            // No video in URL. Just load the stream normally.
            console.log('No video in URL. Loading current stream.');
            pollForStreamReady();
        }
    }
    
    initialLoad(); // Run the new load logic
});