import { useCallback, useEffect, useRef, useState } from 'react';
import { Maximize, Minimize, Pause, Play, Volume2, VolumeX } from 'lucide-react';

type LiveStreamPlayerProps = {
    /** WHEP endpoint URL */
    src: string;
    className?: string;
    /** Show player controls (default true) */
    controls?: boolean;
    /** Start muted (default true) */
    startMuted?: boolean;
};

export const LiveStreamPlayer = ({ src, className = '', controls = true, startMuted = true }: LiveStreamPlayerProps) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const pcRef = useRef<RTCPeerConnection | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [muted, setMuted] = useState(startMuted);
    const [volume, setVolume] = useState(0.8);
    const [paused, setPaused] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [showControls, setShowControls] = useState(true);
    const hideTimerRef = useRef<ReturnType<typeof setTimeout>>();

    const resetHideTimer = useCallback(() => {
        setShowControls(true);
        if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
        hideTimerRef.current = setTimeout(() => setShowControls(false), 3000);
    }, []);

    useEffect(() => {
        return () => { if (hideTimerRef.current) clearTimeout(hideTimerRef.current); };
    }, []);

    useEffect(() => {
        const video = videoRef.current;
        if (!video || !src) return;

        setError(null);
        setLoading(true);
        setPaused(false);

        let cancelled = false;
        let resourceUrl: string | null = null;

        const connect = async () => {
            try {
                const pc = new RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
                });
                pcRef.current = pc;

                pc.addTransceiver('video', { direction: 'recvonly' });
                pc.addTransceiver('audio', { direction: 'recvonly' });

                pc.ontrack = (event) => {
                    if (event.streams[0] && video.srcObject !== event.streams[0]) {
                        video.srcObject = event.streams[0];
                        setLoading(false);
                        resetHideTimer();
                    }
                };

                pc.oniceconnectionstatechange = () => {
                    if (cancelled) return;
                    const state = pc.iceConnectionState;
                    if (state === 'failed' || state === 'disconnected') {
                        setError('Conexão perdida');
                    } else if (state === 'connected' || state === 'completed') {
                        setError(null);
                        setLoading(false);
                    }
                };

                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                await new Promise<void>((resolve) => {
                    if (pc.iceGatheringState === 'complete') { resolve(); return; }
                    const timeout = setTimeout(resolve, 2000);
                    pc.onicegatheringstatechange = () => {
                        if (pc.iceGatheringState === 'complete') { clearTimeout(timeout); resolve(); }
                    };
                });

                if (cancelled) { pc.close(); return; }

                const response = await fetch(src, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: pc.localDescription?.sdp || '',
                });

                if (!response.ok) throw new Error(`WHEP ${response.status}`);

                const answerSdp = await response.text();
                resourceUrl = response.headers.get('Location');

                if (cancelled) { pc.close(); return; }

                await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: answerSdp }));
            } catch {
                if (!cancelled) { setError('Stream indisponível'); setLoading(false); }
            }
        };

        connect();

        return () => {
            cancelled = true;
            if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
            if (video.srcObject) { video.srcObject = null; }
            if (resourceUrl) {
                const deleteUrl = resourceUrl.startsWith('http') ? resourceUrl : new URL(resourceUrl, src).href;
                fetch(deleteUrl, { method: 'DELETE' }).catch(() => {});
            }
        };
    }, [src, resetHideTimer]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;
        video.muted = muted;
        video.volume = volume;
    }, [muted, volume]);

    const togglePlay = () => {
        const video = videoRef.current;
        if (!video) return;
        if (video.paused) { video.play().catch(() => {}); setPaused(false); }
        else { video.pause(); setPaused(true); }
    };

    const toggleMute = () => setMuted((m) => !m);

    const toggleFullscreen = () => {
        const el = containerRef.current;
        if (!el) return;
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
            setIsFullscreen(false);
        } else {
            el.requestFullscreen().catch(() => {});
            setIsFullscreen(true);
        }
    };

    useEffect(() => {
        const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
        document.addEventListener('fullscreenchange', onFsChange);
        return () => document.removeEventListener('fullscreenchange', onFsChange);
    }, []);

    return (
        <div
            ref={containerRef}
            className={`relative overflow-hidden rounded-md bg-black ${className}`}
            onMouseMove={controls ? resetHideTimer : undefined}
            onClick={controls ? resetHideTimer : undefined}
        >
            <video
                ref={videoRef}
                muted={muted}
                autoPlay
                playsInline
                className="h-full w-full"
            />

            {/* Loading */}
            {loading && !error && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                    <div className="flex flex-col items-center gap-2">
                        <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        <span className="text-xs text-white/80">Conectando ao vivo...</span>
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/70">
                    <span className="text-xs text-red-300">{error}</span>
                </div>
            )}

            {/* AO VIVO badge */}
            {!loading && !error && (
                <div className="absolute left-2 top-2 flex items-center gap-1.5 rounded bg-red-600/90 px-2 py-0.5">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-white">AO VIVO</span>
                </div>
            )}

            {/* Controls bar */}
            {controls && !loading && !error && (
                <div
                    className={`absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8 transition-opacity duration-300 ${showControls ? 'opacity-100' : 'opacity-0'}`}
                >
                    <button onClick={togglePlay} className="text-white hover:text-white/80 transition" title={paused ? 'Play' : 'Pausar'}>
                        {paused ? <Play className="h-5 w-5" /> : <Pause className="h-5 w-5" />}
                    </button>

                    <button onClick={toggleMute} className="text-white hover:text-white/80 transition" title={muted ? 'Ativar áudio' : 'Mutar'}>
                        {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
                    </button>

                    <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={muted ? 0 : volume}
                        onChange={(e) => { setVolume(parseFloat(e.target.value)); setMuted(false); }}
                        className="h-1 w-20 cursor-pointer appearance-none rounded-full bg-white/30 accent-white [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                    />

                    <div className="flex-1" />

                    <button onClick={toggleFullscreen} className="text-white hover:text-white/80 transition" title={isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'}>
                        {isFullscreen ? <Minimize className="h-5 w-5" /> : <Maximize className="h-5 w-5" />}
                    </button>
                </div>
            )}
        </div>
    );
};
