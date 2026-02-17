import { Activity, useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import {
    APP_BASE_PATH,
    APP_NAME,
    APP_VERSION,
    apiNetworkActivity,
    managerRuntimeAPI,
    devicesAPI,
    notificationsAPI,
    proceduresAPI,
    recordsAPI,
    session,
    usersAPI,
    placesAPI,
    protocolsAPI,
    citiesAPI,
    marksAPI,
    appSettingsAPI,
    withAppBase,
} from '../../lib/api/client';
import type { AppSettings, CityApi, Device, DeviceStatus, PlaceApi, ManagerMetric, MarkApi, Procedure, Record as RecordApi, User, UserNotification } from '../../lib/api/client';
import { LogOut, Menu, Settings, User as UserIcon, X } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { ConfirmActionModal } from '../../components/ui/ConfirmActionModal';
import { Modal } from '../../components/ui/Modal';
import { SelectField } from '../../components/ui/SelectField';
import { StatusMsg } from '../../components/ui/StatusMsg';
import { menuItems, settingsMenuItems } from './constants';
import { DashboardPage } from './DashboardPage';
import { DevicesPage } from './DevicesPage';
import { MarksPage } from './MarksPage';
import { NotificationsPage } from './NotificationsPage';
import { ProfilePage } from './ProfilePage';
import { RecordsPage } from './RecordsPage';
import { SettingsPage } from './SettingsPage';
import { UsersPage } from './UsersPage';
import { QrScanModal } from './components/QrScanModal';
import { isBrowserQrScanSupported } from './components/qrScanSupport';
import { extractApiErrorDetail, resolveApiErrorMessage } from './errorMessage';
import { useBoundDeviceSession } from './hooks/useBoundDeviceSession';
import { useRealtimeUpdates } from './hooks/useRealtimeUpdates';
import { validatePasswordForProfileSave } from './profiles/passwordPolicy';
import { getDeviceRuntimeStatusFromSnapshot, isOnlineDeviceRuntimeSnapshot, isReadyDeviceRuntimeStatus } from './status';
import type { ActivityFilter, ConfirmState, DeviceActivityFilter, DevicesView, MenuKey, RecordsView, SettingsTab, StatusLevel, StatusState, UsersView } from './types';
import { getPlaceLabel, mapPlace, parseHostConfig } from './utils';


const RECORD_START_ERROR_TRANSLATIONS: Record<string, string> = {
    'device not found': 'Dispositivo não encontrado.',
    'device sem place': 'Dispositivo sem local vinculado.',
    'device inativo': 'Dispositivo desativado.',
    'device sem key para gerar stream url': 'Dispositivo sem chave para gerar URL de stream.',
    'device offline. aguarde ficar online para iniciar a gravação': 'Dispositivo offline. Aguarde ficar online para iniciar a gravação.',
    'device já está em recording': 'Dispositivo já está gravando.',
    'not authorized': 'Não autorizado.',
    'inactive user': 'Usuário inativo.',
    'could not validate credentials': 'Sessão inválida. Faça login novamente.',
};
const PROTOCOL_DEFAULT_PORTS: Record<string, number> = {
    srt: 8890,
    rtmp: 8554,
};
const normalizeCitySearchText = (value: string) => value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
const pickPreferredProtocol = (list: Array<{ protocol: string; is_active: boolean }>) => {
    const active = list.filter((item) => item.is_active !== false);
    const activeSrt = active.find((item) => item.protocol === 'srt');
    if (activeSrt) return activeSrt.protocol;
    if (active.length) return active[0].protocol;
    const anySrt = list.find((item) => item.protocol === 'srt');
    if (anySrt) return anySrt.protocol;
    return list[0]?.protocol || 'srt';
};
const SCAN_FEEDBACK_STORAGE_KEY = 'scan_bind_feedback';
type ScanFeedbackModalState = {
    open: boolean;
    level: 'info' | 'warn' | 'error';
    message: string;
};
type BlockingErrorModalState = {
    open: boolean;
    title: string;
    message: string;
};

const translateRecordStartError = (message: string) => {
    const normalized = message.trim().replace(/\.$/, '').toLowerCase();
    return RECORD_START_ERROR_TRANSLATIONS[normalized] || message;
};

const resolveRecordStartErrorMessage = (error: unknown) => {
    const detail = extractApiErrorDetail(error);
    if (!detail) return 'Falha ao iniciar gravação.';
    return translateRecordStartError(detail);
};
const isApiUnavailableError = (error: unknown) => {
    const maybeError = error as { response?: unknown };
    return !maybeError?.response;
};
const getDeviceDisplayName = (device?: Partial<Device> | null) => {
    if (!device) return '-';
    const mark = String(device.mark_name || '').trim();
    const model = String(device.model || device.name || '').trim();
    return [mark, model].filter(Boolean).join(' ') || '-';
};
const extractDeviceKeyFromScan = (rawValue: string) => {
    const raw = rawValue.trim();
    if (!raw) return '';

    const fromRawUrl = () => {
        try {
            const parsed = new URL(raw);
            return decodeURIComponent(parsed.searchParams.get('key') || '').trim();
        } catch {
            return '';
        }
    };
    const fromRelativeUrl = () => {
        try {
            const parsed = new URL(raw, window.location.origin);
            return decodeURIComponent(parsed.searchParams.get('key') || '').trim();
        } catch {
            return '';
        }
    };

    const fromQueryToken = () => {
        const directMatch = raw.match(/[?&]key=([^&#\s]+)/i) || raw.match(/\bkey=([A-Za-z0-9_-]+)/i);
        if (!directMatch?.[1]) return '';
        try {
            return decodeURIComponent(directMatch[1]).trim();
        } catch {
            return directMatch[1].trim();
        }
    };

    const fromPlainKey = () => {
        const candidate = raw.replace(/^["']|["']$/g, '').trim();
        if (!/^[A-Za-z0-9_-]{6,64}$/.test(candidate)) return '';
        return candidate;
    };

    return fromRawUrl() || fromRelativeUrl() || fromQueryToken() || fromPlainKey();
};

export const AppPage = () => {
    const [menu, setMenu] = useState<MenuKey>('dashboard');
    const [loading, setLoading] = useState(true);
    const [networkBusy, setNetworkBusy] = useState(false);
    const [showGlobalLoader, setShowGlobalLoader] = useState(false);
    const [apiAvailable, setApiAvailable] = useState(false);
    const [status, setStatus] = useState<StatusState>(null);

    const [user, setUser] = useState<User | null>(session.getUser());
    const [appSettings, setAppSettings] = useState<AppSettings>({
        id: 0,
        name: APP_NAME,
        description: 'Streaming Médico',
        host: `http://${window.location.host || 'localhost:3000'}${APP_BASE_PATH === '/' ? '' : APP_BASE_PATH}`,
        recordings_dir: '/recordings',
        output_format: 'mp4',
        scan_start_in: 60,
    });
    const [profilePhotoUrl, setProfilePhotoUrl] = useState('');
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const profilePhotoObjectUrlRef = useRef<string | null>(null);
    const [users, setUsers] = useState<User[]>([]);
    const [devices, setDevices] = useState<Device[]>([]);
    const [deviceStatus, setDeviceStatus] = useState<Record<number, DeviceStatus>>({});
    const [managerMetrics, setManagerMetrics] = useState<ManagerMetric | null>(null);
    const [cities, setCities] = useState<CityApi[]>([]);
    const [placesApi, setPlacesApi] = useState<PlaceApi[]>([]);
    const [records, setRecords] = useState<RecordApi[]>([]);
    const [notifications, setNotifications] = useState<UserNotification[]>([]);
    const [procedures, setProcedures] = useState<Procedure[]>([]);
    const [protocols, setProtocols] = useState<Array<{ id: number; protocol: string; port: number; is_active: boolean }>>([]);
    const [marks, setMarks] = useState<MarkApi[]>([]);

    const [devicesView, setDevicesView] = useState<DevicesView>('list');
    const [recordsView, setRecordsView] = useState<RecordsView>('list');
    const [usersView, setUsersView] = useState<UsersView>('list');
    const [showUserHistory, setShowUserHistory] = useState(false);

    const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
    const [selectedRecord, setSelectedRecord] = useState<RecordApi | null>(null);
    const [selectedUser, setSelectedUser] = useState<User | null>(null);
    const [passwordResetUsers, setPasswordResetUsers] = useState<number[]>([]);

    const [deviceForm, setDeviceForm] = useState({ mark_id: '', model: '', sn: '', place_id: '', protocol: '' });
    const [recordForm, setRecordForm] = useState({ title: '', description: '', procedure_id: '', device_id: '' });
    const [recordEditForm, setRecordEditForm] = useState({ title: '', description: '' });
    const [settingsForm, setSettingsForm] = useState({ full_name: '', password: '', password_confirm: '' });
    const [appSettingsForm, setAppSettingsForm] = useState({ name: '', description: '', recordings_dir: String(appSettings.recordings_dir), scan_start_in: Number(appSettings.scan_start_in) });
    const [userSearch, setUserSearch] = useState('');
    const [userActivityFilter, setUserActivityFilter] = useState<ActivityFilter>('all');
    const [deviceSearch, setDeviceSearch] = useState('');
    const [deviceActivityFilter, setDeviceActivityFilter] = useState<DeviceActivityFilter>('all');
    const [recordSearch, setRecordSearch] = useState('');
    const [recordActivityFilter, setRecordActivityFilter] = useState<ActivityFilter>('all');
    const [deviceCitySearch, setDeviceCitySearch] = useState('');
    const [placeSearch, setPlaceSearch] = useState('');
    const [settingsTab, setSettingsTab] = useState<SettingsTab>('app');
    const [publicHost, setPublicHost] = useState<string>('');
    const [protocolSearch, setProtocolSearch] = useState('');
    const [showInactiveProtocols, setShowInactiveProtocols] = useState(false);
    const [placeTabSearch, setPlaceTabSearch] = useState('');
    const [showInactivePlaces, setShowInactivePlaces] = useState(false);
    const [citySearch, setCitySearch] = useState('');
    const [showInactiveCities, setShowInactiveCities] = useState(false);
    const [markSearch, setMarkSearch] = useState('');
    const [showInactiveMarks, setShowInactiveMarks] = useState(false);
    const [cptecApiOnline, setCptecApiOnline] = useState<boolean | null>(null);

    const [savingDevice, setSavingDevice] = useState(false);
    const [recordingBusy, setRecordingBusy] = useState(false);
    const [savingRecord, setSavingRecord] = useState(false);
    const [savingSettings, setSavingSettings] = useState(false);
    const [loadingNotifications, setLoadingNotifications] = useState(false);
    const [showRecordModal, setShowRecordModal] = useState(false);
    const [scanStartCountdown, setScanStartCountdown] = useState(60);
    const [showDevicePrintModal, setShowDevicePrintModal] = useState(false);
    const [showDashboardScanModal, setShowDashboardScanModal] = useState(false);
    const [scanFeedbackModal, setScanFeedbackModal] = useState<ScanFeedbackModalState>({
        open: false,
        level: 'info',
        message: '',
    });
    const [blockingErrorModal, setBlockingErrorModal] = useState<BlockingErrorModalState>({
        open: false,
        title: '',
        message: '',
    });

    const [qrImageUrl, setQrImageUrl] = useState('');
    const [showQrCode, setShowQrCode] = useState(false);
    const [confirm, setConfirm] = useState<ConfirmState>({ open: false, title: '' });

    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

    const handleMobileMenuSelect = (key: MenuKey) => {
        setMenu(key);
        setMobileMenuOpen(false);
    };

    const handleMobileSettingsSelect = (tab: SettingsTab) => {
        setMenu('settings');
        setSettingsTab(tab);
        setMobileMenuOpen(false);
    };

    const isAdmin = !!user?.is_superuser;
    const { boundDevice, invalidateScan } = useBoundDeviceSession();
    const openRecords = useMemo(() => records.filter((record) => !record.end_time), [records]);
    const unreadNotificationsCount = useMemo(
        () => notifications.filter((notification) => !notification.is_read).length,
        [notifications],
    );
    const places = useMemo(() => placesApi.map((place) => mapPlace(place, cities)), [placesApi, cities]);
    const currentOpenRecord = useMemo(() => {
        if (isAdmin) {
            return openRecords[0] || null;
        }
        return openRecords.find((record) => record.owner_id === user?.id) || null;
    }, [isAdmin, openRecords, user?.id]);
    const boundDeviceRuntimeStatus = useMemo(() => {
        if (!boundDevice) return 'Offline';
        return getDeviceRuntimeStatusFromSnapshot(deviceStatus[boundDevice.id]);
    }, [boundDevice, deviceStatus]);
    const isBoundDeviceReady = isReadyDeviceRuntimeStatus(boundDeviceRuntimeStatus);
    const hostInfo = useMemo(() => parseHostConfig(publicHost || appSettings.host), [publicHost, appSettings.host]);
    const scanStartLimitSec = useMemo(() => {
        const raw = Number(appSettings.scan_start_in || appSettingsForm.scan_start_in || 60);
        if (!Number.isFinite(raw)) return 60;
        return Math.max(5, Math.min(600, Math.floor(raw)));
    }, [appSettings.scan_start_in, appSettingsForm.scan_start_in]);
    const dashboardScanSupported = useMemo(() => isBrowserQrScanSupported(), []);
    const recordSyncTimerRef = useRef<number | null>(null);
    const hasBootstrappedRef = useRef(false);
    const bootstrapInFlightRef = useRef(false);
    const qrImageObjectUrlRef = useRef<string | null>(null);
    const realtimeScopeKey = useMemo(() => {
        if (!user) return 'anon';
        if (user.is_superuser) return `admin:${user.id}`;
        return `user:${user.id}:device:${boundDevice?.id || 0}`;
    }, [user, boundDevice?.id]);
    const loadedMenusRef = useRef<Record<MenuKey, boolean>>({
        dashboard: false,
        records: false,
        devices: false,
        marks: false,
        users: false,
        settings: false,
        notifications: false,
        profile: false,
    });

    const loadRecords = useCallback(async (options?: { silent?: boolean }) => {
        const response = await recordsAPI.getAll({ silent: options?.silent });
        setRecords(response.data);
    }, []);

    const loadNotifications = useCallback(async (options?: { silent?: boolean }) => {
        if (!options?.silent) {
            setLoadingNotifications(true);
        }
        try {
            const response = await notificationsAPI.getAll({ silent: options?.silent });
            setNotifications(response.data);
        } catch (error) {
            if (isApiUnavailableError(error)) {
                setApiAvailable(false);
            }
            if (!options?.silent) {
                setStatus({ level: 'error', msg: 'Falha ao carregar notificações.', time_sec: 3 });
            }
        } finally {
            if (!options?.silent) {
                setLoadingNotifications(false);
            }
        }
    }, []);

    const scheduleRecordStatusSync = useCallback(() => {
        if (recordSyncTimerRef.current !== null) return;
        recordSyncTimerRef.current = window.setTimeout(() => {
            recordSyncTimerRef.current = null;
            void loadRecords();
        }, 400);
    }, [loadRecords]);

    const handleRealtimeRecordEnded = useCallback(() => {
        // Notificações de gravação são centralizadas no Perfil.
    }, []);

    useEffect(() => {
        if (!hasBootstrappedRef.current) {
            hasBootstrappedRef.current = true;
            void bootstrap();
        }
        try {
            const raw = localStorage.getItem(SCAN_FEEDBACK_STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw) as { level?: 'info' | 'warn' | 'error'; message?: string };
                if (parsed.message) {
                    setScanFeedbackModal({
                        open: true,
                        level: parsed.level || 'info',
                        message: parsed.message,
                    });
                }
            }
        } catch {
            // ignore parse/storage failures
        } finally {
            localStorage.removeItem(SCAN_FEEDBACK_STORAGE_KEY);
        }
        return () => {
            if (qrImageObjectUrlRef.current) {
                URL.revokeObjectURL(qrImageObjectUrlRef.current);
                qrImageObjectUrlRef.current = null;
            }
            if (profilePhotoObjectUrlRef.current) {
                URL.revokeObjectURL(profilePhotoObjectUrlRef.current);
            }
            if (recordSyncTimerRef.current !== null) {
                window.clearTimeout(recordSyncTimerRef.current);
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        const unsubscribe = apiNetworkActivity.subscribe(setNetworkBusy);
        return () => {
            unsubscribe();
        };
    }, []);

    useEffect(() => {
        if (mobileMenuOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        const handleResize = () => {
            if (window.innerWidth >= 768) {
                setMobileMenuOpen(false);
            }
        };
        window.addEventListener('resize', handleResize);
        return () => {
            document.body.style.overflow = '';
            window.removeEventListener('resize', handleResize);
        };
    }, [mobileMenuOpen]);

    useEffect(() => {
        let timerId: number | null = null;
        if (networkBusy && !loading) {
            timerId = window.setTimeout(() => {
                setShowGlobalLoader(true);
            }, 180);
        } else {
            setShowGlobalLoader(false);
        }
        return () => {
            if (timerId !== null) {
                window.clearTimeout(timerId);
            }
        };
    }, [networkBusy, loading]);

    useEffect(() => {
        if (boundDevice) {
            setShowRecordModal(true);
        } else {
            setShowRecordModal(false);
        }
    }, [boundDevice]);

    useEffect(() => {
        if (!showRecordModal || procedures.length > 0) return;
        void loadProcedures();
    }, [showRecordModal, procedures.length]);

    useEffect(() => {
        if (!showRecordModal || !boundDevice || isAdmin) return;
        setScanStartCountdown(scanStartLimitSec);
        let remaining = scanStartLimitSec;
        const intervalId = window.setInterval(() => {
            remaining -= 1;
            setScanStartCountdown(remaining);
            if (remaining > 0) return;
            window.clearInterval(intervalId);
            invalidateScan();
            setShowRecordModal(false);
            setStatus({ level: 'warn', msg: `Tempo do scan expirou (${scanStartLimitSec}s). Escaneie novamente.`, time_sec: 3 });
        }, 1000);
        return () => {
            window.clearInterval(intervalId);
        };
    }, [showRecordModal, boundDevice, isAdmin, scanStartLimitSec, invalidateScan]);

    const showStatus = useCallback((level: StatusLevel, msg: string, time_sec = 3) => {
        setStatus({ level, msg, time_sec });
    }, []);

    const clearStatus = useCallback(() => {
        setStatus(null);
    }, []);

    const closeConfirmModal = useCallback(() => {
        setConfirm({ open: false, title: '' });
    }, []);

    const handleConfirmAction = useCallback(async () => {
        if (!confirm.open || !confirm.onConfirm || confirm.loading) return;
        setConfirm((state) => ({ ...state, loading: true, errorMessage: '' }));
        try {
            await confirm.onConfirm();
            closeConfirmModal();
        } catch (error) {
            setConfirm((state) => ({
                ...state,
                loading: false,
                errorMessage: resolveApiErrorMessage(error, state.errorFallback || 'Falha ao confirmar ação.'),
            }));
        }
    }, [confirm, closeConfirmModal]);

    const handleRealtimeConnectionState = useCallback((connected: boolean) => {
        if (!connected) return;
        setApiAvailable(true);
    }, []);

    useRealtimeUpdates({
        user,
        enabled: !loading && !!user,
        scopeKey: realtimeScopeKey,
        setDeviceStatus,
        setRecords,
        setManagerMetrics,
        onRecordEnded: handleRealtimeRecordEnded,
        onRecordStatusSync: scheduleRecordStatusSync,
        onConnectionStateChange: handleRealtimeConnectionState,
    });

    const searchCptecCities = async (cityName: string) => {
        const trimmed = cityName.trim();
        if (!trimmed) return [] as Array<{ name: string; uf: string }>;
        const normalizedQuery = normalizeCitySearchText(trimmed);
        const queryVariants = Array.from(new Set([
            trimmed,
            trimmed.toLowerCase(),
            normalizedQuery,
        ])).filter(Boolean);
        const parsedItems: Array<{ name: string; uf: string }> = [];
        let hasSuccessfulResponse = false;

        for (const query of queryVariants) {
            try {
                const response = await fetch(`https://brasilapi.com.br/api/cptec/v1/cidade/${encodeURIComponent(query)}`);
                if (!response.ok) continue;
                const data = await response.json();
                if (!Array.isArray(data)) continue;
                hasSuccessfulResponse = true;
                data.forEach((item) => {
                    const name = String(item.name || item.nome || item.city || '').trim();
                    const state = String(item.state || item.estado || item.uf || '').trim().toUpperCase();
                    if (!name || !state) return;
                    parsedItems.push({ name, uf: state });
                });
            } catch {
                // Tentaremos próximo variante de consulta.
            }
        }

        if (!hasSuccessfulResponse) {
            setCptecApiOnline(false);
            return [] as Array<{ name: string; uf: string }>;
        }

        setCptecApiOnline(true);
        const deduped = Array.from(
            new Map(parsedItems.map((item) => [`${normalizeCitySearchText(item.name)}|${item.uf}`, item])).values(),
        );
        return deduped.filter((item) => normalizeCitySearchText(item.name).includes(normalizedQuery));
    };
    const fetchCptecCity = async (cityName: string, uf?: string) => {
        const found = await searchCptecCities(cityName);
        if (!found.length) return null;
        const normalizedUf = uf?.trim().toLowerCase();
        if (!normalizedUf) return found[0];
        return found.find((item) => item.uf.toLowerCase() === normalizedUf) || null;
    };

    const bootstrap = async () => {
        if (bootstrapInFlightRef.current) return;
        bootstrapInFlightRef.current = true;
        setLoading(true);
        clearStatus();
        try {
            loadedMenusRef.current = {
                dashboard: false,
                records: false,
                devices: false,
                marks: false,
                users: false,
                settings: false,
                notifications: false,
                profile: false,
            };
            const meResponse = await usersAPI.getMe();
            setApiAvailable(true);
            setUser(meResponse.data);
            session.setUser(meResponse.data);
            setSettingsForm({
                full_name: meResponse.data.full_name || '',
                password: '',
                password_confirm: '',
            });

            await Promise.all([
                loadProfilePhoto(meResponse.data.id),
                loadAppSettings(),
            ]);

            const dashboardLoads: Array<Promise<unknown>> = [
                loadRecords({ silent: true }),
            ];
            if (meResponse.data.is_superuser) {
                dashboardLoads.push(
                    loadManagerMetrics(),
                );
            }
            await Promise.all(dashboardLoads);
            loadedMenusRef.current.dashboard = true;
            loadedMenusRef.current.profile = true;
        } catch (error) {
            if (isApiUnavailableError(error)) {
                setApiAvailable(false);
            }
            showStatus('error', 'Falha ao carregar dados do app.');
        } finally {
            setLoading(false);
            bootstrapInFlightRef.current = false;
        }
    };

    const loadUsers = async () => {
        const response = await usersAPI.getAll();
        setUsers(response.data);
    };

    const loadDevices = async () => {
        const response = await devicesAPI.getAll();
        setDevices(response.data);
    };

    const loadManagerMetrics = useCallback(async () => {
        try {
            const response = await managerRuntimeAPI.current({ silent: true });
            setManagerMetrics(response.data);
        } catch (error) {
            if (isApiUnavailableError(error)) {
                setApiAvailable(false);
            }
            setManagerMetrics(null);
        }
    }, []);
    const ensureMenuData = useEffectEvent(async (targetMenu: MenuKey) => {
        if (!user) return;
        if (loadedMenusRef.current[targetMenu]) return;

        if (targetMenu === 'dashboard') {
            const jobs: Array<Promise<unknown>> = [
                loadRecords({ silent: true }),
            ];
            if (user.is_superuser) {
                jobs.push(loadManagerMetrics());
            }
            await Promise.all(jobs);
            loadedMenusRef.current.dashboard = true;
            return;
        }

        if (targetMenu === 'records') {
            const jobs: Array<Promise<unknown>> = [
                loadRecords({ silent: true }),
                loadProcedures(),
                loadPlaces(),
            ];
            if (user.is_superuser) {
                jobs.push(loadDevices(), loadUsers());
            }
            await Promise.all(jobs);
            loadedMenusRef.current.records = true;
            return;
        }

        if (targetMenu === 'devices' && user.is_superuser) {
            await Promise.all([
                loadDevices(),
                loadPlaces(),
                loadCities(),
                loadMarks(),
                loadProtocols(),
            ]);
            loadedMenusRef.current.devices = true;
            return;
        }

        if (targetMenu === 'marks' && user.is_superuser) {
            await loadMarks();
            loadedMenusRef.current.marks = true;
            return;
        }

        if (targetMenu === 'users' && user.is_superuser) {
            await Promise.all([
                loadUsers(),
                loadRecords({ silent: true }),
                loadPlaces(),
            ]);
            loadedMenusRef.current.users = true;
            return;
        }

        if (targetMenu === 'settings' && user.is_superuser) {
            await Promise.all([
                loadAppSettings(),
                loadProtocols(),
                loadPlaces(),
                loadCities(),
            ]);
            loadedMenusRef.current.settings = true;
            return;
        }

        if (targetMenu === 'notifications') {
            await loadNotifications({ silent: true });
            loadedMenusRef.current.notifications = true;
            return;
        }

        if (targetMenu === 'profile') {
            loadedMenusRef.current.profile = true;
        }
    });

    useEffect(() => {
        if (loading || !apiAvailable || !user) return;
        void ensureMenuData(menu).catch((error) => {
            if (isApiUnavailableError(error)) {
                setApiAvailable(false);
            }
            showStatus('error', 'Falha ao carregar dados desta tela.');
        });
    }, [loading, apiAvailable, user, menu, showStatus]);

    const loadPlaces = async () => {
        const response = await placesAPI.getAll();
        setPlacesApi(response.data);
    };

    const loadCities = async () => {
        const response = await citiesAPI.getAll();
        setCities(response.data);
    };

    const loadAppSettings = async () => {
        const response = await appSettingsAPI.get();
        setAppSettings(response.data);
        setAppSettingsForm({
            name: response.data.name,
            description: response.data.description,
            recordings_dir: response.data.recordings_dir || '/recordings',
            scan_start_in: Number(response.data.scan_start_in || 60),
        });
        setPublicHost(response.data.host);
    };

    const handleUpdateOutputFormat = async (nextFormat: 'mp4' | 'mkv') => {
        try {
            const response = await appSettingsAPI.update({ output_format: nextFormat });
            setAppSettings(response.data);
            showStatus('info', `Formato padrão alterado para ${String(response.data.output_format || nextFormat).toUpperCase()}.`);
        } catch {
            showStatus('error', 'Falha ao alterar formato de saída.');
        }
    };

    const loadProcedures = async () => {
        const response = await proceduresAPI.getAll();
        setProcedures(response.data);
    };

    const loadProtocols = async () => {
        const response = await protocolsAPI.getAll();
        setProtocols(response.data);
    };

    const loadMarks = async () => {
        const response = await marksAPI.getAll();
        setMarks(response.data);
    };

    const handleLogout = () => {
        session.clear();
        window.location.href = withAppBase('/login');
    };

    const setProfilePhotoObjectUrl = (url: string) => {
        if (profilePhotoObjectUrlRef.current) {
            URL.revokeObjectURL(profilePhotoObjectUrlRef.current);
            profilePhotoObjectUrlRef.current = null;
        }
        if (url) {
            profilePhotoObjectUrlRef.current = url;
        }
        setProfilePhotoUrl(url);
    };

    const clearProfilePhoto = () => {
        setProfilePhotoObjectUrl('');
    };

    const loadProfilePhoto = async (userId: number) => {
        try {
            const response = await usersAPI.getPhoto(userId);
            if (!response.data || response.data.size === 0) {
                clearProfilePhoto();
                return;
            }
            const url = URL.createObjectURL(response.data);
            setProfilePhotoObjectUrl(url);
        } catch {
            clearProfilePhoto();
        }
    };

    const handleProfilePhotoClick = () => {
        fileInputRef.current?.click();
    };

    const handleProfilePhotoChange = async (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file || !user) return;
        if (!file.type.startsWith('image/')) {
            showStatus('error', 'Formato de imagem inválido.');
            return;
        }
        clearStatus();
        try {
            await usersAPI.uploadPhoto(file);
            await loadProfilePhoto(user.id);
            showStatus('info', 'Foto de perfil atualizada.');
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao enviar foto de perfil.'));
        } finally {
            event.target.value = '';
        }
    };

    const handleRemoveProfilePhoto = async () => {
        if (!user) return;
        clearStatus();
        try {
            await usersAPI.deletePhoto();
            clearProfilePhoto();
            showStatus('info', 'Foto de perfil removida.');
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao remover foto de perfil.'));
        }
    };

    const clearQrImage = () => {
        setQrImageUrl((previous) => {
            if (previous) {
                URL.revokeObjectURL(previous);
            }
            qrImageObjectUrlRef.current = null;
            return '';
        });
        setShowQrCode(false);
    };

    const openDeviceView = (device: Device) => {
        const selectedPlace = places.find((item) => item.id === device.place_id);
        const fallbackProtocol = pickPreferredProtocol(protocols);
        clearQrImage();
        setSelectedDevice(device);
        setDevicesView('view');
        setDeviceForm({
            mark_id: device.mark_id ? String(device.mark_id) : '',
            model: String(device.model || device.name || '').trim(),
            sn: device.sn,
            place_id: device.place_id ? String(device.place_id) : '',
            protocol: String(device.protocol || fallbackProtocol || '').trim().toLowerCase(),
        });
        setPlaceSearch(selectedPlace ? `${selectedPlace.name} - ${selectedPlace.city}/${selectedPlace.state}` : '');
        setDeviceCitySearch(selectedPlace ? `${selectedPlace.city}/${selectedPlace.state}` : '');
    };

    const openDeviceEdit = (device: Device) => {
        const selectedPlace = places.find((item) => item.id === device.place_id);
        const fallbackProtocol = pickPreferredProtocol(protocols);
        clearQrImage();
        setSelectedDevice(device);
        setDevicesView('edit');
        setDeviceForm({
            mark_id: device.mark_id ? String(device.mark_id) : '',
            model: String(device.model || device.name || '').trim(),
            sn: device.sn,
            place_id: device.place_id ? String(device.place_id) : '',
            protocol: String(device.protocol || fallbackProtocol || '').trim().toLowerCase(),
        });
        setPlaceSearch(selectedPlace ? `${selectedPlace.name} - ${selectedPlace.city}/${selectedPlace.state}` : '');
        setDeviceCitySearch(selectedPlace ? `${selectedPlace.city}/${selectedPlace.state}` : '');
    };

    const openDeviceNew = () => {
        const fallbackProtocol = pickPreferredProtocol(protocols);
        clearQrImage();
        setSelectedDevice(null);
        setDeviceForm({
            mark_id: '',
            model: '',
            sn: '',
            place_id: '',
            protocol: String(fallbackProtocol || '').trim().toLowerCase(),
        });
        setPlaceSearch('');
        setDeviceCitySearch('');
        setDevicesView('new');
    };

    const handleSaveDevice = async (event: FormEvent) => {
        event.preventDefault();
        setSavingDevice(true);
        clearStatus();
        try {
            const selectedProtocol = String(deviceForm.protocol || '').trim().toLowerCase();
            const model = String(deviceForm.model || '').trim();
            const markId = Number(deviceForm.mark_id || 0);
            if (!markId) {
                showStatus('error', 'Selecione a marca do dispositivo.');
                return;
            }
            if (!model) {
                showStatus('error', 'Informe o modelo do dispositivo.');
                return;
            }
            if (selectedDevice) {
                if (!selectedProtocol) {
                    showStatus('error', 'Selecione um protocolo.');
                    return;
                }
                await devicesAPI.update(selectedDevice.id, {
                    mark_id: markId,
                    model,
                    protocol: selectedProtocol,
                    place_id: deviceForm.place_id ? Number(deviceForm.place_id) : undefined,
                });
            } else {
                if (!deviceForm.place_id) {
                    showStatus('error', 'Selecione um place.');
                    return;
                }
                if (!selectedProtocol) {
                    showStatus('error', 'Selecione um protocolo.');
                    return;
                }
                await devicesAPI.create({
                    mark_id: markId,
                    model,
                    sn: deviceForm.sn,
                    protocol: selectedProtocol,
                    place_id: Number(deviceForm.place_id),
                    is_active: true,
                });
            }

            await loadDevices();
            setDevicesView('list');
        } catch (error) {
            const message = resolveApiErrorMessage(error, 'Falha ao salvar dispositivo.');
            setBlockingErrorModal({
                open: true,
                title: 'Erro ao salvar dispositivo',
                message,
            });
        } finally {
            setSavingDevice(false);
        }
    };

    const confirmDeactivateDevice = (device: Device) => {
        setConfirm({
            open: true,
            title: 'Desativar dispositivo',
            description: `Desativar ${getDeviceDisplayName(device)}?`,
            confirmLabel: 'Desativar',
            errorFallback: 'Falha ao desativar dispositivo.',
            onConfirm: async () => {
                await devicesAPI.update(device.id, { is_active: false });
                await loadDevices();
            },
        });
    };

    const confirmDeleteDevice = (device: Device) => {
        setConfirm({
            open: true,
            title: 'Excluir dispositivo',
            description: `Excluir ${getDeviceDisplayName(device)}?`,
            confirmLabel: 'Excluir',
            errorFallback: 'Falha ao excluir dispositivo.',
            onConfirm: async () => {
                await devicesAPI.delete(device.id);
                await loadDevices();
            },
        });
    };

    const generateQrForDevice = async (
        device: Device,
        options?: { show?: boolean; silent?: boolean },
    ) => {
        if (!device) return '';
        if (!options?.silent) {
            clearStatus();
        }
        try {
            const response = await devicesAPI.getQRCodeBlob(device.id);
            const nextUrl = URL.createObjectURL(response.data);
            const previousUrl = qrImageObjectUrlRef.current;
            qrImageObjectUrlRef.current = nextUrl;
            setQrImageUrl(nextUrl);
            if (previousUrl && previousUrl !== nextUrl) {
                URL.revokeObjectURL(previousUrl);
            }
            if (options?.show) {
                setShowQrCode(true);
            }
            return nextUrl;
        } catch {
            if (!options?.silent) {
                showStatus('error', 'Falha ao gerar QR Code.');
            }
            return '';
        }
    };

    const openRecordNew = () => {
        const defaultDeviceId = isAdmin ? '' : String(boundDevice?.id || '');
        setRecordForm({ title: '', description: '', procedure_id: '', device_id: defaultDeviceId });
        setRecordsView('new');
    };

    const openRecordView = (record: RecordApi) => {
        setSelectedRecord(record);
        setRecordEditForm({ title: record.title || '', description: record.description || '' });
        setRecordsView('view');
    };

    const openRecordViewFromDashboard = (record: RecordApi) => {
        setMenu('records');
        openRecordView(record);
    };

    const markNotificationAsRead = async (notificationId: number) => {
        try {
            const response = await notificationsAPI.markAsRead(notificationId);
            setNotifications((previous) => previous.map((item) => (
                item.id === notificationId ? response.data : item
            )));
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao marcar notificação como lida.'));
        }
    };

    const deleteNotification = async (notificationId: number) => {
        try {
            await notificationsAPI.delete(notificationId);
            setNotifications((previous) => previous.filter((item) => item.id !== notificationId));
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao excluir notificação.'));
        }
    };

    const openRecordFromNotification = async (recordId?: number | null) => {
        if (!recordId) return;
        let target = records.find((record) => record.id === recordId) || null;
        if (!target) {
            try {
                const response = await recordsAPI.getAll({ silent: true });
                setRecords(response.data);
                target = response.data.find((record) => record.id === recordId) || null;
            } catch {
                // keep current view
            }
        }
        if (!target) {
            showStatus('warn', 'Gravação da notificação não está mais disponível.');
            return;
        }
        setMenu('records');
        openRecordView(target);
    };

    const openRecordsListFromDashboard = (filter: ActivityFilter) => {
        setRecordSearch('');
        setRecordActivityFilter(filter);
        setRecordsView('list');
        setMenu('records');
    };

    const openUsersListFromDashboard = (filter: ActivityFilter) => {
        setUserSearch('');
        setUserActivityFilter(filter);
        setUsersView('list');
        setShowUserHistory(false);
        setMenu('users');
    };

    const openDevicesListFromDashboard = (filter: DeviceActivityFilter) => {
        setDeviceSearch('');
        setDeviceActivityFilter(filter);
        setDevicesView('list');
        setMenu('devices');
    };

    const handleOpenDashboardScan = () => {
        if (!dashboardScanSupported) {
            showStatus('warn', 'Leitura por câmera não suportada neste navegador.');
            return;
        }
        setShowDashboardScanModal(true);
    };

    const handleCloseDashboardScan = () => {
        setShowDashboardScanModal(false);
    };

    const handleDetectedDashboardScan = (rawValue: string) => {
        const key = extractDeviceKeyFromScan(rawValue);
        if (!key) {
            showStatus('error', 'QR inválido. Use um QR com /scan?key=... ou a key do dispositivo.');
            return;
        }
        setShowDashboardScanModal(false);
        window.location.assign(withAppBase(`/scan?key=${encodeURIComponent(key)}`));
    };

    const handleStartRecord = async (event: FormEvent) => {
        event.preventDefault();
        const deviceId = isAdmin ? Number(recordForm.device_id || 0) : boundDevice?.id;
        if (!deviceId) {
            showStatus('error', isAdmin ? 'Selecione um dispositivo para iniciar.' : 'Scan expirado. Escaneie novamente o QR Code.');
            return;
        }
        if (!recordForm.procedure_id) {
            showStatus('error', 'Selecione um procedimento.');
            return;
        }
        if (!isAdmin && !isBoundDeviceReady) {
            showStatus('warn', 'Dispositivo ainda conectando. Aguarde status Online para iniciar.');
            return;
        }

        setRecordingBusy(true);
        clearStatus();
        try {
            await recordsAPI.start({
                device_id: deviceId,
                title: recordForm.title || undefined,
                description: recordForm.description || undefined,
                procedure_id: recordForm.procedure_id ? Number(recordForm.procedure_id) : undefined,
            });
            await loadRecords();
            setMenu('dashboard');
            if (!isAdmin) {
                invalidateScan();
                setShowRecordModal(false);
            }
            setRecordsView('list');
        } catch (error) {
            showStatus('error', resolveRecordStartErrorMessage(error));
        } finally {
            setRecordingBusy(false);
        }
    };

    const handleStopRecord = async (recordId: number) => {
        clearStatus();
        setRecordingBusy(true);
        try {
            const response = await recordsAPI.stop(recordId, user?.is_superuser ? 'master' : 'user');
            await loadRecords();
            setSelectedRecord(response.data);
            setRecordEditForm({
                title: response.data.title || '',
                description: response.data.description || '',
            });
            setRecordsView('view');
            setMenu('records');
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao parar gravação.'));
        } finally {
            setRecordingBusy(false);
        }
    };

    const handleSaveRecordEdit = async (event: FormEvent) => {
        event.preventDefault();
        if (!selectedRecord) return false;
        setSavingRecord(true);
        clearStatus();
        try {
            const response = await recordsAPI.update(selectedRecord.id, {
                title: recordEditForm.title,
                description: recordEditForm.description,
            });
            await loadRecords();
            setSelectedRecord(response.data);
            setRecordEditForm({
                title: response.data.title || '',
                description: response.data.description || '',
            });
            return true;
        } catch {
            showStatus('error', 'Falha ao salvar gravação.');
            return false;
        } finally {
            setSavingRecord(false);
        }
    };

    const handleSaveSettings = async (event: FormEvent) => {
        event.preventDefault();
        setSavingSettings(true);
        clearStatus();
        try {
            const payload: { full_name?: string; password?: string } = {};
            if (settingsForm.full_name.trim()) {
                payload.full_name = settingsForm.full_name.trim();
            }
            if (settingsForm.password.trim()) {
                const validation = validatePasswordForProfileSave(
                    settingsForm.password,
                    settingsForm.password_confirm,
                    { username: user?.username, fullName: settingsForm.full_name || user?.full_name || '' },
                );
                if (!validation.valid) {
                    showStatus('error', validation.message || 'Senha inválida.');
                    return;
                }
                payload.password = settingsForm.password;
            }
            if (!payload.full_name && !payload.password) {
                showStatus('error', 'Informe o nome ou a nova senha.');
                return;
            }
            const response = await usersAPI.updateMe(payload);
            session.setUser(response.data);
            setUser(response.data);
            setSettingsForm({
                full_name: response.data.full_name || '',
                password: '',
                password_confirm: '',
            });
            showStatus('info', 'Configurações salvas.');
        } catch {
            showStatus('error', 'Falha ao salvar configurações.');
        } finally {
            setSavingSettings(false);
        }
    };

    const handleCancelSettings = () => {
        setSettingsForm({
            full_name: user?.full_name || '',
            password: '',
            password_confirm: '',
        });
        clearStatus();
        setMenu('notifications');
    };

    const handlePrintDevice = async (mode: 'qr' | 'details') => {
        if (!selectedDevice) return;
        let qrUrl = qrImageUrl;
        if (!qrUrl) {
            qrUrl = await generateQrForDevice(selectedDevice, { silent: true });
        }
        if (mode === 'qr' && !qrUrl) {
            showStatus('warn', 'QR Code indisponível para impressão.');
            return;
        }
        const placeLabel = getPlaceLabel(places, selectedDevice.place_id);
        const selectedProtocol = selectedDevice.protocol || '-';
        const protocolListBlock = deviceProtocolPushList.length
            ? `<div><strong>Protocolos:</strong></div>
               <ul style="margin: 6px 0 0; padding-left: 18px;">
                   ${deviceProtocolPushList.map((item) => (
                       `<li style="margin-bottom: 4px;"><strong>${item.protocol.toUpperCase()}:${item.port}</strong> - ${item.url}</li>`
                   )).join('')}
               </ul>`
            : '<div><strong>Protocolos:</strong> -</div>';
        const qrBlock = qrUrl
            ? `<img src="${qrUrl}" alt="QR Code" style="max-width: 260px; width: 100%; height: auto; display: block;" />`
            : '<p>Sem QR Code disponível.</p>';
        const detailsBlock = `
            <div style="display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 20px; align-items: start;">
                <div>
                    <div style="margin-bottom: 12px;">
                        <div><strong>ID:</strong> ${selectedDevice.id}</div>
                        <div><strong>Marca:</strong> ${String(selectedDevice.mark_name || '').trim() || '-'}</div>
                        <div><strong>Modelo:</strong> ${String(selectedDevice.model || selectedDevice.name || '').trim() || '-'}</div>
                        <div><strong>SN:</strong> ${selectedDevice.sn}</div>
                        <div><strong>Protocolo:</strong> ${selectedProtocol}</div>
                        <div><strong>Key:</strong> ${selectedDevice.key || '-'}</div>
                        <div><strong>Local:</strong> ${placeLabel}</div>
                    </div>
                    <div>
                        ${protocolListBlock}
                        <div><strong>Scan URL:</strong> ${scanUrl || '-'}</div>
                    </div>
                </div>
                <div style="text-align: center;">
                    ${qrBlock}
                </div>
            </div>
        `;

        const content = mode === 'qr' ? qrBlock : detailsBlock;
        const title = mode === 'qr' ? 'QR Code do dispositivo' : 'Detalhes do dispositivo';
        const printWindow = window.open('', '_blank', 'width=900,height=700');
        if (!printWindow) return;

        if (mode === 'qr') {
            printWindow.document.write(`
                <!DOCTYPE html>
                <html lang="pt-br">
                    <head>
                        <title>${title}</title>
                        <style>
                            body {
                                margin: 0;
                                min-height: 100vh;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                background: #ffffff;
                            }
                        </style>
                    </head>
                    <body>${content}</body>
                </html>
            `);
        } else {
            printWindow.document.write(`
                <!DOCTYPE html>
                <html lang="pt-br">
                    <head>
                        <title>${title}</title>
                        <style>
                            body { font-family: Arial, sans-serif; padding: 24px; color: #111827; }
                            h1 { font-size: 18px; margin-bottom: 16px; }
                            div { font-size: 14px; line-height: 1.5; }
                        </style>
                    </head>
                    <body>
                        <h1>${title}</h1>
                        ${content}
                    </body>
                </html>
            `);
        }
        printWindow.document.close();
        printWindow.focus();
        printWindow.onload = () => {
            printWindow.print();
            printWindow.close();
        };
    };

    const handleGenerateQrForSelectedDevice = async () => {
        if (!selectedDevice) return;
        await generateQrForDevice(selectedDevice, { show: true });
    };

    const usersFiltered = useMemo(() => {
        const search = userSearch.trim().toLowerCase();
        const usersBySelector = users.filter((u) => (
            userActivityFilter === 'inactive' ? !u.is_active : u.is_active
        ));
        if (!search) return usersBySelector;
        return usersBySelector.filter((u) => (
            u.username.toLowerCase().includes(search)
            || (u.full_name || '').toLowerCase().includes(search)
        ));
    }, [userSearch, users, userActivityFilter]);

    const devicesFiltered = useMemo(() => {
        const search = deviceSearch.trim().toLowerCase();
        const devicesBySelector = devices.filter((device) => {
            const runtimeStatus = deviceStatus[device.id];
            const isOnline = isOnlineDeviceRuntimeSnapshot(runtimeStatus);
            return deviceActivityFilter === 'all'
                ? device.is_active
                : deviceActivityFilter === 'online'
                    ? (device.is_active && isOnline)
                    : deviceActivityFilter === 'active'
                    ? device.is_active
                    : !device.is_active;
        });
        if (!search) return devicesBySelector;
        return devicesBySelector.filter((device) => {
            const place = places.find((item) => item.id === device.place_id);
            const placeLabel = place ? `${place.name} ${place.city} ${place.state}`.toLowerCase() : '';
            return (
                getDeviceDisplayName(device).toLowerCase().includes(search)
                || device.sn.toLowerCase().includes(search)
                || placeLabel.includes(search)
                || String(device.id).includes(search)
            );
        });
    }, [deviceSearch, devices, places, deviceStatus, deviceActivityFilter]);

    const recordsForSelectedUser = useMemo(() => {
        if (!selectedUser) return [];
        return records.filter((record) => record.owner_id === selectedUser.id);
    }, [records, selectedUser]);

    const openUserView = (target: User, view: UsersView) => {
        setSelectedUser(target);
        setUsersView(view);
        setShowUserHistory(false);
        setMenu('users');
    };

    const closeUserView = () => setUsersView('list');

    const openDeviceFromRecord = (device: Device) => {
        setSelectedDevice(device);
        setDevicesView('view');
        setMenu('devices');
    };

    const confirmToggleUserActive = (target: User) => {
        const isDisabling = target.is_active;
        setConfirm({
            open: true,
            title: isDisabling ? 'Desativar usuário' : 'Ativar usuário',
            description: `Deseja ${isDisabling ? 'desativar' : 'ativar'} ${target.username}?`,
            confirmLabel: isDisabling ? 'Desativar' : 'Ativar',
            errorFallback: isDisabling ? 'Falha ao desativar usuário.' : 'Falha ao ativar usuário.',
            onConfirm: async () => {
                const updated = await usersAPI.update(target.id, { is_active: !target.is_active });
                await loadUsers();
                setSelectedUser(updated.data);
            },
        });
    };

    const confirmResetUserPassword = (target: User) => {
        setConfirm({
            open: true,
            title: 'Resetar senha do usuário',
            description: `Resetar a senha de ${target.username}?`,
            confirmLabel: 'Resetar senha',
            errorFallback: 'Falha ao resetar senha.',
            onConfirm: async () => {
                await usersAPI.update(target.id, { password: target.username });
                setPasswordResetUsers((state) => state.includes(target.id) ? state : [...state, target.id]);
                showStatus('info', 'Senha resetada.');
            },
        });
    };

    const activeProcedureOptions = useMemo(
        () => procedures
            .filter((procedure) => procedure.is_active !== false)
            .map((procedure) => ({
                value: String(procedure.id),
                label: procedure.name,
            })),
        [procedures],
    );
    const deviceProtocolPushList = useMemo(() => {
        const deviceKey = (selectedDevice?.key || '').trim();
        if (!deviceKey) return [] as Array<{ protocol: string; port: number; url: string; is_active: boolean }>;

        const selectedProtocol = (selectedDevice?.protocol || '').trim().toLowerCase();
        const candidates = protocols;
        const fallbackProtocol = (selectedProtocol || pickPreferredProtocol(protocols))
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9+.-]/g, '') || 'srt';
        const fallbackPort = PROTOCOL_DEFAULT_PORTS[fallbackProtocol] || 8554;
        const normalizedCandidates = candidates.length
            ? candidates
            : [{ id: 0, protocol: fallbackProtocol, port: fallbackPort, is_active: true }];
        const uniqueByProtocol = Array.from(
            new Map(normalizedCandidates.map((item) => [item.protocol, item])).values(),
        );
        return uniqueByProtocol.map((item) => {
            const protocol = (item.protocol || fallbackProtocol)
                .trim()
                .toLowerCase()
                .replace(/[^a-z0-9+.-]/g, '') || fallbackProtocol;
            const port = Number(item.port) || PROTOCOL_DEFAULT_PORTS[protocol] || 8554;
            const streamPath = `${APP_NAME}/${APP_VERSION}/${deviceKey}/stream`;
            const url = protocol === 'srt'
                ? `${protocol}://${hostInfo.hostname}:${port}?streamid=publish:${streamPath}`
                : `${protocol}://${hostInfo.hostname}:${port}/${streamPath}`;
            return {
                protocol,
                port,
                url,
                is_active: item.is_active !== false,
            };
        });
    }, [selectedDevice?.key, selectedDevice?.protocol, protocols, hostInfo.hostname]);
    const scanUrl = selectedDevice?.key
        ? `http://${hostInfo.hostname}:${hostInfo.port || '3000'}${hostInfo.basePath || (APP_BASE_PATH === '/' ? '' : APP_BASE_PATH)}/scan?key=${encodeURIComponent(selectedDevice.key)}`
        : '';

    if (loading) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-zinc-50">
                <p className="text-zinc-700">Carregando...</p>
            </div>
        );
    }

    const renderContent = (target: MenuKey | 'profile') => {
        if (target === 'dashboard') {
            return (
                <DashboardPage
                    isAdmin={isAdmin}
                    users={users}
                    devices={devices}
                    deviceStatus={deviceStatus}
                    records={records}
                    openRecords={openRecords}
                    managerMetrics={managerMetrics}
                    currentOpenRecord={currentOpenRecord}
                    places={places}
                    procedures={procedures}
                    recordingBusy={recordingBusy}
                    onOpenRecordsList={openRecordsListFromDashboard}
                    onOpenUsersList={openUsersListFromDashboard}
                    onOpenDevicesList={openDevicesListFromDashboard}
                    onStopRecord={handleStopRecord}
                    onOpenRecord={openRecordViewFromDashboard}
                    onOpenScan={handleOpenDashboardScan}
                    showScanAction={dashboardScanSupported}
                />
            );
        }
        if (target === 'records') {
            return (
                <RecordsPage
                    isAdmin={isAdmin}
                    user={user}
                    recordsView={recordsView}
                    records={records}
                    selectedRecord={selectedRecord}
                    procedures={procedures}
                    users={users}
                    devices={devices}
                    places={places}
                    recordForm={recordForm}
                    recordEditForm={recordEditForm}
                    recordSearch={recordSearch}
                    recordActivityFilter={recordActivityFilter}
                    boundDevice={boundDevice}
                    deviceStatus={deviceStatus}
                    recordingBusy={recordingBusy}
                    savingRecord={savingRecord}
                    currentOpenRecord={currentOpenRecord}
                    onRecordFormChange={setRecordForm}
                    onRecordEditChange={setRecordEditForm}
                    onRecordSearchChange={setRecordSearch}
                    onRecordActivityFilterChange={setRecordActivityFilter}
                    onStartRecord={handleStartRecord}
                    onSaveRecordEdit={handleSaveRecordEdit}
                    onStopRecord={handleStopRecord}
                    onOpenRecordNew={openRecordNew}
                    onOpenRecordView={openRecordView}
                    onCloseRecordsView={() => setRecordsView('list')}
                    outputFormat={String(appSettings.output_format || 'mp4').toLowerCase()}
                    onOpenUserView={openUserView}
                    onOpenDeviceView={openDeviceFromRecord}
                />
            );
        }
        if (target === 'devices') {
            return (
                    <DevicesPage
                        isAdmin={isAdmin}
                        devicesView={devicesView}
                        selectedDevice={selectedDevice}
                        places={places}
                        cities={cities}
                        marks={marks}
                        devicesFiltered={devicesFiltered}
                        deviceStatus={deviceStatus}
                        deviceForm={deviceForm}
                        citySearch={deviceCitySearch}
                        placeSearch={placeSearch}
                        deviceSearch={deviceSearch}
                        deviceActivityFilter={deviceActivityFilter}
                        savingDevice={savingDevice}
                        qrImageUrl={qrImageUrl}
                        showQrCode={showQrCode}
                        protocols={deviceProtocolPushList}
                        availableProtocols={protocols}
                        scanUrl={scanUrl}
                        onViewChange={setDevicesView}
                        onDeviceFormChange={setDeviceForm}
                        onCitySearchChange={setDeviceCitySearch}
                        onPlaceSearchChange={setPlaceSearch}
                        onDeviceSearchChange={setDeviceSearch}
                        onDeviceActivityFilterChange={setDeviceActivityFilter}
                        onSaveDevice={handleSaveDevice}
                        onOpenDeviceEdit={openDeviceEdit}
                        onOpenDeviceNew={openDeviceNew}
                        onOpenDeviceView={openDeviceView}
                        onConfirmDeactivate={confirmDeactivateDevice}
                        onConfirmDelete={confirmDeleteDevice}
                        onOpenPrintModal={setShowDevicePrintModal}
                        onGenerateQrCode={handleGenerateQrForSelectedDevice}
                    />
            );
        }
        if (target === 'marks') {
            return (
                <MarksPage
                    marks={marks}
                    markSearch={markSearch}
                    setMarkSearch={setMarkSearch}
                    showInactiveMarks={showInactiveMarks}
                    setShowInactiveMarks={setShowInactiveMarks}
                    loadMarks={loadMarks}
                    showStatus={showStatus}
                    setConfirm={setConfirm}
                />
            );
        }
        if (target === 'users') {
            return (
                <UsersPage
                    isAdmin={isAdmin}
                    usersView={usersView}
                    selectedUser={selectedUser}
                    usersFiltered={usersFiltered}
                    userSearch={userSearch}
                    userActivityFilter={userActivityFilter}
                    onUserSearchChange={setUserSearch}
                    onUserActivityFilterChange={setUserActivityFilter}
                    onSelectUser={openUserView}
                    onCloseView={closeUserView}
                    onToggleUserActive={confirmToggleUserActive}
                    onResetPassword={confirmResetUserPassword}
                    onToggleHistory={() => setShowUserHistory((state) => !state)}
                    showUserHistory={showUserHistory}
                    recordsForSelectedUser={recordsForSelectedUser}
                    places={places}
                    passwordResetUsers={passwordResetUsers}
                />
            );
        }
        if (target === 'settings') {
            return (
                <SettingsPage
                    settingsTab={settingsTab}
                    appSettingsForm={appSettingsForm}
                    setAppSettingsForm={setAppSettingsForm}
                    setAppSettings={setAppSettings}
                    setPublicHost={setPublicHost}
                    outputFormat={(String(appSettings.output_format || 'mp4').toLowerCase() === 'mkv' ? 'mkv' : 'mp4')}
                    onOutputFormatChange={handleUpdateOutputFormat}
                    protocols={protocols}
                    protocolSearch={protocolSearch}
                    setProtocolSearch={setProtocolSearch}
                    showInactiveProtocols={showInactiveProtocols}
                    setShowInactiveProtocols={setShowInactiveProtocols}
                    places={places}
                    placeTabSearch={placeTabSearch}
                    setPlaceTabSearch={setPlaceTabSearch}
                    showInactivePlaces={showInactivePlaces}
                    setShowInactivePlaces={setShowInactivePlaces}
                    cities={cities}
                    citySearch={citySearch}
                    setCitySearch={setCitySearch}
                    showInactiveCities={showInactiveCities}
                    setShowInactiveCities={setShowInactiveCities}
                    cptecApiOnline={cptecApiOnline}
                    fetchCptecCity={fetchCptecCity}
                    searchCptecCities={searchCptecCities}
                    loadProtocols={loadProtocols}
                    loadPlaces={loadPlaces}
                    loadCities={loadCities}
                    showStatus={showStatus}
                    setConfirm={setConfirm}
                    onOpenCitiesSettings={() => setSettingsTab('cities')}
                />
            );
        }
        if (target === 'notifications') {
            return (
                <NotificationsPage
                    user={user}
                    profilePhotoUrl={profilePhotoUrl}
                    notifications={notifications}
                    loadingNotifications={loadingNotifications}
                    onOpenProfileEdit={() => setMenu('profile')}
                    onMarkAsRead={markNotificationAsRead}
                    onDeleteNotification={deleteNotification}
                    onOpenNotificationRecord={openRecordFromNotification}
                />
            );
        }
        return (
            <ProfilePage
                user={user}
                profilePhotoUrl={profilePhotoUrl}
                onClearPhoto={clearProfilePhoto}
                onPhotoClick={handleProfilePhotoClick}
                onRemovePhoto={handleRemoveProfilePhoto}
                settingsForm={settingsForm}
                onSettingsChange={setSettingsForm}
                onSaveSettings={handleSaveSettings}
                onCancelSettings={handleCancelSettings}
                savingSettings={savingSettings}
            />
        );
    };

    return (
        <div className="min-h-screen bg-zinc-50 text-zinc-900 overflow-x-hidden">
            <header className="border-b border-zinc-200 bg-white">
                <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-2 py-2 sm:flex-row sm:gap-3 sm:px-4 sm:py-3">
                    <div className="flex min-w-0 items-center gap-2 sm:gap-3">
                        <button
                            type="button"
                            onClick={() => setMobileMenuOpen(true)}
                            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-zinc-700 transition hover:bg-zinc-100 active:scale-95 md:hidden"
                            aria-label="Abrir menu"
                        >
                            <Menu className="h-5 w-5" />
                        </button>
                        <img src={withAppBase('/logo.png')} alt="Logo" className="h-10 w-auto max-w-[100px] shrink-0 object-contain sm:h-[90px] sm:max-w-[314px]" />
                        <div className="min-w-0 hidden sm:block">
                            <p className="truncate text-xs uppercase tracking-wide text-zinc-600">
                                {appSettings.description || 'Streaming Médico'}
                            </p>
                            <h1 className="truncate text-lg font-semibold">{appSettings.name || APP_NAME}</h1>
                        </div>
                    </div>
                    <div className="flex items-center gap-1 sm:gap-3">
                        <button
                            type="button"
                            onClick={() => setMenu('notifications')}
                            className="flex min-w-0 items-center gap-1.5 sm:gap-2 rounded-full border border-transparent px-1.5 sm:px-2 py-1.5 sm:py-1 text-sm text-zinc-700 transition hover:border-zinc-200 hover:bg-white active:bg-zinc-100 min-h-[44px] sm:min-h-0"
                        >
                            <span className="relative inline-flex h-8 w-8 shrink-0">
                                {unreadNotificationsCount > 0 ? (
                                    <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-sky-300 shadow-sm" />
                                ) : null}
                                <span className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-zinc-200 bg-white">
                                    {profilePhotoUrl ? (
                                        <img
                                            src={profilePhotoUrl}
                                            alt="Perfil"
                                            className="h-full w-full object-cover"
                                            onError={clearProfilePhoto}
                                        />
                                    ) : (
                                        <UserIcon className="h-4 w-4 text-zinc-600" />
                                    )}
                                </span>
                            </span>
                            <span className="max-w-[100px] sm:max-w-[160px] truncate text-xs sm:text-sm">{user?.full_name || user?.username}</span>
                        </button>
                        <Button variant="danger" size="sm" className="shrink-0 px-2 sm:px-3" onClick={handleLogout}>
                            <LogOut className="h-4 w-4 sm:mr-2" /><span className="hidden sm:inline"> Sair</span>
                        </Button>
                    </div>
                </div>
            </header>

            {/* Mobile drawer */}
            <div
                className={`fixed inset-0 z-50 md:hidden transition-opacity duration-200 ${mobileMenuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
            >
                <div className="absolute inset-0 bg-black/40" onClick={() => setMobileMenuOpen(false)} />
                <div
                    className={`absolute inset-y-0 left-0 w-64 bg-white shadow-xl transition-transform duration-200 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
                >
                    <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
                        <span className="text-sm font-semibold text-zinc-900">Menu</span>
                        <button
                            type="button"
                            onClick={() => setMobileMenuOpen(false)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-100"
                            aria-label="Fechar menu"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                    <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
                        {menuItems
                            .filter((item) => !(item.adminOnly && !isAdmin))
                            .map((item) => (
                                <button
                                    key={item.key}
                                    onClick={() => handleMobileMenuSelect(item.key)}
                                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm transition active:scale-[0.98] ${menu === item.key && !(menu === 'settings') ? 'bg-emerald-600 text-white' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                >
                                    {item.icon}
                                    <span>{item.label}</span>
                                </button>
                            ))}
                        {isAdmin ? (
                            <>
                                <div className="my-2 border-t border-zinc-200" />
                                <button
                                    type="button"
                                    onClick={() => handleMobileSettingsSelect('app')}
                                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm transition active:scale-[0.98] ${menu === 'settings' ? 'bg-emerald-600 text-white' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                >
                                    <Settings className="h-4 w-4" />
                                    <span>Configurações</span>
                                </button>
                                {settingsMenuItems.map((item) => {
                                    const active = menu === 'settings' && settingsTab === item.key;
                                    return (
                                        <button
                                            key={item.key}
                                            onClick={() => handleMobileSettingsSelect(item.key)}
                                            className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 pl-8 text-sm transition active:scale-[0.98] ${active ? 'bg-emerald-50 text-emerald-700' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                        >
                                            {item.icon}
                                            <span>{item.label}</span>
                                        </button>
                                    );
                                })}
                            </>
                        ) : null}
                    </nav>
                    <div className="border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500">
                        versão {APP_VERSION}
                    </div>
                </div>
            </div>

            <div className="mx-auto max-w-7xl px-3 py-3 sm:px-4 sm:py-4">
                <div className="grid gap-3 md:grid-cols-[240px,1fr] md:gap-4">
                    <aside className="hidden md:block rounded-xl border border-zinc-200 bg-white p-3">
                    <nav className="flex gap-1 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
                        {menuItems
                            .filter((item) => !(item.adminOnly && !isAdmin))
                            .map((item) => (
                                <button
                                    key={item.key}
                                    onClick={() => setMenu(item.key)}
                                    className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-xs transition active:scale-95 md:flex md:h-auto md:w-full md:justify-start md:gap-2 md:px-3 md:py-2 md:text-sm ${menu === item.key ? 'bg-emerald-600 text-white' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                    title={item.label}
                                >
                                    {item.icon}
                                    <span className="hidden md:inline">{item.label}</span>
                                </button>
                            ))}
                        {isAdmin ? settingsMenuItems.map((item) => {
                            const active = menu === 'settings' && settingsTab === item.key;
                            return (
                                <button
                                    key={`compact-settings-${item.key}`}
                                    onClick={() => {
                                        setMenu('settings');
                                        setSettingsTab(item.key);
                                    }}
                                    className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-xs transition active:scale-95 md:hidden ${active ? 'bg-emerald-50 text-emerald-700' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                    title={item.label}
                                >
                                    {item.icon}
                                </button>
                            );
                        }) : null}
                    </nav>
                    {isAdmin ? (
                        <div className="hidden md:mt-3 md:block md:border-t md:border-zinc-200 md:pt-3">
                            <button
                                type="button"
                                onClick={() => {
                                    setMenu('settings');
                                    setSettingsTab('app');
                                }}
                                className={`hidden items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition md:flex md:w-full ${menu === 'settings' ? 'bg-emerald-600 text-white' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                title="Configurações"
                            >
                                <Settings className="h-4 w-4" />
                                <span className="hidden md:inline">Configurações</span>
                            </button>
                            <div className="mt-1 flex gap-1 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
                                {settingsMenuItems.map((item) => {
                                    const active = menu === 'settings' && settingsTab === item.key;
                                    return (
                                        <button
                                            key={item.key}
                                            onClick={() => {
                                                setMenu('settings');
                                                setSettingsTab(item.key);
                                            }}
                                            className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-left text-xs transition active:scale-95 md:flex md:h-auto md:w-full md:justify-start md:gap-2 md:px-3 md:py-2 md:pl-8 md:text-sm ${active ? 'bg-emerald-50 text-emerald-700' : 'text-zinc-700 hover:bg-zinc-100'}`}
                                            title={item.label}
                                        >
                                            {item.icon}
                                            <span className="hidden md:inline">{item.label}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    ) : null}
                    <div className="mt-2 border-t border-zinc-200 pt-2 text-xs text-zinc-500 md:mt-4 md:pt-3">versão {APP_VERSION}</div>
                    </aside>

                    <main className="min-w-0 space-y-4">
                    {status ? (
                        <StatusMsg
                            level={status.level}
                            msg={status.msg}
                            time_sec={status.time_sec}
                            onClear={clearStatus}
                        />
                    ) : null}
                    <Activity mode={menu === 'dashboard' ? 'visible' : 'hidden'}>
                        {renderContent('dashboard')}
                    </Activity>
                    <Activity mode={menu === 'records' ? 'visible' : 'hidden'}>
                        {renderContent('records')}
                    </Activity>
                    {isAdmin ? (
                        <Activity mode={menu === 'devices' ? 'visible' : 'hidden'}>
                            {renderContent('devices')}
                        </Activity>
                    ) : null}
                    {isAdmin ? (
                        <Activity mode={menu === 'marks' ? 'visible' : 'hidden'}>
                            {renderContent('marks')}
                        </Activity>
                    ) : null}
                    {isAdmin ? (
                        <Activity mode={menu === 'users' ? 'visible' : 'hidden'}>
                            {renderContent('users')}
                        </Activity>
                    ) : null}
                    {isAdmin ? (
                        <Activity mode={menu === 'settings' ? 'visible' : 'hidden'}>
                            {renderContent('settings')}
                        </Activity>
                    ) : null}
                    <Activity mode={menu === 'notifications' ? 'visible' : 'hidden'}>
                        {renderContent('notifications')}
                    </Activity>
                    <Activity mode={menu === 'profile' ? 'visible' : 'hidden'}>
                        {renderContent('profile')}
                    </Activity>
                    </main>
                </div>
            </div>
            <footer className="mx-auto max-w-7xl px-3 pb-4 sm:px-4">
                <div className="flex justify-end">
                    <img
                        src={withAppBase('/marlex-logo.svg')}
                        alt="Marlex"
                        className="h-7 w-auto opacity-90"
                    />
                </div>
            </footer>

            <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                onChange={handleProfilePhotoChange}
                className="hidden"
            />

            {showGlobalLoader ? (
                <div className="pointer-events-none fixed right-3 top-3 z-40 sm:right-4 sm:top-4">
                    <div className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white/95 px-3 py-2 text-xs text-zinc-700 shadow-lg backdrop-blur">
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-600" />
                        Sincronizando...
                    </div>
                </div>
            ) : null}

            <ConfirmActionModal
                isOpen={confirm.open}
                onClose={closeConfirmModal}
                onConfirm={() => void handleConfirmAction()}
                title={confirm.title}
                description={confirm.description}
                errorMessage={confirm.errorMessage}
                confirmLabel={confirm.confirmLabel}
                loading={confirm.loading}
                confirmVariant="danger"
            />

            <Modal
                isOpen={!apiAvailable}
                onClose={() => {}}
                title="Sistema indisponivel"
            >
                <div className="space-y-4 text-sm text-zinc-700">
                    <p className="flex items-center gap-2">
                        <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-600" />
                        API offline no momento.
                    </p>
                    <p className="text-xs text-zinc-500">
                        As sincronizações ficam pausadas até a API voltar.
                    </p>
                    <div className="flex justify-end">
                        <Button
                            variant="secondary"
                            onClick={() => {
                                void bootstrap();
                            }}
                        >
                            Tentar novamente
                        </Button>
                    </div>
                </div>
            </Modal>

            <Modal isOpen={showDevicePrintModal} onClose={() => setShowDevicePrintModal(false)} title="Imprimir">
                <div className="space-y-4 text-sm text-zinc-700">
                    <p>Selecione o conteúdo para impressão.</p>
                    <div className="flex flex-wrap gap-2">
                        <Button
                            variant="secondary"
                            onClick={() => {
                                void handlePrintDevice('qr');
                                setShowDevicePrintModal(false);
                            }}
                        >
                            QR Code
                        </Button>
                        <Button
                            variant="secondary"
                            onClick={() => {
                                void handlePrintDevice('details');
                                setShowDevicePrintModal(false);
                            }}
                        >
                            Detalhes
                        </Button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={scanFeedbackModal.open}
                onClose={() => setScanFeedbackModal({ open: false, level: 'info', message: '' })}
                title="Mensagem do scan"
            >
                <div className="space-y-4 text-sm text-zinc-700">
                    <p
                        className={
                            scanFeedbackModal.level === 'error'
                                ? 'text-red-700'
                                : scanFeedbackModal.level === 'warn'
                                    ? 'text-amber-700'
                                    : 'text-zinc-700'
                        }
                    >
                        {scanFeedbackModal.message}
                    </p>
                    <div className="flex justify-end">
                        <Button onClick={() => setScanFeedbackModal({ open: false, level: 'info', message: '' })}>
                            OK
                        </Button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={blockingErrorModal.open}
                onClose={() => setBlockingErrorModal({ open: false, title: '', message: '' })}
                title={blockingErrorModal.title || 'Erro'}
            >
                <div className="space-y-4 text-sm text-zinc-700">
                    <p className="text-red-700">{blockingErrorModal.message}</p>
                    <div className="flex justify-end">
                        <Button onClick={() => setBlockingErrorModal({ open: false, title: '', message: '' })}>
                            OK
                        </Button>
                    </div>
                </div>
            </Modal>

            <QrScanModal
                isOpen={showDashboardScanModal}
                onClose={handleCloseDashboardScan}
                onDetected={handleDetectedDashboardScan}
            />

            <Modal isOpen={showRecordModal} onClose={() => { invalidateScan(); setShowRecordModal(false); }} title="Iniciar gravação">
                <div className="space-y-4 text-sm text-zinc-700">
                    <p>Dispositivo: {boundDevice ? `${getDeviceDisplayName(boundDevice)} (#${boundDevice.id})` : '-'}</p>
                    <p className="text-xs text-zinc-500">Status: {boundDeviceRuntimeStatus}</p>
                    {!isAdmin ? (
                        <p className="text-xs text-amber-700">Tempo restante para iniciar: {scanStartCountdown}s</p>
                    ) : null}
                    {boundDevice && !isBoundDeviceReady ? (
                        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                            Conectando ao dispositivo. O botão REC será liberado quando o status ficar Online.
                        </p>
                    ) : null}
                    <form onSubmit={handleStartRecord} className="space-y-3">
                        <input
                            value={recordForm.title}
                            onChange={(event) => setRecordForm((state) => ({ ...state, title: event.target.value }))}
                            placeholder="Título"
                            className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                            required
                        />
                        <textarea
                            value={recordForm.description}
                            onChange={(event) => setRecordForm((state) => ({ ...state, description: event.target.value }))}
                            placeholder="Descrição"
                            className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none"
                            rows={2}
                        />
                        <SelectField
                            value={recordForm.procedure_id}
                            options={activeProcedureOptions}
                            onValueChange={(value) => setRecordForm((state) => ({ ...state, procedure_id: value }))}
                            placeholder="Selecione o procedimento"
                        />
                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                            <Button type="button" variant="ghost" onClick={() => { invalidateScan(); setShowRecordModal(false); }} className="w-full sm:w-auto">Cancelar</Button>
                            <Button
                                type="submit"
                                variant="danger"
                                className="w-full sm:w-auto rounded-full px-5"
                                disabled={recordingBusy || !isBoundDeviceReady}
                            >
                                <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-red-600 shadow-[0_0_0_4px_rgba(239,68,68,0.35)]" />
                                {recordingBusy ? 'Iniciando...' : 'REC iniciar gravação'}
                            </Button>
                        </div>
                    </form>
                </div>
            </Modal>
        </div>
    );
};
