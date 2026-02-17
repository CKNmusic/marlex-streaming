import { useCallback, useState } from 'react';
import { Copy, Eye, PlayCircle, StopCircle } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { SelectField } from '../../../components/ui/SelectField';
import type { Device, DeviceStatus, Record as RecordApi, User } from '../../../lib/api/client';
import type { ActivityFilter, PlaceItem } from '../types';
import { SortableHeader } from '../components/SortableHeader';
import { useSortableTable } from '../hooks/useSortableTable';
import { formatDateTime, formatTransferRate, getPlaceLabel, getRecordPublicCode, resolveUserLabel } from '../utils';
import { RecordStatusIconButton } from './RecordStatusIconButton';
import { RecordStatusInfoModal } from './RecordStatusInfoModal';
import { getRecordStatusTitle, resolveRecordLifecycleStatus } from './status';

type RecordSortKey = 'code' | 'title' | 'date' | 'status';

const getRecordRowClass = (status: string) => {
    if (status === 'Recording') return 'border-b border-zinc-200/70 bg-emerald-50/50';
    if (status === 'Failed') return 'border-b border-zinc-200/70 bg-red-50/50';
    return 'border-b border-zinc-200/70';
};

type RecordsListPageProps = {
    isAdmin: boolean;
    user: User | null;
    records: RecordApi[];
    users: User[];
    places: PlaceItem[];
    recordSearch: string;
    boundDevice: Device | null;
    deviceStatus: Record<number, DeviceStatus>;
    recordActivityFilter: ActivityFilter;
    currentOpenRecord: RecordApi | null;
    onRecordSearchChange: (value: string) => void;
    onRecordActivityFilterChange: (value: ActivityFilter) => void;
    onStopRecord: (recordId: number) => Promise<void> | void;
    onOpenRecordNew: () => void;
    onOpenRecordView: (record: RecordApi) => void;
};

export const RecordsListPage = ({
    isAdmin,
    user,
    records,
    users,
    places,
    recordSearch,
    boundDevice,
    deviceStatus,
    recordActivityFilter,
    currentOpenRecord,
    onRecordSearchChange,
    onRecordActivityFilterChange,
    onStopRecord,
    onOpenRecordNew,
    onOpenRecordView,
}: RecordsListPageProps) => {
    const activityOptions = [
        { value: 'all', label: 'Todos' },
        { value: 'active', label: 'Mostrar apenas em andamento' },
        { value: 'inactive', label: 'Mostrar apenas finalizadas' },
    ];
    const [statusModalRecord, setStatusModalRecord] = useState<RecordApi | null>(null);
    const userRecords = isAdmin ? records : records.filter((record) => record.owner_id === user?.id);
    const recordSearchValue = recordSearch.trim().toLowerCase();
    const recordsBySelector = userRecords.filter((record) => {
        if (recordActivityFilter === 'active') return !record.end_time;
        if (recordActivityFilter === 'inactive') return !!record.end_time;
        return true;
    });
    const recordsFiltered = !recordSearchValue
        ? recordsBySelector
        : recordsBySelector.filter((record) => {
            const placeLabel = getPlaceLabel(places, record.place_id).toLowerCase();
            const userLabel = resolveUserLabel(users, record.owner_id).toLowerCase();
            const publicId = getRecordPublicCode(record).toLowerCase();
            return (
                publicId.includes(recordSearchValue)
                || String(record.device_id).includes(recordSearchValue)
                || (record.title || '').toLowerCase().includes(recordSearchValue)
                || (record.description || '').toLowerCase().includes(recordSearchValue)
                || placeLabel.includes(recordSearchValue)
                || (isAdmin && userLabel.includes(recordSearchValue))
            );
        });

    const getRecordSortValue = useCallback((record: RecordApi, key: RecordSortKey): string | number => {
        if (key === 'code') return getRecordPublicCode(record);
        if (key === 'title') return record.title || '';
        if (key === 'date') return record.start_time || '';
        if (key === 'status') return resolveRecordLifecycleStatus(record);
        return '';
    }, []);
    const { sorted: recordsSorted, sortKey, sortDir, onSort } = useSortableTable<RecordApi, RecordSortKey>(
        recordsFiltered, 'date', 'desc', getRecordSortValue,
    );

    const canShowStart = isAdmin || !!boundDevice;
    return (
        <>
            <Card title="Gravações">
                <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <input
                        value={recordSearch}
                        onChange={(event) => onRecordSearchChange(event.target.value)}
                        placeholder={isAdmin ? 'Buscar por código, título, descrição, local ou usuário' : 'Buscar por código, título, descrição ou local'}
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
                    />
                    {canShowStart ? (
                        <Button onClick={onOpenRecordNew} className="w-full sm:w-auto">
                            <PlayCircle className="mr-2 h-4 w-4" /> Iniciar gravação
                        </Button>
                    ) : null}
                </div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                    <SelectField
                        value={recordActivityFilter}
                        options={activityOptions}
                        onValueChange={(value) => onRecordActivityFilterChange(value as ActivityFilter)}
                        className="w-full sm:w-[280px]"
                        triggerClassName="text-xs text-zinc-700"
                    />
                </div>

                {currentOpenRecord ? (
                    <div className="mb-4 flex flex-col gap-2 rounded-lg border border-zinc-200 p-3 text-xs text-zinc-700 sm:flex-row sm:items-center sm:justify-between">
                        <div className="space-y-0.5">
                            <span className="block font-medium">
                                Gravação em andamento: {getRecordPublicCode(currentOpenRecord)}
                            </span>
                            <span className="block text-[11px] text-zinc-600">
                                Velocidade: {formatTransferRate(currentOpenRecord.transfer_rate_bps, { showWaiting: true })}
                            </span>
                        </div>
                        <Button size="sm" variant="secondary" onClick={() => void onStopRecord(currentOpenRecord.id)}>
                            <StopCircle className="mr-2 h-4 w-4 text-red-600" /> Finalizar gravação
                        </Button>
                    </div>
                ) : null}

                <div className="table-scroll">
                    <table className="w-full table-fixed text-left text-sm">
                        <colgroup>
                            <col className="w-32" />
                            {isAdmin ? <col className="hidden md:table-column w-40" /> : null}
                            <col />
                            <col className="hidden sm:table-column" />
                            <col className="hidden md:table-column w-40" />
                            <col className="w-14" />
                            <col className="w-16" />
                        </colgroup>
                        <thead className="text-zinc-600">
                            <tr className="border-b border-zinc-200">
                                <SortableHeader<RecordSortKey> label="Código" sortKey="code" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                                {isAdmin ? <th className="hidden py-2 md:table-cell">Usuário</th> : null}
                                <SortableHeader<RecordSortKey> label="Título" sortKey="title" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                                <th className="hidden py-2 sm:table-cell">Local</th>
                                <SortableHeader<RecordSortKey> label="Data" sortKey="date" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden md:table-cell" />
                                <SortableHeader<RecordSortKey> label="Status" sortKey="status" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="text-center" />
                                <th className="py-2 text-center">Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recordsSorted.map((record) => {
                                const status = resolveRecordLifecycleStatus(record);
                                const statusTitle = getRecordStatusTitle(status, record);
                                const placeLabel = getPlaceLabel(places, record.place_id);
                                return (
                                    <tr key={record.id} className={getRecordRowClass(status)}>
                                        <td className="py-2">
                                            <span className="block truncate">{getRecordPublicCode(record)}</span>
                                        </td>
                                        {isAdmin ? (
                                            <td className="hidden py-2 md:table-cell">
                                                <span className="block truncate">{resolveUserLabel(users, record.owner_id)}</span>
                                            </td>
                                        ) : null}
                                        <td className="py-2">
                                            <span title={record.title || '-'} className="block truncate">
                                                {record.title || '-'}
                                            </span>
                                            <span className="block truncate text-[11px] text-zinc-500 sm:hidden">
                                                {placeLabel}
                                            </span>
                                            <span className="block truncate text-[11px] text-zinc-500 md:hidden">
                                                {formatDateTime(record.start_time, { includeSeconds: false })}
                                            </span>
                                        </td>
                                        <td className="hidden py-2 sm:table-cell">
                                            <span className="block truncate">{placeLabel}</span>
                                        </td>
                                        <td className="hidden py-2 md:table-cell whitespace-nowrap">
                                            {formatDateTime(record.start_time, { includeSeconds: false })}
                                        </td>
                                        <td className="py-2 text-center">
                                            <div className="flex flex-col items-center justify-center gap-0.5">
                                                <RecordStatusIconButton
                                                    status={status}
                                                    title={statusTitle}
                                                    onClick={() => setStatusModalRecord(record)}
                                                />
                                                {status === 'Recording' ? (
                                                    <span className="text-[10px] font-medium text-zinc-600">
                                                        {formatTransferRate(record.transfer_rate_bps, { showWaiting: true })}
                                                    </span>
                                                ) : null}
                                            </div>
                                        </td>
                                        <td className="py-2 text-center">
                                            <div className="flex items-center justify-center gap-0.5">
                                                {status === 'Recording' && deviceStatus[record.device_id]?.stream_url ? (
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        className="h-8 w-8 p-0"
                                                        onClick={() => void navigator.clipboard.writeText(deviceStatus[record.device_id]?.stream_url || '')}
                                                        title="Copiar link ao vivo"
                                                    >
                                                        <Copy className="h-3.5 w-3.5 text-emerald-600" />
                                                    </Button>
                                                ) : null}
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="h-8 w-8 p-0"
                                                    onClick={() => onOpenRecordView(record)}
                                                    title="Visualizar"
                                                >
                                                    <Eye className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                            {recordsSorted.length === 0 ? (
                                <tr>
                                    <td colSpan={isAdmin ? 7 : 6} className="py-6 text-center text-zinc-500">
                                        Nenhuma gravação encontrada.
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </Card>
            <RecordStatusInfoModal
                isOpen={statusModalRecord !== null}
                record={statusModalRecord}
                onClose={() => setStatusModalRecord(null)}
            />
        </>
    );
};
