export type DeviceRuntimeStatus = 'Offline' | 'Connecting' | 'Online' | 'Starting' | 'Recording' | 'Stopping';
const DEVICE_RUNTIME_STALE_MS = 15_000;

export type DeviceStatusHelpItem = {
    status: DeviceRuntimeStatus;
    title: string;
    description: string;
};

export const DEVICE_STATUS_HELP: DeviceStatusHelpItem[] = [
    {
        status: 'Offline',
        title: 'Offline',
        description: 'Sem comunicação.',
    },
    {
        status: 'Online',
        title: 'Online',
        description: 'Está ativo e publicando, aguardando gravação.',
    },
    {
        status: 'Connecting',
        title: 'Connecting',
        description: 'Publicação aceita e aguardando estabilizar o stream.',
    },
    {
        status: 'Starting',
        title: 'Starting',
        description: 'Transição para iniciar gravação.',
    },
    {
        status: 'Recording',
        title: 'Recording',
        description: 'Está ativa gravando.',
    },
    {
        status: 'Stopping',
        title: 'Stopping',
        description: 'Finalizando gravação em andamento.',
    },
];

export const normalizeDeviceRuntimeStatus = (value?: string | null): DeviceRuntimeStatus => {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'connecting') return 'Connecting';
    if (normalized === 'starting') return 'Starting';
    if (normalized === 'recording') return 'Recording';
    if (normalized === 'stopping') return 'Stopping';
    if (normalized === 'online') return 'Online';
    return 'Offline';
};

const parseCheckedAt = (value?: string | null): number | null => {
    if (!value) return null;
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
};

export const isDeviceRuntimeSnapshotFresh = (
    checkedAt?: string | null,
    staleAfterMs: number = DEVICE_RUNTIME_STALE_MS,
): boolean => {
    const parsed = parseCheckedAt(checkedAt);
    if (parsed === null) return false;
    return (Date.now() - parsed) <= Math.max(1_000, staleAfterMs);
};

export const getDeviceRuntimeStatusFromSnapshot = (
    snapshot?: { status?: string | null; checked_at?: string | null } | null,
): DeviceRuntimeStatus => {
    if (!snapshot) return 'Offline';
    return normalizeDeviceRuntimeStatus(snapshot.status);
};

export const isOnlineDeviceRuntimeStatus = (value?: string | null): boolean => {
    const normalized = normalizeDeviceRuntimeStatus(value);
    return normalized === 'Online' || normalized === 'Starting' || normalized === 'Recording' || normalized === 'Stopping';
};

export const isOnlineDeviceRuntimeSnapshot = (
    snapshot?: { status?: string | null; checked_at?: string | null; online?: boolean } | null,
): boolean => {
    if (!snapshot) return false;
    if (snapshot.online) return true;
    return isOnlineDeviceRuntimeStatus(snapshot.status);
};

export const isReadyDeviceRuntimeStatus = (value?: string | null): boolean => {
    const normalized = normalizeDeviceRuntimeStatus(value);
    return normalized === 'Online' || normalized === 'Recording';
};
