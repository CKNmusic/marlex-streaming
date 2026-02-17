import { useState } from 'react';
import { Bell, Pencil, User as UserIcon } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import type { User, UserNotification } from '../../lib/api/client';
import { formatDateTime } from './utils';

type NotificationsPageProps = {
    user: User | null;
    profilePhotoUrl: string;
    notifications: UserNotification[];
    loadingNotifications: boolean;
    onOpenProfileEdit: () => void;
    onMarkAsRead: (notificationId: number) => Promise<void>;
    onDeleteNotification: (notificationId: number) => Promise<void>;
    onOpenNotificationRecord: (recordId?: number | null) => Promise<void> | void;
};

export const NotificationsPage = ({
    user,
    profilePhotoUrl,
    notifications,
    loadingNotifications,
    onOpenProfileEdit,
    onMarkAsRead,
    onDeleteNotification,
    onOpenNotificationRecord,
}: NotificationsPageProps) => {
    const [selectedNotification, setSelectedNotification] = useState<UserNotification | null>(null);
    const unreadCount = notifications.filter((item) => !item.is_read).length;
    const currentUserId = user?.id ?? null;
    const isAdmin = Boolean(user?.is_superuser);

    const canMutateNotification = (notification: UserNotification) => {
        if (!currentUserId) return false;
        if (isAdmin) return true;
        return notification.user_id === currentUserId;
    };

    const getOwnerLabel = (notification: UserNotification) => {
        const ownerName = (notification.user_name || '').trim() || 'Sem nome';
        return `Usuário #${notification.user_id} - ${ownerName}`;
    };

    const handleOpenNotification = async (notification: UserNotification) => {
        const canMutate = canMutateNotification(notification);
        setSelectedNotification(
            !notification.is_read && canMutate
                ? { ...notification, is_read: true }
                : notification,
        );
        if (!notification.is_read && canMutate) {
            await onMarkAsRead(notification.id);
        }
    };

    const handleDeleteNotification = async () => {
        if (!selectedNotification || !canMutateNotification(selectedNotification)) return;
        await onDeleteNotification(selectedNotification.id);
        setSelectedNotification(null);
    };

    return (
        <div className="space-y-4">
            <Card title="Perfil">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                        <div className="h-16 w-16 overflow-hidden rounded-full border border-zinc-200 bg-white">
                            {profilePhotoUrl ? (
                                <img src={profilePhotoUrl} alt="Perfil" className="h-full w-full object-cover" />
                            ) : (
                                <div className="flex h-full w-full items-center justify-center text-zinc-600">
                                    <UserIcon className="h-6 w-6" />
                                </div>
                            )}
                        </div>
                        <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-zinc-900">{user?.full_name || user?.username || 'Usuário'}</p>
                            <p className="text-xs text-zinc-600">
                                {unreadCount > 0 ? `${unreadCount} notificação(ões) não lida(s)` : 'Sem notificações não lidas'}
                            </p>
                        </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={onOpenProfileEdit} title="Abrir perfil">
                        <Pencil className="mr-2 h-4 w-4" />
                        Abrir perfil
                    </Button>
                </div>
            </Card>

            <Card title="Notificações">
                <div className="space-y-2">
                    {loadingNotifications ? (
                        <div className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-600">Carregando notificações...</div>
                    ) : null}
                    {!loadingNotifications && notifications.length === 0 ? (
                        <div className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-600">
                            Nenhuma notificação disponível.
                        </div>
                    ) : null}
                    {notifications.map((notification) => {
                        const isForeignForAdmin = isAdmin && currentUserId !== null && notification.user_id !== currentUserId;
                        return (
                            <button
                                key={notification.id}
                                type="button"
                                onClick={() => void handleOpenNotification(notification)}
                                className={`w-full rounded-md border p-3 text-left transition ${
                                    notification.is_read
                                        ? 'border-zinc-200 bg-zinc-100 text-zinc-700 hover:bg-zinc-200/70'
                                        : 'border-sky-300 bg-white text-zinc-900 hover:border-sky-400 hover:bg-sky-50/40'
                                }`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <p className="text-sm font-medium">{notification.title}</p>
                                    {!notification.is_read ? (
                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">Nova</span>
                                    ) : null}
                                </div>
                                {isForeignForAdmin ? (
                                    <p className="mt-1 text-[11px] text-sky-700">{getOwnerLabel(notification)}</p>
                                ) : null}
                                <p className="mt-1 text-xs text-zinc-600">{notification.message}</p>
                                <div className="mt-2 flex items-center gap-2 text-[11px] text-zinc-500">
                                    <Bell className="h-3 w-3" />
                                    <span>{formatDateTime(notification.created_at, { includeSeconds: true })}</span>
                                </div>
                            </button>
                        );
                    })}
                </div>
            </Card>

            <Modal
                isOpen={selectedNotification !== null}
                onClose={() => setSelectedNotification(null)}
                title={selectedNotification?.title || 'Notificação'}
                size="md"
            >
                {selectedNotification ? (
                    <div className="space-y-4 text-sm text-zinc-700">
                        {isAdmin && currentUserId !== null && selectedNotification.user_id !== currentUserId ? (
                            <p className="text-xs text-sky-700">{getOwnerLabel(selectedNotification)}</p>
                        ) : null}
                        <p>{selectedNotification.message}</p>
                        <p className="text-xs text-zinc-500">
                            {formatDateTime(selectedNotification.created_at, { includeSeconds: true })}
                        </p>
                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
                            <Button variant="ghost" onClick={() => setSelectedNotification(null)} className="w-full sm:w-auto">Fechar</Button>
                            {canMutateNotification(selectedNotification) ? (
                                <Button variant="danger" onClick={() => void handleDeleteNotification()} className="w-full sm:w-auto">Excluir</Button>
                            ) : null}
                            {selectedNotification.record_id ? (
                                <Button
                                    variant="secondary"
                                    onClick={() => void onOpenNotificationRecord(selectedNotification.record_id)}
                                    className="w-full sm:w-auto"
                                >
                                    Abrir gravação
                                </Button>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </Modal>
        </div>
    );
};
