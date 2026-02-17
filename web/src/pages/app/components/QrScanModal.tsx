import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react';
import { X } from 'lucide-react';

type QrScanModalProps = {
    isOpen: boolean;
    onClose: () => void;
    onDetected: (rawValue: string) => void;
};

type ScanState = 'idle' | 'starting' | 'scanning' | 'error';

const getCameraErrorMessage = (error: unknown) => {
    const asError = error as { name?: string; message?: string };
    if (asError?.name === 'NotAllowedError') {
        return 'Permissão de câmera negada. Autorize o acesso e tente novamente.';
    }
    if (asError?.name === 'NotFoundError') {
        return 'Nenhuma câmera encontrada neste dispositivo.';
    }
    if (asError?.name === 'NotReadableError') {
        return 'A câmera já está em uso por outro aplicativo.';
    }
    if (asError?.name === 'OverconstrainedError') {
        return 'Não foi possível abrir a câmera traseira. Tente novamente.';
    }
    return asError?.message || 'Falha ao iniciar câmera para leitura do QR Code.';
};

export const QrScanModal = ({ isOpen, onClose, onDetected }: QrScanModalProps) => {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const frameRef = useRef<number | null>(null);
    const detectorRef = useRef<{ detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue?: string }>> } | null>(null);
    const lastDetectRef = useRef(0);
    const [scanState, setScanState] = useState<ScanState>('idle');
    const [statusMessage, setStatusMessage] = useState('');

    const stopCamera = useCallback(() => {
        if (frameRef.current !== null) {
            window.cancelAnimationFrame(frameRef.current);
            frameRef.current = null;
        }
        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        detectorRef.current = null;
    }, []);

    const emitDetected = useEffectEvent((rawValue: string) => {
        const value = rawValue.trim();
        if (!value) return;
        stopCamera();
        onDetected(value);
    });

    useEffect(() => {
        if (!isOpen) {
            stopCamera();
            return;
        }

        let cancelled = false;
        const start = async () => {
            setScanState('starting');
            setStatusMessage('Abrindo câmera...');

            const BarcodeDetectorCtor = (window as unknown as {
                BarcodeDetector?: new (options: { formats: string[] }) => { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue?: string }>> };
            }).BarcodeDetector;

            if (!BarcodeDetectorCtor) {
                setScanState('error');
                setStatusMessage('Leitura por câmera não suportada neste navegador. Use a câmera nativa do dispositivo para ler o QR Code.');
                return;
            }

            if (!navigator.mediaDevices?.getUserMedia) {
                setScanState('error');
                setStatusMessage('A câmera não está disponível neste navegador. Use a câmera nativa do dispositivo para ler o QR Code.');
                return;
            }

            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        facingMode: { ideal: 'environment' },
                    },
                });

                if (cancelled) {
                    stream.getTracks().forEach((track) => track.stop());
                    return;
                }

                streamRef.current = stream;
                detectorRef.current = new BarcodeDetectorCtor({ formats: ['qr_code'] });

                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    await videoRef.current.play();
                }

                if (cancelled) return;

                setScanState('scanning');
                setStatusMessage('');
                const scheduleNext = () => {
                    frameRef.current = window.requestAnimationFrame(() => {
                        void scanLoop();
                    });
                };

                const scanLoop = async () => {
                    if (cancelled || !videoRef.current || !detectorRef.current) {
                        return;
                    }
                    try {
                        const now = Date.now();
                        if (now - lastDetectRef.current >= 200 && videoRef.current.readyState >= 2) {
                            lastDetectRef.current = now;
                            const results = await detectorRef.current.detect(videoRef.current);
                            const first = results.find((item) => item.rawValue && item.rawValue.trim());
                            if (first?.rawValue) {
                                emitDetected(first.rawValue);
                                return;
                            }
                        }
                    } catch {
                        // ignore transient detector errors and keep scanning
                    }
                    scheduleNext();
                };

                scheduleNext();
            } catch (error) {
                if (cancelled) return;
                setScanState('error');
                setStatusMessage(getCameraErrorMessage(error));
            }
        };

        void start();

        return () => {
            cancelled = true;
            stopCamera();
        };
    }, [isOpen, stopCamera]);

    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        }
        return () => {
            document.body.style.overflow = '';
        };
    }, [isOpen]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 bg-black">
            {/* Camera feed - full screen */}
            <video
                ref={videoRef}
                className="absolute inset-0 h-full w-full object-cover"
                muted
                playsInline
                autoPlay
            />

            {/* Overlay with cutout */}
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                {/* Top dark overlay */}
                <div className="w-full flex-1 bg-black/60" />

                {/* Middle row: left dark | viewfinder | right dark */}
                <div className="flex w-full items-center justify-center">
                    <div className="flex-1 bg-black/60" style={{ height: 256 }} />
                    <div className="relative h-64 w-64 shrink-0">
                        {/* Corner accents */}
                        <span className="absolute left-0 top-0 h-8 w-8 rounded-tl-lg border-l-[3px] border-t-[3px] border-white" />
                        <span className="absolute right-0 top-0 h-8 w-8 rounded-tr-lg border-r-[3px] border-t-[3px] border-white" />
                        <span className="absolute bottom-0 left-0 h-8 w-8 rounded-bl-lg border-b-[3px] border-l-[3px] border-white" />
                        <span className="absolute bottom-0 right-0 h-8 w-8 rounded-br-lg border-b-[3px] border-r-[3px] border-white" />

                        {/* Scan line animation */}
                        {scanState === 'scanning' ? (
                            <span className="absolute left-2 right-2 h-0.5 bg-emerald-400/80 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-[scanline_2s_ease-in-out_infinite]" />
                        ) : null}
                    </div>
                    <div className="flex-1 bg-black/60" style={{ height: 256 }} />
                </div>

                {/* Bottom dark overlay */}
                <div className="flex w-full flex-1 flex-col items-center bg-black/60 pt-6">
                    {scanState === 'starting' ? (
                        <div className="flex items-center gap-2 text-sm text-white/80">
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                            Iniciando câmera...
                        </div>
                    ) : scanState === 'error' ? (
                        <p className="max-w-xs px-4 text-center text-sm text-red-300">
                            {statusMessage}
                        </p>
                    ) : (
                        <p className="text-sm text-white/80">
                            Aponte para o QR Code
                        </p>
                    )}
                </div>
            </div>

            {/* Close button */}
            <button
                type="button"
                onClick={onClose}
                className="absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur-sm transition hover:bg-black/70"
                aria-label="Fechar"
            >
                <X className="h-5 w-5" />
            </button>

            {/* Scan line keyframes */}
            <style>{`
                @keyframes scanline {
                    0%, 100% { top: 8px; }
                    50% { top: calc(100% - 10px); }
                }
            `}</style>
        </div>
    );
};
