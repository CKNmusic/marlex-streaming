import { useCallback, useEffect, useState } from 'react';
import { Copy, Eye, Link2, Trash2, UserPlus } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { Modal } from '../../../components/ui/Modal';
import { SelectField } from '../../../components/ui/SelectField';
import type { Invite, User } from '../../../lib/api/client';
import { APP_BASE_PATH, invitesAPI } from '../../../lib/api/client';
import type { ActivityFilter, UsersView } from '../types';

type UsersListPageProps = {
    usersFiltered: User[];
    userSearch: string;
    userActivityFilter: ActivityFilter;
    onUserSearchChange: (value: string) => void;
    onUserActivityFilterChange: (value: ActivityFilter) => void;
    onSelectUser: (user: User, view: UsersView) => void;
};

const userActivityOptions = [
    { value: 'all', label: 'Todos (ativos)' },
    { value: 'inactive', label: 'Somente desativados' },
];

const buildInviteUrl = (code: string) => {
    const base = window.location.origin;
    const path = APP_BASE_PATH === '/' ? '' : APP_BASE_PATH;
    return `${base}${path}/register?code=${encodeURIComponent(code)}`;
};

const formatExpiresAt = (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}, ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export const UsersListPage = ({
    usersFiltered,
    userSearch,
    userActivityFilter,
    onUserSearchChange,
    onUserActivityFilterChange,
    onSelectUser,
}: UsersListPageProps) => {
    const [inviteModalOpen, setInviteModalOpen] = useState(false);
    const [invites, setInvites] = useState<Invite[]>([]);
    const [loadingInvites, setLoadingInvites] = useState(false);
    const [generatingInvite, setGeneratingInvite] = useState(false);
    const [copiedCode, setCopiedCode] = useState<string | null>(null);
    const [inviteError, setInviteError] = useState<string | null>(null);

    const extractErrorMessage = (err: unknown): string => {
        const axiosErr = err as { response?: { data?: { detail?: string }; status?: number } };
        if (axiosErr?.response?.data?.detail) return axiosErr.response.data.detail;
        if (axiosErr?.response?.status === 403) return 'Sem permissão. Apenas administradores podem gerenciar convites.';
        if (axiosErr?.response?.status === 401) return 'Sessão expirada. Faça login novamente.';
        return 'Erro de conexão com o servidor.';
    };

    const loadInvites = useCallback(async () => {
        setLoadingInvites(true);
        setInviteError(null);
        try {
            const response = await invitesAPI.getAll();
            setInvites(response.data);
        } catch (err) {
            setInviteError(extractErrorMessage(err));
        } finally {
            setLoadingInvites(false);
        }
    }, []);

    useEffect(() => {
        if (inviteModalOpen) {
            void loadInvites();
        }
    }, [inviteModalOpen, loadInvites]);

    const handleGenerateInvite = async () => {
        setGeneratingInvite(true);
        setInviteError(null);
        try {
            await invitesAPI.create();
            await loadInvites();
        } catch (err) {
            setInviteError(extractErrorMessage(err));
        } finally {
            setGeneratingInvite(false);
        }
    };

    const handleRevokeInvite = async (id: number) => {
        setInviteError(null);
        try {
            await invitesAPI.revoke(id);
            await loadInvites();
        } catch (err) {
            setInviteError(extractErrorMessage(err));
        }
    };

    const handleCopyInviteLink = (code: string) => {
        const url = buildInviteUrl(code);
        void navigator.clipboard.writeText(url);
        setCopiedCode(code);
        setTimeout(() => setCopiedCode(null), 2000);
    };

    const handleCopyCode = (code: string) => {
        void navigator.clipboard.writeText(code);
        setCopiedCode(code);
        setTimeout(() => setCopiedCode(null), 2000);
    };

    const activeInvites = invites.filter((inv) => inv.is_active && !inv.used_by);

    return (
        <>
            <Card title="Usuários">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                    <input
                        value={userSearch}
                        onChange={(event) => onUserSearchChange(event.target.value)}
                        placeholder="Buscar por username ou nome"
                        className="flex-1 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    />
                    <Button onClick={() => setInviteModalOpen(true)} className="w-full sm:w-auto">
                        <UserPlus className="mr-1 h-4 w-4" />
                        Convidar
                    </Button>
                </div>
                <div className="mb-3">
                    <SelectField
                        value={userActivityFilter}
                        options={userActivityOptions}
                        onValueChange={(value) => onUserActivityFilterChange(value as ActivityFilter)}
                        className="w-full sm:w-[220px]"
                        triggerClassName="text-xs text-zinc-700"
                    />
                </div>

                <div className="table-scroll">
                    <table className="w-full table-fixed text-left text-sm">
                        <colgroup>
                            <col className="w-10" />
                            <col />
                            <col className="hidden sm:table-column" />
                            <col className="w-16" />
                        </colgroup>
                        <thead className="text-zinc-600">
                            <tr className="border-b border-zinc-200">
                                <th className="py-2">ID</th>
                                <th className="py-2">Username</th>
                                <th className="hidden py-2 sm:table-cell">Nome</th>
                                <th className="py-2">Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            {usersFiltered.map((u) => (
                                <tr key={u.id} className="border-b border-zinc-200/70">
                                    <td className="py-2">{u.id}</td>
                                    <td className="py-2">
                                        <span className="block truncate">{u.username}</span>
                                        <span className="block truncate text-[11px] text-zinc-500 sm:hidden">{u.full_name || '-'}</span>
                                    </td>
                                    <td className="hidden py-2 sm:table-cell">{u.full_name || '-'}</td>
                                    <td className="py-2">
                                        <Button size="sm" variant="ghost" onClick={() => onSelectUser(u, 'view')} title="Ver">
                                            <Eye className="h-4 w-4" />
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                            {usersFiltered.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="py-6 text-center text-zinc-500">Nenhum usuário encontrado.</td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </Card>

            <Modal
                isOpen={inviteModalOpen}
                onClose={() => setInviteModalOpen(false)}
                title="Convites de cadastro"
            >
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <p className="text-sm text-zinc-600">
                            {loadingInvites ? 'Carregando...' : `${activeInvites.length} convite(s) ativo(s)`}
                        </p>
                        <Button
                            size="sm"
                            onClick={() => void handleGenerateInvite()}
                            disabled={generatingInvite}
                        >
                            <UserPlus className="mr-1 h-4 w-4" />
                            {generatingInvite ? 'Gerando...' : 'Gerar convite'}
                        </Button>
                    </div>

                    {inviteError ? (
                        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                            {inviteError}
                        </div>
                    ) : null}

                    {activeInvites.length > 0 ? (
                        <div className="space-y-2">
                            {activeInvites.map((invite) => (
                                <div
                                    key={invite.id}
                                    className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-zinc-50 p-3 sm:flex-row sm:items-center sm:justify-between"
                                >
                                    <div className="space-y-0.5">
                                        <p className="font-mono text-sm font-semibold tracking-wider text-zinc-900">
                                            {invite.code}
                                        </p>
                                        <p className="text-[11px] text-zinc-500">
                                            Expira em: {formatExpiresAt(invite.expires_at)}
                                        </p>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            title="Copiar código"
                                            onClick={() => handleCopyCode(invite.code)}
                                        >
                                            <Copy className="h-3.5 w-3.5" />
                                            {copiedCode === invite.code ? (
                                                <span className="ml-1 text-[11px] text-emerald-600">Copiado!</span>
                                            ) : null}
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            title="Copiar link de registro"
                                            onClick={() => handleCopyInviteLink(invite.code)}
                                        >
                                            <Link2 className="h-3.5 w-3.5" />
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            title="Revogar convite"
                                            onClick={() => void handleRevokeInvite(invite.id)}
                                        >
                                            <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : !loadingInvites ? (
                        <p className="py-4 text-center text-sm text-zinc-500">
                            Nenhum convite ativo. Gere um convite para convidar um novo usuário.
                        </p>
                    ) : null}
                </div>
            </Modal>
        </>
    );
};
