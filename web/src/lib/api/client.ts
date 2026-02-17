import axios, { type AxiosRequestConfig } from 'axios';

export const APP_NAME = import.meta.env.VITE_APP_NAME || 'surgwaze';
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'v1';
const rawBaseUrl = String(import.meta.env.BASE_URL || '/');
const normalizedBaseUrl = rawBaseUrl.replace(/\/+$/, '');
export const APP_BASE_PATH = normalizedBaseUrl
    ? (normalizedBaseUrl.startsWith('/') ? normalizedBaseUrl : `/${normalizedBaseUrl}`)
    : '/';
export const withAppBase = (path: string) => {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    if (APP_BASE_PATH === '/') return normalizedPath;
    if (normalizedPath === APP_BASE_PATH || normalizedPath.startsWith(`${APP_BASE_PATH}/`)) {
        return normalizedPath;
    }
    return `${APP_BASE_PATH}${normalizedPath}`;
};
const defaultApiUrl = `http://${window.location.hostname || 'localhost'}:8001/${APP_NAME}/${APP_VERSION}`;
const runtimeApiUrl = localStorage.getItem('api_url_override') || defaultApiUrl;
export const API_URL = import.meta.env.VITE_API_URL || runtimeApiUrl;
export const WS_URL = API_URL.replace(/^http/i, 'ws');

export interface User {
    id: number;
    username: string;
    full_name: string | null;
    is_superuser: boolean;
    is_active: boolean;
}

export interface Device {
    id: number;
    name: string; // compatibilidade (mesmo valor de model)
    model: string;
    mark_id?: number | null;
    mark_name?: string | null;
    sn: string;
    protocol?: string | null;
    key: string | null;
    place_id: number;
    is_active: boolean;
    status?: string | null;
    last_seen?: string | null;
    created_at: string;
}

export interface DeviceStatus {
    device_id: number;
    online: boolean;
    status: 'Offline' | 'Connecting' | 'Online' | 'Starting' | 'Recording' | 'Stopping' | string;
    stream_url: string | null;
    checked_at: string;
    metadata?: {
        ip?: string;
        key?: string;
        protocol?: string;
        codec?: string;
        resolution?: string;
        audio_codec?: string;
    } | null;
}

export interface Procedure {
    id: number;
    name: string;
    description: string | null;
    is_active: boolean;
}

export interface PlaceApi {
    id: number;
    name: string;
    description: string | null;
    city_id: number;
    is_active: boolean;
}

export interface CityApi {
    id: number;
    name: string;
    uf: string;
    is_active: boolean;
}

export interface MarkApi {
    id: number;
    name: string;
    is_active: boolean;
    created_at?: string | null;
}

export interface Record {
    id: number;
    public_id?: string | null;
    owner_id: number;
    device_id: number;
    place_id: number;
    procedure_id: number | null;
    title: string | null;
    description: string | null;
    start_time: string;
    end_time: string | null;
    seq?: number | null;
    output_path?: string | null;
    file_size_bytes?: number | null;
    transfer_rate_bps?: number | null;
    final_status?: string | null;
    stop_reason?: string | null;
    lifecycle_log?: string | null;
    video_resolution?: string | null;
    video_codec?: string | null;
    audio_codec?: string | null;
}

export interface AppSettings {
    id: number;
    name: string;
    description: string;
    host: string;
    recordings_dir?: string;
    output_format?: 'mp4' | 'mkv' | string;
    scan_start_in?: number;
}

export interface ManagerMetric {
    timestamp: string;
    cpu_percent: number;
    memory_percent: number;
    network: {
        download_bps: number;
        upload_bps: number;
    };
    recordings_active: number;
    publishers_online: number;
    manager_clients: number;
    app_users_online: number;
}

export interface UserNotification {
    id: number;
    code: string;
    user_id: number;
    user_name?: string | null;
    record_id?: number | null;
    record_public_id?: string | null;
    notification_type: string;
    title: string;
    message: string;
    is_read: boolean;
    read_at?: string | null;
    created_at: string;
}

export interface Invite {
    id: number;
    code: string;
    created_by: number;
    used_by?: number | null;
    used_at?: string | null;
    expires_at: string;
    is_active: boolean;
    created_at: string;
}

export interface RegisterPayload {
    invite_code: string;
    username: string;
    password: string;
    full_name: string;
}

interface LoginResponse {
    access_token?: string;
    token_type?: 'bearer' | 'reset';
    reset_required?: boolean;
    reset_token?: string;
}

const api = axios.create({
    baseURL: API_URL,
    headers: { 'Content-Type': 'application/json' },
});

type NetworkBusyListener = (busy: boolean) => void;
type LoaderAxiosRequestConfig = AxiosRequestConfig & {
    skipGlobalLoader?: boolean;
    __trackedGlobalLoader?: boolean;
};

const networkBusyListeners = new Set<NetworkBusyListener>();
let trackedRequests = 0;

const emitNetworkBusy = () => {
    const busy = trackedRequests > 0;
    networkBusyListeners.forEach((listener) => {
        try {
            listener(busy);
        } catch {
            // ignore listener failures
        }
    });
};

export const apiNetworkActivity = {
    subscribe(listener: NetworkBusyListener) {
        networkBusyListeners.add(listener);
        listener(trackedRequests > 0);
        return () => {
            networkBusyListeners.delete(listener);
        };
    },
    isBusy() {
        return trackedRequests > 0;
    },
};

const buildLoaderConfig = (silent?: boolean): AxiosRequestConfig =>
    ({ skipGlobalLoader: !!silent } as unknown as AxiosRequestConfig);

const trackRequestStart = (config: unknown) => {
    const requestConfig = config as LoaderAxiosRequestConfig;
    if (requestConfig.skipGlobalLoader) return;
    requestConfig.__trackedGlobalLoader = true;
    trackedRequests += 1;
    emitNetworkBusy();
};

const trackRequestEnd = (config: unknown) => {
    const requestConfig = config as LoaderAxiosRequestConfig;
    if (!requestConfig?.__trackedGlobalLoader) return;
    requestConfig.__trackedGlobalLoader = false;
    trackedRequests = Math.max(0, trackedRequests - 1);
    emitNetworkBusy();
};

api.interceptors.request.use((config) => {
    trackRequestStart(config);
    const token = session.getToken();
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (response) => {
        trackRequestEnd(response.config);
        return response;
    },
    (error) => {
        trackRequestEnd(error?.config);
        if (error.response?.status === 401) {
            session.clear();
            window.location.href = withAppBase('/login');
        }
        return Promise.reject(error);
    },
);

export const session = {
    setToken(token: string) {
        localStorage.setItem('token', token);
    },
    getToken() {
        return localStorage.getItem('token');
    },
    setUser(user: User) {
        localStorage.setItem('user', JSON.stringify(user));
    },
    getUser(): User | null {
        const raw = localStorage.getItem('user');
        if (!raw) return null;
        try {
            return JSON.parse(raw) as User;
        } catch {
            return null;
        }
    },
    setBoundDevice(device: Device) {
        localStorage.setItem('bound_device', JSON.stringify(device));
        localStorage.setItem('bound_device_ts', String(Date.now()));
    },
    getBoundDevice(): Device | null {
        const raw = localStorage.getItem('bound_device');
        if (!raw) return null;
        const tsRaw = localStorage.getItem('bound_device_ts');
        if (tsRaw) {
            const ageMs = Date.now() - Number(tsRaw);
            if (Number.isFinite(ageMs) && ageMs > 60000) {
                localStorage.removeItem('bound_device');
                localStorage.removeItem('bound_device_ts');
                return null;
            }
        }
        try {
            return JSON.parse(raw) as Device;
        } catch {
            return null;
        }
    },
    clearBoundDevice() {
        localStorage.removeItem('bound_device');
        localStorage.removeItem('bound_device_ts');
    },
    clear() {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        localStorage.removeItem('bound_device');
        localStorage.removeItem('bound_device_ts');
    },
};

export const authAPI = {
    login: (username: string, password: string) => {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);
        return axios.post<LoginResponse>(`${API_URL}/login/access-token`, formData, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });
    },
    resetPassword: (reset_token: string, password: string) =>
        axios.post<LoginResponse>(`${API_URL}/login/reset-password`, { reset_token, password }),
    register: (data: RegisterPayload) =>
        axios.post<{ message: string }>(`${API_URL}/register/`, data),
};

export const usersAPI = {
    getAll: () => api.get<User[]>('/users'),
    getMe: () => api.get<User>('/users/me'),
    update: (id: number, data: Partial<User> & { password?: string }) => api.patch<User>(`/users/${id}`, data),
    updateMe: (data: { full_name?: string | null; password?: string }) => api.patch<User>('/users/me', data),
    uploadPhoto: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        const token = session.getToken();
        return axios
            .post<{ filename: string }>(`${API_URL}/users/me/photo`, formData, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            })
            .catch((error) => {
                if (error.response?.status === 401) {
                    session.clear();
                    window.location.href = withAppBase('/login');
                }
                return Promise.reject(error);
            });
    },
    getPhoto: (userId: number) =>
        api.get<Blob>(`/users/${userId}/photo`, {
            responseType: 'blob',
        }),
    deletePhoto: () => api.delete<{ removed: boolean }>('/users/me/photo'),
};

export const devicesAPI = {
    getAll: (skip = 0, limit = 100) => api.get<Device[]>(`/devices/?skip=${skip}&limit=${limit}`),
    getStatus: (options?: { silent?: boolean }) =>
        api.get<DeviceStatus[]>('/devices/status', buildLoaderConfig(options?.silent)),
    getBindStatus: (deviceId: number) => api.get<DeviceStatus>(`/devices/${deviceId}/bind-status`, { timeout: 8000 }),
    create: (data: {
        name?: string;
        model: string;
        mark_id?: number;
        mark_name?: string;
        sn: string;
        protocol?: string;
        place_id: number;
        is_active?: boolean;
    }) => api.post<Device>('/devices/', data),
    update: (id: number, data: {
        name?: string;
        model?: string;
        mark_id?: number;
        mark_name?: string;
        sn?: string;
        protocol?: string;
        place_id?: number;
        is_active?: boolean;
    }) => api.patch<Device>(`/devices/${id}`, data),
    delete: (id: number) => api.delete<Device>(`/devices/${id}`),
    bind: (key: string) => api.post<Device>('/devices/bind', { key }, { timeout: 10000 }),
    getQRCodeBlob: (id: number) =>
        api.get<Blob>(`/devices/${id}/qrcode`, {
            responseType: 'blob',
        }),
};

export const proceduresAPI = {
    getAll: () => api.get<Procedure[]>('/procedures/'),
};

export const protocolsAPI = {
    getAll: () => api.get<Array<{ id: number; protocol: string; port: number; is_active: boolean }>>('/protocols/'),
    create: (data: { protocol: string; port: number; is_active?: boolean }) => api.post('/protocols/', data),
    update: (id: number, data: { protocol?: string; port?: number; is_active?: boolean }) => api.patch(`/protocols/${id}`, data),
    delete: (id: number) => api.delete(`/protocols/${id}`),
};

export const placesAPI = {
    getAll: () => api.get<PlaceApi[]>('/places/'),
    create: (data: { name: string; description?: string; city_id: number; is_active?: boolean }) => api.post<PlaceApi>('/places/', data),
    update: (id: number, data: { name?: string; description?: string; city_id?: number; is_active?: boolean }) => api.patch<PlaceApi>(`/places/${id}`, data),
    delete: (id: number) => api.delete<PlaceApi>(`/places/${id}`),
};

export const citiesAPI = {
    getAll: () => api.get<CityApi[]>('/cities/'),
    create: (data: { name: string; uf: string; is_active?: boolean }) => api.post<CityApi>('/cities/', data),
    update: (id: number, data: { name?: string; uf?: string; is_active?: boolean }) => api.patch<CityApi>(`/cities/${id}`, data),
    delete: (id: number) => api.delete<CityApi>(`/cities/${id}`),
};

export const marksAPI = {
    getAll: () => api.get<MarkApi[]>('/marks/'),
    create: (data: { name: string; is_active?: boolean }) => api.post<MarkApi>('/marks/', data),
    update: (id: number, data: { name?: string; is_active?: boolean }) => api.patch<MarkApi>(`/marks/${id}`, data),
    delete: (id: number) => api.delete<MarkApi>(`/marks/${id}`),
};

export const recordsAPI = {
    getAll: (options?: { silent?: boolean }) =>
        api.get<Record[]>('/records', buildLoaderConfig(options?.silent)),
    start: (data: { device_id: number; procedure_id?: number; title?: string; description?: string }) => api.post<Record>('/records/start', data),
    stop: (recordId: number, reason = 'user') => api.post<Record>(`/records/stop/${recordId}?reason=${encodeURIComponent(reason)}`),
    update: (recordId: number, data: { title?: string; description?: string }) => api.patch<Record>(`/records/${recordId}`, data),
    delete: (recordId: number) => api.delete<boolean>(`/records/${recordId}`),
};

export const appSettingsAPI = {
    get: () => api.get<AppSettings>('/app-settings/'),
    update: (data: { name?: string; description?: string; host?: string; recordings_dir?: string; output_format?: string; scan_start_in?: number }) =>
        api.patch<AppSettings>('/app-settings/', data),
};

export const managerRuntimeAPI = {
    current: (options?: { silent?: boolean }) =>
        api.get<ManagerMetric>('/manager-runtime/metrics/current', buildLoaderConfig(options?.silent)),
    history: (limit = 120) => api.get<{ items: ManagerMetric[] }>(`/manager-runtime/metrics/history?limit=${limit}`),
};

export const invitesAPI = {
    getAll: () => api.get<Invite[]>('/invites/'),
    create: () => api.post<Invite>('/invites/'),
    revoke: (id: number) => api.delete<Invite>(`/invites/${id}`),
};

export const notificationsAPI = {
    getAll: (options?: { onlyUnread?: boolean; silent?: boolean }) =>
        api.get<UserNotification[]>(
            `/notifications/?only_unread=${options?.onlyUnread ? 'true' : 'false'}`,
            buildLoaderConfig(options?.silent),
        ),
    unreadCount: (options?: { silent?: boolean }) =>
        api.get<{ count: number }>('/notifications/unread-count', buildLoaderConfig(options?.silent)),
    markAsRead: (id: number) => api.patch<UserNotification>(`/notifications/${id}/read`),
    delete: (id: number) => api.delete<UserNotification>(`/notifications/${id}`),
};
