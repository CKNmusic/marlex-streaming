export type MenuKey = 'dashboard' | 'records' | 'devices' | 'marks' | 'users' | 'settings' | 'notifications' | 'profile';
export type DevicesView = 'list' | 'view' | 'edit' | 'new';
export type RecordsView = 'list' | 'view' | 'new';
export type UsersView = 'list' | 'view';
export type SettingsTab = 'app' | 'protocols' | 'places' | 'cities';
export type ActivityFilter = 'all' | 'active' | 'inactive';
export type DeviceActivityFilter = ActivityFilter | 'online';

export type ConfirmState = {
    open: boolean;
    title: string;
    description?: string;
    confirmLabel?: string;
    errorFallback?: string;
    errorMessage?: string;
    loading?: boolean;
    onConfirm?: () => void | Promise<void>;
};

export type StatusLevel = 'error' | 'warn' | 'info';
export type StatusState = { level: StatusLevel; msg: string; time_sec?: number } | null;

export type PlaceItem = {
    id: number;
    name: string;
    description: string;
    cityId: number;
    city: string;
    state: string;
    is_active: boolean;
};
