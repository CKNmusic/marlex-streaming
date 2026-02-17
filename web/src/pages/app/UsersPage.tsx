import { Card } from '../../components/ui/Card';
import { UsersListPage } from './users/UsersListPage';
import { UserViewPage } from './users/UserViewPage';
import type { UsersPageProps } from './users/types';

export const UsersPage = ({
    isAdmin,
    usersView,
    selectedUser,
    usersFiltered,
    userSearch,
    userActivityFilter,
    onUserSearchChange,
    onUserActivityFilterChange,
    onSelectUser,
    onCloseView,
    onToggleUserActive,
    onResetPassword,
    onToggleHistory,
    showUserHistory,
    recordsForSelectedUser,
    places,
    passwordResetUsers,
}: UsersPageProps) => {
    if (!isAdmin) {
        return <Card title="Usuários"><p className="text-sm text-zinc-600">Somente master.</p></Card>;
    }

    if (usersView === 'view' && selectedUser) {
        return (
            <UserViewPage
                selectedUser={selectedUser}
                onCloseView={onCloseView}
                onToggleUserActive={onToggleUserActive}
                onResetPassword={onResetPassword}
                onToggleHistory={onToggleHistory}
                showUserHistory={showUserHistory}
                recordsForSelectedUser={recordsForSelectedUser}
                places={places}
                passwordResetUsers={passwordResetUsers}
            />
        );
    }

    return (
        <UsersListPage
            usersFiltered={usersFiltered}
            userSearch={userSearch}
            userActivityFilter={userActivityFilter}
            onUserSearchChange={onUserSearchChange}
            onUserActivityFilterChange={onUserActivityFilterChange}
            onSelectUser={onSelectUser}
        />
    );
};
