import type { CityApi, PlaceApi, Procedure, Record as RecordApi, User } from '../../lib/api/client';
import { APP_BASE_PATH } from '../../lib/api/client';
import type { PlaceItem } from './types';

export const mapPlace = (place: PlaceApi, cities: CityApi[]): PlaceItem => {
    const city = cities.find((item) => item.id === place.city_id);
    return {
        id: place.id,
        name: place.name,
        description: place.description || '',
        cityId: place.city_id,
        city: city?.name || '-',
        state: city?.uf || '-',
        is_active: place.is_active ?? true,
    };
};

export const formatDateTime = (
    value: string | null,
    options?: { includeSeconds?: boolean },
) => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    const includeSeconds = options?.includeSeconds ?? true;
    const pad = (input: number) => String(input).padStart(2, '0');
    const day = pad(date.getDate());
    const month = pad(date.getMonth() + 1);
    const year = date.getFullYear();
    const hour = pad(date.getHours());
    const minute = pad(date.getMinutes());
    if (!includeSeconds) {
        return `${day}/${month}/${year}, ${hour}:${minute}`;
    }
    const second = pad(date.getSeconds());
    return `${day}/${month}/${year}, ${hour}:${minute}:${second}`;
};

export const getPlaceLabel = (placesData: PlaceItem[], placeId?: number | null) => {
    if (!placeId) return '-';
    const place = placesData.find((item) => item.id === placeId);
    if (!place) return '-';
    return place.city !== '-' ? `${place.name} - ${place.city}/${place.state}` : place.name;
};

export const getProcedureLabel = (proceduresData: Procedure[], procedureId?: number | null) => {
    if (!procedureId) return '-';
    const procedure = proceduresData.find((item) => item.id === procedureId);
    return procedure ? procedure.name : '-';
};

export const resolveUserLabel = (users: User[], ownerId?: number | null) => {
    if (!ownerId) return '-';
    const found = users.find((item) => item.id === ownerId);
    return found ? `${found.full_name || found.username} (#${found.id})` : `#${ownerId}`;
};

export const getRecordPublicCode = (
    record: Pick<RecordApi, 'id' | 'public_id' | 'owner_id' | 'device_id' | 'start_time'>,
) => {
    if (record.public_id?.trim()) return record.public_id.trim();
    const seed = `${record.id}:${record.owner_id}:${record.device_id}:${record.start_time}`;
    const encoded = typeof btoa === 'function' ? btoa(seed) : seed;
    const normalized = encoded.replace(/[^a-z0-9]/gi, '').toUpperCase();
    return `REC-${(normalized || String(record.id)).slice(0, 16)}`;
};

export const formatStorageSize = (bytes?: number | null) => {
    if (bytes == null || Number.isNaN(bytes)) return '-';
    const gb = bytes / (1024 ** 3);
    if (gb >= 1) {
        return `${gb.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} GB`;
    }
    const mb = bytes / (1024 ** 2);
    return `${mb.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MB`;
};

export const formatTransferRate = (bytesPerSecond?: number | null, options?: { showWaiting?: boolean }) => {
    if (bytesPerSecond == null || Number.isNaN(bytesPerSecond)) return '-';
    const safeValue = Math.max(Number(bytesPerSecond), 0);
    if (safeValue === 0 && options?.showWaiting) return 'Aguardando dados...';
    const gb = safeValue / (1024 ** 3);
    if (gb >= 1) {
        return `${gb.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} GB/s`;
    }
    const mb = safeValue / (1024 ** 2);
    if (mb >= 1) {
        return `${mb.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MB/s`;
    }
    const kb = safeValue / 1024;
    return `${kb.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} KB/s`;
};

export const parseHostConfig = (value?: string) => {
    const fallback = {
        hostname: window.location.hostname || 'localhost',
        port: window.location.port || '3000',
        basePath: APP_BASE_PATH === '/' ? '' : APP_BASE_PATH,
    };
    if (!value) return fallback;
    const trimmed = value.trim();
    if (!trimmed) return fallback;
    try {
        const url = trimmed.startsWith('http://') || trimmed.startsWith('https://')
            ? new URL(trimmed)
            : new URL(`http://${trimmed}`);
        const normalizedPath = url.pathname.replace(/\/+$/, '');
        const basePath = !normalizedPath || normalizedPath === '/'
            ? fallback.basePath
            : (normalizedPath.startsWith('/') ? normalizedPath : `/${normalizedPath}`);
        return {
            hostname: url.hostname || fallback.hostname,
            port: url.port || fallback.port,
            basePath,
        };
    } catch {
        return fallback;
    }
};
