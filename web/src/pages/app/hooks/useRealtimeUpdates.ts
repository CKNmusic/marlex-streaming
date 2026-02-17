import { useEffect, useEffectEvent } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { WS_URL, session } from '../../../lib/api/client';
import type { DeviceStatus, ManagerMetric, Record as RecordApi, User } from '../../../lib/api/client';

type UseRealtimeUpdatesArgs = {
    user: User | null;
    enabled?: boolean;
    scopeKey?: string;
    setDeviceStatus: Dispatch<SetStateAction<Record<number, DeviceStatus>>>;
    setRecords: Dispatch<SetStateAction<RecordApi[]>>;
    setManagerMetrics: Dispatch<SetStateAction<ManagerMetric | null>>;
    onRecordEnded: (referenceMs?: number) => void;
    onRecordStatusSync?: () => void;
    onConnectionStateChange?: (connected: boolean) => void;
};

const toDeviceStatus = (input: Record<string, unknown>): DeviceStatus | null => {
    const deviceId = Number(input.device_id || 0);
    if (deviceId <= 0) return null;
    const rawMetadata = input.metadata;
    const metadata = (rawMetadata && typeof rawMetadata === 'object')
        ? (rawMetadata as DeviceStatus['metadata'])
        : null;
    return {
        device_id: deviceId,
        online: Boolean(input.online),
        status: String(input.status || 'Offline'),
        stream_url: (input.stream_url as string | null) || null,
        checked_at: String(input.checked_at || new Date().toISOString()),
        metadata,
    };
};

export const useRealtimeUpdates = ({
    user,
    enabled = true,
    scopeKey = 'default',
    setDeviceStatus,
    setRecords,
    setManagerMetrics,
    onRecordEnded,
    onRecordStatusSync,
    onConnectionStateChange,
}: UseRealtimeUpdatesArgs) => {
    const notifyRecordEnded = useEffectEvent((referenceMs?: number) => {
        onRecordEnded(referenceMs);
    });
    const notifyRecordStatusSync = useEffectEvent(() => {
        onRecordStatusSync?.();
    });
    const notifyConnectionState = useEffectEvent((connected: boolean) => {
        onConnectionStateChange?.(connected);
    });

    useEffect(() => {
        if (!user) return;
        if (!enabled) return;
        const token = session.getToken();
        if (!token) return;
        let ws: WebSocket | null = null;
        const manualClose = new WeakSet<WebSocket>();
        let pingTimer: number | null = null;
        let reconnectTimer: number | null = null;
        let reconnectDelayMs = 1000;
        let disposed = false;

        const queryParts = [`token=${encodeURIComponent(token)}`];
        if (user.is_superuser) {
            queryParts.push('dashboard=manager');
        }

        const wsUrl = `${WS_URL.replace(/\/$/, '')}/realtime/ws?${queryParts.join('&')}`;
        const pageIsActive = () => !document.hidden && document.visibilityState === 'visible';
        const clearPing = () => {
            if (pingTimer !== null) {
                window.clearInterval(pingTimer);
                pingTimer = null;
            }
        };
        const scheduleReconnect = (delayMs: number) => {
            if (reconnectTimer !== null) {
                window.clearTimeout(reconnectTimer);
            }
            reconnectTimer = window.setTimeout(() => {
                reconnectTimer = null;
                void connect();
            }, delayMs);
        };

        const connect = () => {
            if (disposed || !pageIsActive()) return;
            if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

            const socket = new WebSocket(wsUrl);
            ws = socket;

            socket.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data) as Record<string, unknown>;
                    const eventType = String(payload.type || '');

                    if (eventType === 'device_status') {
                        const nextStatus = toDeviceStatus(payload);
                        if (nextStatus) {
                            setDeviceStatus((state) => ({
                                ...state,
                                [nextStatus.device_id]: nextStatus,
                            }));
                        }
                        return;
                    }

                    if (eventType === 'record_status') {
                        const recordId = Number(payload.record_id || 0);
                        if (recordId > 0) {
                            const eventEndedAt = (payload.end_time as string | null) || null;
                            setRecords((state) => state.map((item) => {
                                if (item.id !== recordId) return item;
                                return {
                                    ...item,
                                    end_time: eventEndedAt || item.end_time,
                                    final_status: (payload.final_status as string | null) || item.final_status,
                                    stop_reason: (payload.stop_reason as string | null) || item.stop_reason,
                                };
                            }));
                            if (eventEndedAt) {
                                const endedAtMs = new Date(eventEndedAt).getTime();
                                notifyRecordEnded(Number.isFinite(endedAtMs) ? endedAtMs : undefined);
                            }
                            notifyRecordStatusSync();
                        }
                        return;
                    }

                    if (eventType === 'manager_metrics' && user.is_superuser && payload.metrics) {
                        setManagerMetrics(payload.metrics as ManagerMetric);
                        return;
                    }

                    if (eventType === 'snapshot') {
                        const snapshotDevices = Array.isArray(payload.devices) ? payload.devices : [];
                        setDeviceStatus(() => {
                            const next: Record<number, DeviceStatus> = {};
                            snapshotDevices.forEach((entry) => {
                                const nextStatus = toDeviceStatus(entry as Record<string, unknown>);
                                if (nextStatus) {
                                    next[nextStatus.device_id] = nextStatus;
                                }
                            });
                            return next;
                        });
                        if (user.is_superuser && payload.metrics) {
                            setManagerMetrics(payload.metrics as ManagerMetric);
                        }
                    }
                } catch {
                    // ignore malformed realtime events
                }
            };

            socket.onopen = () => {
                if (disposed || !pageIsActive()) {
                    manualClose.add(socket);
                    socket.close(1000, 'inactive');
                    return;
                }
                notifyConnectionState(true);
                reconnectDelayMs = 1000;
                clearPing();
                pingTimer = window.setInterval(() => {
                    if (socket.readyState === WebSocket.OPEN) {
                        socket.send('ping');
                    }
                }, 15000);
            };

            socket.onclose = () => {
                notifyConnectionState(false);
                clearPing();
                if (ws === socket) {
                    ws = null;
                }
                if (manualClose.has(socket)) {
                    manualClose.delete(socket);
                    return;
                }
                if (disposed || !pageIsActive()) return;
                reconnectDelayMs = Math.min(reconnectDelayMs * 2, 30000);
                scheduleReconnect(reconnectDelayMs);
            };

            socket.onerror = () => {
                notifyConnectionState(false);
            };
        };

        const disconnect = () => {
            notifyConnectionState(false);
            clearPing();
            if (reconnectTimer !== null) {
                window.clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            if (!ws) {
                return;
            }
            const socket = ws;
            ws = null;
            manualClose.add(socket);
            if (socket.readyState === WebSocket.OPEN) {
                socket.close(1000, 'client-disconnect');
                return;
            }
            if (socket.readyState === WebSocket.CONNECTING) {
                socket.addEventListener(
                    'open',
                    () => {
                        if (socket.readyState === WebSocket.OPEN) {
                            socket.close(1000, 'client-disconnect');
                        }
                    },
                    { once: true },
                );
            }
        };

        const handleVisibilityChange = () => {
            if (!pageIsActive()) {
                disconnect();
                return;
            }
            connect();
        };

        void connect();
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('beforeunload', disconnect);

        return () => {
            disposed = true;
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            window.removeEventListener('beforeunload', disconnect);
            if (reconnectTimer !== null) {
                window.clearTimeout(reconnectTimer);
            }
            disconnect();
        };
    }, [user, enabled, scopeKey, setDeviceStatus, setManagerMetrics, setRecords]);
};
