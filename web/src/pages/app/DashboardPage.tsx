import { ArrowDownCircle, ArrowUpCircle, Copy, Cpu, Film, MemoryStick, QrCode, Video } from 'lucide-react';
import type { Device, DeviceStatus, ManagerMetric, Procedure, Record as RecordApi, User } from '../../lib/api/client';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { isOnlineDeviceRuntimeSnapshot } from './status';
import type { ActivityFilter, DeviceActivityFilter, PlaceItem } from './types';
import { formatDateTime, getPlaceLabel, getProcedureLabel, getRecordPublicCode } from './utils';

const DASHBOARD_CARD_CLASS = 'h-full min-h-[56px] !p-2 sm:!p-3';

type MetricCardProps = {
    label: string;
    value: number;
    onAction?: () => void;
};

const MetricCard = ({ label, value, onAction }: MetricCardProps) => (
    <Card className={DASHBOARD_CARD_CLASS}>
        <p className="text-[11px] text-zinc-600 sm:text-xs">{label}</p>
        {value > 0 && onAction ? (
            <button className="text-xs font-semibold text-emerald-600 sm:text-sm" onClick={onAction}>
                {value}
            </button>
        ) : (
            <p className="text-xs font-semibold text-zinc-900 sm:text-sm">{value}</p>
        )}
    </Card>
);

const progressStyle = (value: number) => ({
    background: `conic-gradient(#0ea5e9 ${Math.max(0, Math.min(100, value))}%, #e4e4e7 0)`,
});

const formatBps = (value: number) => {
    if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB/s`;
    if (value >= 1024) return `${(value / 1024).toFixed(2)} KB/s`;
    return `${value} B/s`;
};

type DashboardPageProps = {
    isAdmin: boolean;
    users: User[];
    devices: Device[];
    deviceStatus: Record<number, DeviceStatus>;
    records: RecordApi[];
    openRecords: RecordApi[];
    managerMetrics: ManagerMetric | null;
    currentOpenRecord: RecordApi | null;
    places: PlaceItem[];
    procedures: Procedure[];
    recordingBusy: boolean;
    onOpenRecordsList: (filter: ActivityFilter) => void;
    onOpenUsersList: (filter: ActivityFilter) => void;
    onOpenDevicesList: (filter: DeviceActivityFilter) => void;
    onStopRecord: (recordId: number) => Promise<void> | void;
    onOpenRecord: (record: RecordApi) => void;
    onOpenScan: () => void;
    showScanAction: boolean;
};

export const DashboardPage = ({
    isAdmin,
    users,
    devices,
    deviceStatus,
    records,
    openRecords,
    managerMetrics,
    currentOpenRecord,
    places,
    procedures,
    recordingBusy,
    onOpenRecordsList,
    onOpenUsersList,
    onOpenDevicesList,
    onStopRecord,
    onOpenRecord,
    onOpenScan,
    showScanAction,
}: DashboardPageProps) => {
    const userTotal = users.filter((u) => u.is_active).length;
    const userOnline = managerMetrics?.app_users_online || 0;
    const deviceTotal = devices.filter((d) => d.is_active).length;
    const deviceOnline = devices.filter((d) => {
        if (!d.is_active) return false;
        const runtimeStatus = deviceStatus[d.id];
        return isOnlineDeviceRuntimeSnapshot(runtimeStatus);
    }).length;
    const cpuPercent = managerMetrics?.cpu_percent || 0;
    const memPercent = managerMetrics?.memory_percent || 0;
    const downloadBps = managerMetrics?.network.download_bps || 0;
    const uploadBps = managerMetrics?.network.upload_bps || 0;
    const managerRecordings = managerMetrics?.recordings_active || 0;
    const managerPublishers = managerMetrics?.publishers_online || 0;
    const recordsActive = isAdmin ? managerRecordings : openRecords.length;

    return (
        <div className="space-y-6">
            {!isAdmin ? (
                <Card className="!p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <p className="text-sm font-semibold text-zinc-900">Pareamento rápido</p>
                            <p className="text-xs text-zinc-600">Escaneie o QR Code do dispositivo para iniciar o vínculo.</p>
                        </div>
                        {showScanAction ? (
                            <Button size="sm" onClick={onOpenScan} className="inline-flex items-center gap-2">
                                <QrCode className="h-4 w-4" />
                                Escanear QR
                            </Button>
                        ) : null}
                    </div>
                </Card>
            ) : null}
            {openRecords.length > 0 ? (
                <div className="space-y-3">
                    <p className="text-xs font-semibold text-zinc-700">
                        {openRecords.length === 1 ? 'Gravação ativa' : `Gravações ativas (${openRecords.length})`}
                    </p>
                    {openRecords.map((record) => {
                        const streamUrl = deviceStatus[record.device_id]?.stream_url;
                        return (
                            <Card key={record.id} className="!p-4">
                                <div className="flex flex-col gap-3">
                                    <div className="grid gap-2 text-sm text-zinc-700 sm:grid-cols-2">
                                        <p><span className="text-zinc-500">Código:</span> {getRecordPublicCode(record)}</p>
                                        <p><span className="text-zinc-500">Início:</span> {formatDateTime(record.start_time)}</p>
                                        <p><span className="text-zinc-500">Título:</span> {record.title || '-'}</p>
                                        <p><span className="text-zinc-500">Local:</span> {getPlaceLabel(places, record.place_id)}</p>
                                        <p><span className="text-zinc-500">Procedimento:</span> {getProcedureLabel(procedures, record.procedure_id)}</p>
                                        <p><span className="text-zinc-500">Status:</span> {record.final_status || 'recording'}</p>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        <Button size="sm" variant="secondary" onClick={() => onOpenRecord(record)}>
                                            Ver detalhes
                                        </Button>
                                        {streamUrl ? (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => void navigator.clipboard.writeText(streamUrl)}
                                                title="Copiar link ao vivo"
                                            >
                                                <Copy className="mr-1 h-3.5 w-3.5" /> Link ao vivo
                                            </Button>
                                        ) : null}
                                        <Button
                                            size="sm"
                                            variant="danger"
                                            disabled={recordingBusy}
                                            onClick={() => void onStopRecord(record.id)}
                                        >
                                            {recordingBusy ? 'Parando...' : 'STOP'}
                                        </Button>
                                    </div>
                                </div>
                            </Card>
                        );
                    })}
                </div>
            ) : null}
            {isAdmin ? (
                <div className="grid grid-cols-3 gap-2 sm:gap-3">
                    <Card className="!p-4">
                        <div className="flex flex-col items-center justify-center gap-2 text-center">
                            <div
                                className="relative h-14 w-14 rounded-full p-1 sm:h-20 sm:w-20"
                                style={progressStyle(memPercent)}
                            >
                                <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
                                    <MemoryStick className="h-3 w-3 text-sky-600 sm:h-4 sm:w-4" />
                                    <p className="text-xs font-semibold text-zinc-900">{memPercent.toFixed(1)}%</p>
                                </div>
                            </div>
                        </div>
                    </Card>
                    <Card className="!p-4">
                        <div className="space-y-2">
                            <div className="flex items-center gap-1 text-xs font-semibold text-zinc-900 sm:gap-2 sm:text-sm">
                                <ArrowUpCircle className="h-3.5 w-3.5 text-blue-600 sm:h-4 sm:w-4" />
                                <span>{formatBps(uploadBps)}</span>
                            </div>
                            <div className="flex items-center gap-1 text-xs font-semibold text-zinc-900 sm:gap-2 sm:text-sm">
                                <ArrowDownCircle className="h-3.5 w-3.5 text-emerald-600 sm:h-4 sm:w-4" />
                                <span>{formatBps(downloadBps)}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-600">
                                <span className="inline-flex items-center gap-1">
                                    <Video className="h-3.5 w-3.5 text-emerald-600" />
                                    <span>Publishers: {managerPublishers}</span>
                                </span>
                                <span className="inline-flex items-center gap-1">
                                    <Film className="h-3.5 w-3.5 text-red-600" />
                                    <span>Gravando: {managerRecordings}</span>
                                </span>
                            </div>
                        </div>
                    </Card>
                    <Card className="!p-4">
                        <div className="flex flex-col items-center justify-center gap-2 text-center">
                            <div
                                className="relative h-14 w-14 rounded-full p-1 sm:h-20 sm:w-20"
                                style={progressStyle(cpuPercent)}
                            >
                                <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
                                    <Cpu className="h-3 w-3 text-orange-600 sm:h-4 sm:w-4" />
                                    <p className="text-xs font-semibold text-zinc-900">{cpuPercent.toFixed(1)}%</p>
                                </div>
                            </div>
                        </div>
                    </Card>
                </div>
            ) : null}
            <div className="space-y-3">
                <p className="text-xs font-semibold text-zinc-700">Gravações</p>
                <div className="grid grid-cols-2 gap-2 sm:gap-4">
                    <MetricCard label="Total" value={records.length} onAction={() => onOpenRecordsList('all')} />
                    <MetricCard label="Recording" value={recordsActive} onAction={() => onOpenRecordsList('active')} />
                </div>
            </div>
            {isAdmin ? (
                <>
                    <div className="space-y-3">
                        <p className="text-xs font-semibold text-zinc-700">Usuários</p>
                        <div className="grid grid-cols-2 gap-2 sm:gap-4">
                            <MetricCard label="Todos" value={userTotal} onAction={() => onOpenUsersList('all')} />
                            <MetricCard label="Onlines" value={userOnline - 1} />
                        </div>
                    </div>
                    <div className="space-y-3">
                        <p className="text-xs font-semibold text-zinc-700">Dispositivos</p>
                        <div className="grid grid-cols-2 gap-2 sm:gap-4">
                            <MetricCard label="Todos" value={deviceTotal} onAction={() => onOpenDevicesList('all')} />
                            <MetricCard label="Onlines" value={deviceOnline} onAction={() => onOpenDevicesList('online')} />
                        </div>
                    </div>
                </>
            ) : null}
        </div>
    );
};
