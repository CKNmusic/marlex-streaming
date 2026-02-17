import { useMemo, useState } from 'react';
import { Copy, Eye, Pencil, Printer } from 'lucide-react';
import { APP_NAME, APP_VERSION } from '../../../lib/api/client';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { Modal } from '../../../components/ui/Modal';
import { LiveStreamPlayer } from '../../../components/LiveStreamPlayer';
import type { Device, DeviceStatus } from '../../../lib/api/client';
import { getDeviceRuntimeStatusFromSnapshot } from '../status';
import type { PlaceItem } from '../types';

type DeviceViewPageProps = {
    selectedDevice: Device;
    places: PlaceItem[];
    deviceStatus: Record<number, DeviceStatus>;
    qrImageUrl: string;
    showQrCode: boolean;
    protocols: Array<{ protocol: string; port: number; url: string; is_active: boolean }>;
    scanUrl: string;
    onViewBack: () => void;
    onOpenPrintModal: (open: boolean) => void;
    onGenerateQrCode: () => void;
    onOpenDeviceEdit: (device: Device) => void;
};

export const DeviceViewPage = ({
    selectedDevice,
    places,
    deviceStatus,
    qrImageUrl,
    showQrCode,
    protocols,
    scanUrl,
    onViewBack,
    onOpenPrintModal,
    onGenerateQrCode,
    onOpenDeviceEdit,
}: DeviceViewPageProps) => {
    const place = places.find((item) => item.id === selectedDevice.place_id);
    const selectedStatus = getDeviceRuntimeStatusFromSnapshot(deviceStatus[selectedDevice.id]);
    const selectedProtocol = String(selectedDevice.protocol || '').trim().toLowerCase();
    const status = deviceStatus[selectedDevice.id];
    const isOnline = status?.online === true;
    const [liveOpen, setLiveOpen] = useState(false);

    const whepUrl = useMemo(() => {
        const deviceKey = (selectedDevice.key || '').trim();
        if (!deviceKey) return null;
        const origin = window.location.origin;
        const streamPath = `${APP_NAME}/${APP_VERSION}/${encodeURIComponent(deviceKey)}/stream`;
        return `${origin}/webrtc/${streamPath}/whep`;
    }, [selectedDevice.key]);

    return (
        <>
            <Card
                title="Detalhe do dispositivo"
                onBack={onViewBack}
                headerActions={(
                    <div className="flex items-center gap-1">
                        {isOnline && whepUrl && (
                            <Button size="sm" variant="ghost" onClick={() => setLiveOpen(true)} title="Ver ao vivo">
                                <Eye className="mr-1 h-4 w-4" />
                                Ao vivo
                            </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => onOpenDeviceEdit(selectedDevice)} title="Editar">
                            <Pencil className="mr-1 h-4 w-4" />
                            Editar
                        </Button>
                    </div>
                )}
            >
                <div className="grid gap-4 lg:grid-cols-2">
                    <div className="grid grid-cols-[90px,minmax(0,1fr)] items-center gap-x-2 gap-y-2 text-sm sm:grid-cols-[130px,minmax(0,1fr)] sm:gap-x-3">
                        <p className="text-right text-zinc-600">ID</p>
                        <p className="text-left">{selectedDevice.id}</p>
                        <p className="text-right text-zinc-600">Marca</p>
                        <p className="text-left">{String(selectedDevice.mark_name || '').trim() || '-'}</p>
                        <p className="text-right text-zinc-600">Modelo</p>
                        <p className="text-left">{String(selectedDevice.model || selectedDevice.name || '').trim() || '-'}</p>
                        <p className="text-right text-zinc-600">SN</p>
                        <p className="text-left">{selectedDevice.sn}</p>
                        <p className="text-right text-zinc-600">Status</p>
                        <p className="text-left">{selectedStatus}</p>
                        <p className="text-right text-zinc-600">Key</p>
                        <p className="text-left break-all">{selectedDevice.key || '-'}</p>
                        <p className="text-right text-zinc-600">Local</p>
                        <p className="text-left break-words">{place ? (place.city !== '-' ? `${place.name} - ${place.city}/${place.state}` : place.name) : '-'}</p>
                    </div>
                    <div className="space-y-3">
                        <div className="rounded-lg bg-white p-3">
                            {showQrCode && qrImageUrl ? (
                                <img src={qrImageUrl} alt="QR Code" className="mx-auto h-48 w-48" />
                            ) : (
                                <div className="flex min-h-[12rem] items-center justify-center">
                                    <Button variant="secondary" size="sm" onClick={onGenerateQrCode}>
                                        Gerar QR Code
                                    </Button>
                                </div>
                            )}
                        </div>
                        <div className="space-y-2 rounded-md border border-zinc-200 bg-white p-3 text-xs">
                            {protocols.map((item) => {
                                const isConfigured = String(item.protocol || '').trim().toLowerCase() === selectedProtocol;
                                const canCopy = !!item.url && item.url !== '-';
                                return (
                                    <div
                                        key={item.protocol}
                                        className={`rounded-md p-2 ${isConfigured ? 'border-2 border-blue-400 bg-blue-50/50' : 'border border-zinc-200 bg-zinc-50'}`}
                                    >
                                        <div className="mb-1 flex items-center justify-between gap-2">
                                            <span className="flex items-center gap-2">
                                                <strong>{item.protocol.toUpperCase()} : {item.port || '-'}</strong>
                                                {isConfigured && (
                                                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                                                        Configurado
                                                    </span>
                                                )}
                                            </span>
                                            <Button
                                                size="sm"
                                                variant="secondary"
                                                className="h-7 shrink-0 whitespace-nowrap px-2 py-0 text-[11px]"
                                                onClick={() => navigator.clipboard.writeText(item.url || '')}
                                                disabled={!canCopy}
                                            >
                                                <Copy className="mr-1 h-3 w-3" /> Copiar
                                            </Button>
                                        </div>
                                        <p className="font-mono break-all">{item.url || '-'}</p>
                                    </div>
                                );
                            })}
                            <p><strong>Scan URL:</strong></p>
                            <p> <span className="font-mono break-all">{scanUrl || '-'}</span></p>
                            <div className="flex flex-nowrap gap-2 overflow-x-auto pb-1">
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="shrink-0 whitespace-nowrap"
                                    onClick={() => onOpenPrintModal(true)}
                                >
                                    <Printer className="mr-1 h-3 w-3" /> Imprimir
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </Card>

            {/* Modal ao vivo */}
            <Modal isOpen={liveOpen} onClose={() => setLiveOpen(false)} title={`${String(selectedDevice.model || selectedDevice.name || 'Dispositivo').trim()} - Ao vivo`} size="xl">
                {whepUrl && (
                    <LiveStreamPlayer src={whepUrl} className="aspect-video w-full" />
                )}
            </Modal>
        </>
    );
};
