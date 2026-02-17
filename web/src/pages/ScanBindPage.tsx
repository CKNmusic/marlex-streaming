import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, QrCode } from 'lucide-react';
import axios from 'axios';
import { devicesAPI, session } from '../lib/api/client';
import { Button } from '../components/ui/Button';
import { StatusMsg } from '../components/ui/StatusMsg';

type BindStatus = 'idle' | 'loading' | 'success' | 'error';
const SCAN_FEEDBACK_STORAGE_KEY = 'scan_bind_feedback';
const SCAN_CONNECTION_TIMEOUT_MS = 5000;
const SCAN_STATUS_RETRY_MS = 1000;

const resolveDeviceLabel = (device: { mark_name?: string | null; model?: string | null; name?: string | null }) => {
    const mark = String(device.mark_name || '').trim();
    const model = String(device.model || device.name || '').trim();
    return [mark, model].filter(Boolean).join(' ');
};

const persistScanFeedback = (level: 'info' | 'warn' | 'error', nextMessage: string) => {
    try {
        localStorage.setItem(SCAN_FEEDBACK_STORAGE_KEY, JSON.stringify({ level, message: nextMessage }));
    } catch {
        // ignore storage failures
    }
};

export const ScanBindPage = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const key = searchParams.get('key');
    const missingKey = !key;
    const hasToken = !!session.getToken();
    const needsLogin = !!key && !hasToken;
    const cancelFlowRef = useRef(false);
    const [retryTick, setRetryTick] = useState(0);
    const [status, setStatus] = useState<BindStatus>(() => {
        if (missingKey) return 'error';
        if (needsLogin) return 'idle';
        return 'loading';
    });
    const [message, setMessage] = useState(
        missingKey
            ? 'Parâmetro key não informado no link.'
            : needsLogin
                ? 'Você precisa estar logado para concluir o scan.'
                : 'Aguardando dispositivo ficar online...'
    );
    const loginNextPath = useMemo(() => {
        if (missingKey)
            return '/scan';
        return `/scan?key=${encodeURIComponent(key)}`;
    }, [key, missingKey]);

    const handleLogin = () => {
        navigate(`/login?next=${encodeURIComponent(loginNextPath)}`, { replace: true });
    };

    const handleCancel = () => {
        cancelFlowRef.current = true;
        session.clearBoundDevice();
        navigate(hasToken ? '/app' : '/login', { replace: true });
    };

    const handleRetry = () => {
        cancelFlowRef.current = true;
        setRetryTick((current) => current + 1);
    };

    useEffect(() => {
        cancelFlowRef.current = false;
        let redirectTimer: number | null = null;
        let closeTimer: number | null = null;
        const sleep = (ms: number) => new Promise((resolve) => {
            window.setTimeout(resolve, ms);
        });

        if (missingKey || needsLogin) {
            return () => {
                cancelFlowRef.current = true;
            };
        }

        void (async () => {
            setStatus('loading');
            setMessage('Aguardando dispositivo ficar online...');
            try {
                const response = await devicesAPI.bind(key);
                if (cancelFlowRef.current) return;
                session.setBoundDevice(response.data);
                const deviceLabel = resolveDeviceLabel(response.data) || 'dispositivo';

                setStatus('loading');
                setMessage(`Dispositivo ${deviceLabel} identificado. Aguardando ficar online...`);

                let ready = false;
                const waitStartedAt = Date.now();
                while ((Date.now() - waitStartedAt) < SCAN_CONNECTION_TIMEOUT_MS) {
                    if (cancelFlowRef.current) return;
                    try {
                        const statusResponse = await devicesAPI.getBindStatus(response.data.id);
                        const nextStatus = statusResponse.data.status || 'Offline';
                        session.setBoundDevice({
                            ...response.data,
                            status: nextStatus,
                            last_seen: statusResponse.data.checked_at,
                        });
                        if (nextStatus === 'Online' || nextStatus === 'Recording') {
                            ready = true;
                            break;
                        }
                        setMessage(`Dispositivo ${deviceLabel} está offline. Aguardando conexão...`);
                    } catch {
                        setMessage(`Falha ao verificar status do dispositivo ${deviceLabel}. Tentando novamente...`);
                    }
                    const elapsed = Date.now() - waitStartedAt;
                    const remaining = SCAN_CONNECTION_TIMEOUT_MS - elapsed;
                    if (remaining <= 0) break;
                    await sleep(Math.min(SCAN_STATUS_RETRY_MS, remaining));
                }

                if (cancelFlowRef.current) return;
                if (!ready) {
                    const timeoutMessage = `Dispositivo ${deviceLabel} permanece offline após 5 segundos. Fechando...`;
                    setStatus('error');
                    setMessage(timeoutMessage);
                    closeTimer = window.setTimeout(() => {
                        if (cancelFlowRef.current) return;
                        persistScanFeedback('warn', timeoutMessage);
                        session.clearBoundDevice();
                        navigate(hasToken ? '/app' : '/login', { replace: true });
                    }, 400);
                    return;
                }

                setStatus('success');
                setMessage(`Dispositivo ${deviceLabel} pronto para gravação. Redirecionando...`);
                redirectTimer = window.setTimeout(() => navigate('/app', { replace: true }), 800);
            } catch (error) {
                if (cancelFlowRef.current) return;
                const detail = axios.isAxiosError(error)
                    ? error.response?.data?.detail
                    : null;
                setStatus('error');
                setMessage(typeof detail === 'string' && detail ? detail : 'Falha no vínculo do dispositivo. Verifique a key.');
            }
        })();

        return () => {
            cancelFlowRef.current = true;
            if (redirectTimer !== null) {
                window.clearTimeout(redirectTimer);
            }
            if (closeTimer !== null) {
                window.clearTimeout(closeTimer);
            }
        };
    }, [key, missingKey, navigate, needsLogin, retryTick, hasToken]);

    return (
        <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-6">
            <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-8 text-center">
                <div className="mb-4 flex justify-center">
                    <div className="rounded-xl bg-blue-500/10 p-3 ring-1 ring-blue-500/20">
                        <QrCode className="h-8 w-8 text-blue-400" />
                    </div>
                </div>

                {status === 'loading' ? <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin text-amber-500" /> : null}

                <StatusMsg
                    level={status === 'error' ? 'error' : status === 'loading' ? 'warn' : 'info'}
                    msg={message}
                    time_sec={status === 'loading' ? 10 : 3}
                />

                <div className="mt-4 flex flex-col gap-2">
                    {status === 'loading' ? (
                        <Button variant="secondary" onClick={handleCancel}>
                            Cancelar
                        </Button>
                    ) : null}

                    {!hasToken ? (
                        <Button onClick={handleLogin}>
                            Entrar para continuar
                        </Button>
                    ) : null}

                    {status === 'error' && key && hasToken ? (
                        <Button onClick={handleRetry}>
                            Tentar novamente
                        </Button>
                    ) : null}

                    {status !== 'loading' ? (
                        <Button variant="ghost" onClick={handleCancel}>
                            Voltar
                        </Button>
                    ) : null}
                </div>
            </div>
        </div>
    );
};
