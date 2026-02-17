import type { FormEvent } from 'react';
import { Eye, Plus } from 'lucide-react';
import { Button } from '../../../../components/ui/Button';
import { IconActionButton } from '../../../../components/ui/IconActionButton';
import { SelectField } from '../../../../components/ui/SelectField';

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

type ProtocolsTabProps = {
    protocolSearch: string;
    onProtocolSearchChange: (value: string) => void;
    showInactiveProtocols: boolean;
    onShowInactiveProtocolsChange: (value: boolean) => void;
    filteredProtocols: ProtocolItem[];
    protocolForm: ProtocolFormState;
    onProtocolFormChange: (next: ProtocolFormState) => void;
    editingProtocolId: number | null;
    showProtocolForm: boolean;
    onOpenCreateProtocol: () => void;
    onCreateProtocol: (event: FormEvent) => Promise<void> | void;
    onCancelProtocolForm: () => void;
    onViewProtocol: (protocol: ProtocolItem) => void;
};

export const ProtocolsTab = ({
    protocolSearch,
    onProtocolSearchChange,
    showInactiveProtocols,
    onShowInactiveProtocolsChange,
    filteredProtocols,
    protocolForm,
    onProtocolFormChange,
    editingProtocolId,
    showProtocolForm,
    onOpenCreateProtocol,
    onCreateProtocol,
    onCancelProtocolForm,
    onViewProtocol,
}: ProtocolsTabProps) => {
    const visibilityOptions = [
        { value: 'all', label: 'Todos (ativos)' },
        { value: 'inactive', label: 'Somente desativados' },
    ];

    return (
        <div className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <input
                value={protocolSearch}
                onChange={(event) => onProtocolSearchChange(event.target.value)}
                placeholder="Buscar protocolo"
                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
            />
            <Button onClick={onOpenCreateProtocol} className="w-full sm:ml-2 sm:w-auto">
                <Plus className="mr-1 h-4 w-4" />
                Adicionar
            </Button>
        </div>

        <SelectField
            value={showInactiveProtocols ? 'inactive' : 'all'}
            options={visibilityOptions}
            onValueChange={(value) => onShowInactiveProtocolsChange(value === 'inactive')}
            className="w-full sm:w-[220px]"
            triggerClassName="text-xs text-zinc-700"
        />

        {showProtocolForm ? (
            <form onSubmit={onCreateProtocol} className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <div className="grid gap-2 md:grid-cols-[1fr,160px,auto]">
                    <input
                        value={protocolForm.protocol}
                        onChange={(event) => onProtocolFormChange({ ...protocolForm, protocol: event.target.value })}
                        placeholder="Protocolo"
                        className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    />
                    <input
                        value={protocolForm.port}
                        onChange={(event) => onProtocolFormChange({ ...protocolForm, port: event.target.value })}
                        placeholder="Porta"
                        className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    />
                    <div className="flex gap-2">
                        <Button type="submit" size="sm">
                            {editingProtocolId ? 'Salvar' : 'Adicionar'}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={onCancelProtocolForm}>
                            Cancelar
                        </Button>
                    </div>
                </div>
            </form>
        ) : null}

        <div className="table-scroll">
            <table className="w-full table-fixed text-left text-sm">
                <colgroup>
                    <col />
                    <col className="hidden sm:table-column" />
                    <col className="w-[170px] sm:w-[190px]" />
                </colgroup>
                <thead className="text-zinc-600">
                    <tr className="border-b border-zinc-200">
                        <th className="py-2">Protocolo</th>
                        <th className="hidden py-2 sm:table-cell">Porta</th>
                        <th className="py-2 whitespace-nowrap">Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {filteredProtocols.map((protocol) => {
                        return (
                            <tr key={protocol.id} className="border-b border-zinc-200/70">
                                <td className="py-2 min-w-[200px] sm:min-w-0">
                                    <span className="block whitespace-normal break-words sm:truncate">{protocol.protocol}</span>
                                    <span className="block truncate text-[11px] text-zinc-500 sm:hidden">{protocol.port}</span>
                                </td>
                                <td className="hidden py-2 sm:table-cell">{protocol.port}</td>
                                <td className="py-2 min-w-[170px]">
                                    <div className="flex flex-nowrap gap-1 overflow-x-auto pb-1 sm:gap-2">
                                        <IconActionButton
                                            icon={Eye}
                                            title="Visualizar"
                                            onClick={() => onViewProtocol(protocol)}
                                        />
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                    {filteredProtocols.length === 0 ? (
                        <tr>
                            <td colSpan={3} className="py-6 text-center text-zinc-500">Sem protocolos.</td>
                        </tr>
                    ) : null}
                </tbody>
            </table>
        </div>
    </div>
    );
};
