import type { ReactNode } from 'react';
import {
    AppWindow,
    Film,
    LayoutDashboard,
    Map,
    MapPin,
    Network,
    Tag,
    Users as UsersIcon,
    Video,
} from 'lucide-react';
import type { MenuKey, SettingsTab } from './types';

export const menuItems: Array<{ key: MenuKey; label: string; icon: ReactNode; adminOnly?: boolean }> = [
    { key: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard className="h-4 w-4" /> },
    { key: 'records', label: 'Gravações', icon: <Film className="h-4 w-4" /> },
    { key: 'devices', label: 'Dispositivos', icon: <Video className="h-4 w-4" />, adminOnly: true },
    { key: 'marks', label: 'Marcas', icon: <Tag className="h-4 w-4" />, adminOnly: true },
    { key: 'users', label: 'Usuários', icon: <UsersIcon className="h-4 w-4" />, adminOnly: true },
];

export const settingsMenuItems: Array<{ key: SettingsTab; label: string; icon: ReactNode }> = [
    { key: 'app', label: 'Aplicação', icon: <AppWindow className="h-4 w-4" /> },
    { key: 'protocols', label: 'Protocolos', icon: <Network className="h-4 w-4" /> },
    { key: 'places', label: 'Locais', icon: <MapPin className="h-4 w-4" /> },
    { key: 'cities', label: 'Cidades', icon: <Map className="h-4 w-4" /> },
];
