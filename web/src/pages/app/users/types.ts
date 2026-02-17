import type { Record as RecordApi, User } from '../../../lib/api/client';
import type { ActivityFilter, PlaceItem, UsersView } from '../types';

export type UsersPageProps = {
    isAdmin: boolean;
    usersView: UsersView;
    selectedUser: User | null;
    usersFiltered: User[];
    userSearch: string;
    userActivityFilter: ActivityFilter;
    onUserSearchChange: (value: string) => void;
    onUserActivityFilterChange: (value: ActivityFilter) => void;
    onSelectUser: (user: User, view: UsersView) => void;
    onCloseView: () => void;
    onToggleUserActive: (user: User) => void;
    onResetPassword: (user: User) => void;
    onToggleHistory: () => void;
    showUserHistory: boolean;
    recordsForSelectedUser: RecordApi[];
    places: PlaceItem[];
    passwordResetUsers: number[];
};
