import { useState } from 'react';
import { Calendar, History, Pencil, StopCircle } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { Modal } from '../../../components/ui/Modal';
import type { Record as RecordApi, User } from '../../../lib/api/client';
import type { PlaceItem } from '../types';
import { formatDateTime, getPlaceLabel, getRecordPublicCode } from '../utils';

type UserViewPageProps = {
    selectedUser: User;
    onCloseView: () => void;
    onToggleUserActive: (user: User) => void;
    onResetPassword: (user: User) => void;
    onToggleHistory: () => void;
    showUserHistory: boolean;
    recordsForSelectedUser: RecordApi[];
    places: PlaceItem[];
    passwordResetUsers: number[];
};

export const UserViewPage = ({
    selectedUser,
    onCloseView,
    onToggleUserActive,
    onResetPassword,
    onToggleHistory,
    showUserHistory,
    recordsForSelectedUser,
    places,
    passwordResetUsers,
}: UserViewPageProps) => {
    const [dateModalRecord, setDateModalRecord] = useState<RecordApi | null>(null);

    return (
        <Card title="Detalhes do usuário" onBack={onCloseView}>
            <p className="mb-4 text-sm text-zinc-600">Informações do usuário.</p>
            <div className="grid grid-cols-[110px,minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-sm sm:grid-cols-[130px,minmax(0,1fr)]">
                <p className="text-right text-zinc-600">Nome</p>
                <p className="text-left">{selectedUser.full_name || '-'}</p>
                <p className="text-right text-zinc-600">Username</p>
                <p className="text-left">{selectedUser.username}</p>
                <p className="text-right text-zinc-600">Perfil</p>
                <p className="text-left">{selectedUser.is_superuser ? 'master' : 'user'}</p>
                <p className="text-right text-zinc-600">Status</p>
                <p className="text-left">{selectedUser.is_active ? 'ativo' : 'inativo'}</p>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => onToggleUserActive(selectedUser)}>
                    <StopCircle className="mr-2 h-4 w-4" />
                    {selectedUser.is_active ? 'Desativar' : 'Ativar'}
                </Button>
                {!passwordResetUsers.includes(selectedUser.id) ? (
                    <Button variant="ghost" onClick={() => onResetPassword(selectedUser)}>
                        <Pencil className="mr-2 h-4 w-4" /> Resetar senha
                    </Button>
                ) : null}
                <Button variant="ghost" onClick={onToggleHistory}>
                    <History className="mr-2 h-4 w-4" />
                    {showUserHistory ? 'Ocultar histórico' : 'Histórico'}
                </Button>
                <Button variant="ghost" onClick={onCloseView}>Fechar</Button>
            </div>

            {showUserHistory ? (
                <div className="mt-6">
                    <p className="mb-2 text-sm text-zinc-600">Histórico de gravações</p>
                    <div className="table-scroll">
                        <table className="w-full table-fixed text-left text-sm">
                            <colgroup>
                                <col className="w-10" />
                                <col className="hidden sm:table-column" />
                                <col />
                                <col className="hidden md:table-column" />
                                <col className="hidden md:table-column" />
                                <col className="w-12 md:hidden" />
                            </colgroup>
                            <thead className="text-zinc-600">
                                <tr className="border-b border-zinc-200">
                                    <th className="py-2">Código</th>
                                    <th className="hidden py-2 sm:table-cell">Disp.</th>
                                    <th className="py-2">Título</th>
                                    <th className="hidden py-2 md:table-cell">Início</th>
                                    <th className="hidden py-2 md:table-cell">Fim</th>
                                    <th className="py-2 text-center md:hidden">Datas</th>
                                </tr>
                            </thead>
                            <tbody>
                                {recordsForSelectedUser.map((record) => (
                                    <tr key={record.id} className="border-b border-zinc-200/70">
                                        <td className="py-2">
                                            <span className="block truncate">{getRecordPublicCode(record)}</span>
                                        </td>
                                        <td className="hidden py-2 sm:table-cell">{record.device_id}</td>
                                        <td className="py-2">
                                            <span className="block truncate">{record.title || '-'}</span>
                                            <span className="block truncate text-[11px] text-zinc-500">
                                                {getPlaceLabel(places, record.place_id)}
                                            </span>
                                        </td>
                                        <td className="hidden py-2 md:table-cell">{formatDateTime(record.start_time)}</td>
                                        <td className="hidden py-2 md:table-cell">{formatDateTime(record.end_time)}</td>
                                        <td className="py-2 text-center md:hidden">
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                title="Ver datas"
                                                onClick={() => setDateModalRecord(record)}
                                            >
                                                <Calendar className="h-4 w-4" />
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                                {recordsForSelectedUser.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="py-6 text-center text-zinc-500">Sem registros.</td>
                                    </tr>
                                ) : null}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : null}

            <Modal
                isOpen={dateModalRecord !== null}
                onClose={() => setDateModalRecord(null)}
                title="Datas da gravação"
            >
                <div className="space-y-2 text-sm text-zinc-700">
                    <p><span className="text-zinc-500">Código:</span> {dateModalRecord ? getRecordPublicCode(dateModalRecord) : '-'}</p>
                    <p><span className="text-zinc-500">Início:</span> {formatDateTime(dateModalRecord?.start_time || null)}</p>
                    <p><span className="text-zinc-500">Fim:</span> {formatDateTime(dateModalRecord?.end_time || null)}</p>
                </div>
            </Modal>
        </Card>
    );
};
