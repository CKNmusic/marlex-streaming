import { useCallback, useState } from 'react';
import { Eye, Plus } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { SelectField } from '../../../components/ui/SelectField';
import type { Device, DeviceStatus } from '../../../lib/api/client';
import type { DeviceActivityFilter, PlaceItem } from '../types';
import { SortableHeader } from '../components/SortableHeader';
import { DeviceStatusIconButton } from '../components/DeviceStatusIconButton';
import { DeviceStatusInfoModal } from '../components/DeviceStatusInfoModal';
import { useSortableTable } from '../hooks/useSortableTable';
import { getDeviceRuntimeStatusFromSnapshot, normalizeDeviceRuntimeStatus } from '../status';

type DeviceSortKey = 'name' | 'sn' | 'place' | 'status';

const getDeviceRowClass = (status: string) => {
    if (status === 'Recording') return 'border-b border-zinc-200/70 bg-red-50/50';
    if (status === 'Online' || status === 'Starting' || status === 'Stopping') return 'border-b border-zinc-200/70 bg-emerald-50/50';
    return 'border-b border-zinc-200/70';
};

type DevicesListPageProps = {
    devicesFiltered: Device[];
    places: PlaceItem[];
    deviceStatus: Record<number, DeviceStatus>;
    deviceSearch: string;
    deviceActivityFilter: DeviceActivityFilter;
    onDeviceSearchChange: (value: string) => void;
    onDeviceActivityFilterChange: (value: DeviceActivityFilter) => void;
    onOpenDeviceNew: () => void;
    onOpenDeviceView: (device: Device) => void;
};

export const DevicesListPage = ({
    devicesFiltered,
    places,
    deviceStatus,
    deviceSearch,
    deviceActivityFilter,
    onDeviceSearchChange,
    onDeviceActivityFilterChange,
    onOpenDeviceNew,
    onOpenDeviceView,
}: DevicesListPageProps) => {
    const deviceActivityOptions = [
        { value: 'all', label: 'Todos (ativos)' },
        { value: 'online', label: 'Mostrar apenas Onlines' },
        { value: 'inactive', label: 'Somente desativados' },
    ];
    const [statusModal, setStatusModal] = useState<ReturnType<typeof normalizeDeviceRuntimeStatus> | null>(null);

    const getDeviceSortValue = useCallback((device: Device, key: DeviceSortKey): string | number => {
        if (key === 'name') {
            return [String(device.mark_name || '').trim(), String(device.model || device.name || '').trim()].filter(Boolean).join(' ');
        }
        if (key === 'sn') return device.sn || '';
        if (key === 'place') return places.find((p) => p.id === device.place_id)?.name || '';
        if (key === 'status') return getDeviceRuntimeStatusFromSnapshot(deviceStatus[device.id]);
        return '';
    }, [places, deviceStatus]);
    const { sorted: devicesSorted, sortKey, sortDir, onSort } = useSortableTable<Device, DeviceSortKey>(
        devicesFiltered, 'name', 'asc', getDeviceSortValue,
    );

    return (
        <>
            <Card title="Dispositivos">
                <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <input
                        value={deviceSearch}
                        onChange={(event) => onDeviceSearchChange(event.target.value)}
                        placeholder="Buscar por nome, SN ou local"
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
                    />
                    <Button onClick={onOpenDeviceNew} className="w-full sm:ml-2 sm:w-auto">
                        <Plus className="mr-1 h-4 w-4" />
                        Adicionar
                    </Button>
                </div>
                <div className="mb-3 flex items-center gap-2 text-xs text-zinc-600">
                    <SelectField
                        value={deviceActivityFilter}
                        options={deviceActivityOptions}
                        onValueChange={(value) => onDeviceActivityFilterChange(value as DeviceActivityFilter)}
                        className="w-full sm:w-[260px]"
                        triggerClassName="text-xs text-zinc-700"
                    />
                </div>

                <div className="table-scroll">
                    <table className="w-full table-fixed text-left text-sm">
                        <colgroup>
                            <col />
                            <col className="hidden sm:table-column" />
                            <col className="hidden md:table-column" />
                            <col className="hidden md:table-column" />
                            <col className="w-14" />
                            <col className="w-16" />
                        </colgroup>
                        <thead className="text-zinc-600">
                            <tr className="border-b border-zinc-200">
                                <SortableHeader<DeviceSortKey> label="Nome" sortKey="name" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                                <SortableHeader<DeviceSortKey> label="SN" sortKey="sn" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                                <SortableHeader<DeviceSortKey> label="Local" sortKey="place" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden md:table-cell" />
                                <th className="hidden py-2 md:table-cell">Cidade</th>
                                <SortableHeader<DeviceSortKey> label="Status" sortKey="status" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                                <th className="py-2">Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            {devicesSorted.map((device) => {
                                const place = places.find((item) => item.id === device.place_id);
                                const status = getDeviceRuntimeStatusFromSnapshot(deviceStatus[device.id]);
                                return (
                                    <tr key={device.id} className={getDeviceRowClass(status)}>
                                        <td className="py-2">
                                            <span className="block truncate">
                                                {[String(device.mark_name || '').trim(), String(device.model || device.name || '').trim()]
                                                    .filter(Boolean)
                                                    .join(' ')}
                                            </span>
                                            <span className="block truncate text-[11px] text-zinc-500 md:hidden">
                                                {place ? (place.city !== '-' ? `${place.name} - ${place.city}/${place.state}` : place.name) : '-'}
                                            </span>
                                        </td>
                                        <td className="hidden py-2 sm:table-cell">{device.sn}</td>
                                        <td className="hidden py-2 md:table-cell">{place?.name || '-'}</td>
                                        <td className="hidden py-2 md:table-cell">{place && place.city !== '-' ? `${place.city}/${place.state}` : '-'}</td>
                                        <td className="py-2">
                                            <DeviceStatusIconButton status={status} onClick={() => setStatusModal(status)} />
                                        </td>
                                        <td className="py-2">
                                            <Button size="sm" variant="ghost" onClick={() => onOpenDeviceView(device)} title="Ver">
                                                <Eye className="h-4 w-4" />
                                            </Button>
                                        </td>
                                    </tr>
                                );
                            })}
                            {devicesSorted.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="py-6 text-center text-zinc-500">Nenhum dispositivo cadastrado.</td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </Card>

            <DeviceStatusInfoModal
                isOpen={statusModal !== null}
                status={statusModal || 'Offline'}
                onClose={() => setStatusModal(null)}
            />
        </>
    );
};
