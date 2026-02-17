import { useMemo, useState } from 'react';
import { Pencil, PlayCircle, StopCircle } from 'lucide-react';
import type { Dispatch, FormEvent, SetStateAction } from 'react';
import { protocolsAPI } from '../../../../lib/api/client';
import { Button } from '../../../../components/ui/Button';
import { Modal } from '../../../../components/ui/Modal';
import { resolveApiErrorMessage } from '../../errorMessage';
import { ProtocolsTab } from './ProtocolsTab';
import type { ConfirmState, StatusLevel } from '../../types';

type ProtocolItem = {
    id: number;
    protocol: string;
    port: number;
    is_active: boolean;
};

type ProtocolFormState = {
    protocol: string;
    port: string;
};

type ProtocolsSettingsSectionProps = {
    protocols: ProtocolItem[];
    protocolSearch: string;
    setProtocolSearch: (value: string) => void;
    showInactiveProtocols: boolean;
    setShowInactiveProtocols: (value: boolean) => void;
    loadProtocols: () => Promise<void>;
    showStatus: (level: StatusLevel, msg: string) => void;
    setConfirm: Dispatch<SetStateAction<ConfirmState>>;
};

export const ProtocolsSettingsSection = ({
    protocols,
    protocolSearch,
    setProtocolSearch,
    showInactiveProtocols,
    setShowInactiveProtocols,
    loadProtocols,
    showStatus,
    setConfirm,
}: ProtocolsSettingsSectionProps) => {
    const [viewingProtocol, setViewingProtocol] = useState<ProtocolItem | null>(null);
    const [showProtocolForm, setShowProtocolForm] = useState(false);
    const [protocolForm, setProtocolForm] = useState<ProtocolFormState>({ protocol: '', port: '' });
    const [editingProtocolId, setEditingProtocolId] = useState<number | null>(null);

    const filteredProtocols = useMemo(
        () => protocols.filter((protocol) => {
            if (showInactiveProtocols) return protocol.is_active === false;
            return protocol.is_active !== false;
        }).filter((protocol) => {
            const search = protocolSearch.trim().toLowerCase();
            if (!search) return true;
            return protocol.protocol.toLowerCase().includes(search) || String(protocol.port).includes(search);
        }),
        [protocols, showInactiveProtocols, protocolSearch],
    );

    const handleCreateProtocol = async (event: FormEvent) => {
        event.preventDefault();
        if (!protocolForm.protocol.trim() || !protocolForm.port.trim()) {
            showStatus('error', 'Informe protocolo e porta.');
            return;
        }

        try {
            if (editingProtocolId) {
                await protocolsAPI.update(editingProtocolId, {
                    protocol: protocolForm.protocol.trim(),
                    port: Number(protocolForm.port),
                });
            } else {
                await protocolsAPI.create({
                    protocol: protocolForm.protocol.trim(),
                    port: Number(protocolForm.port),
                });
            }
            await loadProtocols();
            setProtocolForm({ protocol: '', port: '' });
            setEditingProtocolId(null);
            setShowProtocolForm(false);
            showStatus('info', 'Protocolo criado.');
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao criar protocolo.'));
        }
    };

    const toggleProtocolActive = async (protocolId: number, nextActive: boolean) => {
        try {
            await protocolsAPI.update(protocolId, { is_active: nextActive });
            await loadProtocols();
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao atualizar protocolo.'));
        }
    };

    const confirmDeactivateProtocol = (protocolId: number, label: string) => {
        setConfirm({
            open: true,
            title: 'Desativar protocolo',
            description: `Desativar ${label}?`,
            confirmLabel: 'Desativar',
            errorFallback: 'Falha ao desativar protocolo.',
            onConfirm: async () => {
                await protocolsAPI.update(protocolId, { is_active: false });
                await loadProtocols();
            },
        });
    };

    const handleToggleProtocolActive = (protocolId: number, nextActive: boolean, label: string) => {
        if (nextActive) {
            void toggleProtocolActive(protocolId, true);
            return;
        }
        confirmDeactivateProtocol(protocolId, label);
    };

    const handleOpenCreateProtocol = () => {
        setEditingProtocolId(null);
        setProtocolForm({ protocol: '', port: '' });
        setShowProtocolForm(true);
    };

    const handleEditProtocol = (protocol: { id: number; protocol: string; port: number }) => {
        setEditingProtocolId(protocol.id);
        setProtocolForm({ protocol: protocol.protocol, port: String(protocol.port) });
        setShowProtocolForm(true);
    };

    const handleCancelProtocolForm = () => {
        setEditingProtocolId(null);
        setProtocolForm({ protocol: '', port: '' });
        setShowProtocolForm(false);
    };

    return (
        <>
            <ProtocolsTab
                protocolSearch={protocolSearch}
                onProtocolSearchChange={setProtocolSearch}
                showInactiveProtocols={showInactiveProtocols}
                onShowInactiveProtocolsChange={setShowInactiveProtocols}
                filteredProtocols={filteredProtocols}
                protocolForm={protocolForm}
                onProtocolFormChange={setProtocolForm}
                editingProtocolId={editingProtocolId}
                showProtocolForm={showProtocolForm}
                onOpenCreateProtocol={handleOpenCreateProtocol}
                onCreateProtocol={handleCreateProtocol}
                onCancelProtocolForm={handleCancelProtocolForm}
                onViewProtocol={setViewingProtocol}
            />
            <Modal
                isOpen={!!viewingProtocol}
                onClose={() => setViewingProtocol(null)}
                title="Detalhe do protocolo"
            >
                {viewingProtocol ? (
                    <div className="space-y-4 text-sm">
                        <div className="grid grid-cols-[120px,minmax(0,1fr)] gap-y-2">
                            <p className="text-zinc-600">ID</p>
                            <p>{viewingProtocol.id}</p>
                            <p className="text-zinc-600">Protocolo</p>
                            <p>{viewingProtocol.protocol}</p>
                            <p className="text-zinc-600">Porta</p>
                            <p>{viewingProtocol.port}</p>
                            <p className="text-zinc-600">Status</p>
                            <p>{viewingProtocol.is_active ? 'Ativo' : 'Desativado'}</p>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    handleEditProtocol(viewingProtocol);
                                    setViewingProtocol(null);
                                }}
                            >
                                <Pencil className="mr-2 h-4 w-4" />
                                Editar
                            </Button>
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                    const label = `${viewingProtocol.protocol}:${viewingProtocol.port}`;
                                    handleToggleProtocolActive(viewingProtocol.id, !viewingProtocol.is_active, label);
                                    setViewingProtocol(null);
                                }}
                            >
                                {viewingProtocol.is_active ? (
                                    <StopCircle className="mr-2 h-4 w-4" />
                                ) : (
                                    <PlayCircle className="mr-2 h-4 w-4" />
                                )}
                                {viewingProtocol.is_active ? 'Desativar' : 'Ativar'}
                            </Button>
                        </div>
                    </div>
                ) : null}
            </Modal>
        </>
    );
};
