import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Cpu, Download, Pencil, User as UserIcon } from 'lucide-react';
import { API_URL, APP_NAME, APP_VERSION } from '../../../lib/api/client';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { LiveStreamPlayer } from '../../../components/LiveStreamPlayer';
import type { Device, DeviceStatus, Record as RecordApi, User } from '../../../lib/api/client';
import type { PlaceItem, UsersView } from '../types';
import { formatDateTime, formatStorageSize, formatTransferRate, getPlaceLabel, getRecordPublicCode, resolveUserLabel } from '../utils';
import type { RecordEditFormState } from './types';
import { getRecordStatusTitle, resolveRecordLifecycleStatus } from './status';

type RecordViewPageProps = {
    isAdmin: boolean;
    selectedRecord: RecordApi;
    users: User[];
    devices: Device[];
    places: PlaceItem[];
    deviceStatus: Record<number, DeviceStatus>;
    recordEditForm: RecordEditFormState;
    savingRecord: boolean;
    outputFormat: string;
    onRecordEditChange: (next: RecordEditFormState) => void;
    onSaveRecordEdit: (event: FormEvent) => Promise<boolean> | boolean;
    onCloseRecordsView: () => void;
    onOpenUserView: (user: User, view: UsersView) => void;
    onOpenDeviceView: (device: Device) => void;
};

export const RecordViewPage = ({
    isAdmin,
    selectedRecord,
    users,
    devices,
    places,
    deviceStatus,
    recordEditForm,
    savingRecord,
    outputFormat,
    onRecordEditChange,
    onSaveRecordEdit,
    onCloseRecordsView,
    onOpenUserView,
    onOpenDeviceView,
}: RecordViewPageProps) => {
    const sessionToken = localStorage.getItem('token') || '';
    const recordUser = users.find((item) => item.id === selectedRecord.owner_id) || null;
    const recordDevice = devices.find((item) => item.id === selectedRecord.device_id) || null;
    const lifecycleStatus = resolveRecordLifecycleStatus(selectedRecord);
    const finalStatusLabel = getRecordStatusTitle(lifecycleStatus, selectedRecord);
    const [editing, setEditing] = useState(false);
    const canDownload = !!selectedRecord.end_time;
    const canPlayback = !!selectedRecord.end_time;
    const isRecording = !selectedRecord.end_time;
    const downloadUrl = `${API_URL}/records/${selectedRecord.id}/stream?token=${encodeURIComponent(sessionToken)}&download=1`;
    const downloadFilename = `${getRecordPublicCode(selectedRecord)}.${outputFormat === 'mkv' ? 'mkv' : 'mp4'}`;

    const status = recordDevice ? deviceStatus[recordDevice.id] : null;
    const isDeviceOnline = status?.online === true;

    const whepUrl = useMemo(() => {
        if (!isRecording || !recordDevice?.key) return null;
        const deviceKey = recordDevice.key.trim();
        if (!deviceKey) return null;
        const origin = window.location.origin;
        const streamPath = `${APP_NAME}/${APP_VERSION}/${encodeURIComponent(deviceKey)}/stream`;
        return `${origin}/webrtc/${streamPath}/whep`;
    }, [isRecording, recordDevice?.key]);

    const handleDownload = () => {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = downloadFilename;
        link.rel = 'noopener noreferrer';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };
    const handleSubmitEdit = async (event: FormEvent) => {
        const saved = await onSaveRecordEdit(event);
        if (saved) {
            setEditing(false);
        }
    };

    return (
        <Card
            title="Detalhe da gravação"
            onBack={onCloseRecordsView}
            headerActions={!editing ? (
                <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                    <Pencil className="mr-1 h-4 w-4" />
                    Editar
                </Button>
            ) : null}
        >
            <div className="mb-4">
                <p className="text-sm font-medium text-zinc-900">{selectedRecord.title || '-'}</p>
                <p className="text-sm text-zinc-600">{selectedRecord.description || '-'}</p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
                <div className="grid grid-cols-[110px,minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-sm sm:grid-cols-[130px,minmax(0,1fr)]">
                    {isAdmin ? (
                        <>
                            <p className="text-right text-zinc-600">Usuário</p>
                            <div className="flex items-center justify-between gap-2 text-left">
                                <span>{resolveUserLabel(users, selectedRecord.owner_id)}</span>
                                {recordUser ? (
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        title="Ver usuário"
                                        onClick={() => onOpenUserView(recordUser, 'view')}
                                    >
                                        <UserIcon className="h-4 w-4" />
                                    </Button>
                                ) : null}
                            </div>
                        </>
                    ) : null}
                    <p className="text-right text-zinc-600">Código</p>
                    <p className="text-left">{getRecordPublicCode(selectedRecord)}</p>
                    <p className="text-right text-zinc-600">Início</p>
                    <p className="text-left">{formatDateTime(selectedRecord.start_time)}</p>
                    <p className="text-right text-zinc-600">Fim</p>
                    <p className="text-left">{formatDateTime(selectedRecord.end_time)}</p>
                    <p className="text-right text-zinc-600">Status</p>
                    <p className="text-left">{finalStatusLabel}</p>
                    <p className="text-right text-zinc-600">Tamanho</p>
                    <p className="text-left">{formatStorageSize(selectedRecord.file_size_bytes)}</p>
                    <p className="text-right text-zinc-600">Velocidade</p>
                    <p className="text-left">{formatTransferRate(selectedRecord.transfer_rate_bps, { showWaiting: !selectedRecord.end_time })}</p>
                    <p className="text-right text-zinc-600">Resolução</p>
                    <p className="text-left">{selectedRecord.video_resolution || '-'}</p>
                    <p className="text-right text-zinc-600">Codec vídeo</p>
                    <p className="text-left">{selectedRecord.video_codec || '-'}</p>
                    <p className="text-right text-zinc-600">Codec áudio</p>
                    <p className="text-left">{selectedRecord.audio_codec || '-'}</p>
                    <p className="text-right text-zinc-600">Local</p>
                    <div className="flex items-center justify-between gap-2 text-left">
                        <span className="break-words">{getPlaceLabel(places, selectedRecord.place_id)}</span>
                        {recordDevice ? (
                            <Button
                                size="sm"
                                variant="ghost"
                                title="Ver dispositivo"
                                onClick={() => onOpenDeviceView(recordDevice)}
                            >
                                <Cpu className="h-4 w-4" />
                            </Button>
                        ) : null}
                    </div>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-white/80 p-3">
                    {canPlayback ? (
                        <video
                            controls
                            className="w-full rounded-md"
                            src={`${API_URL}/records/${selectedRecord.id}/stream?token=${encodeURIComponent(sessionToken)}`}
                        />
                    ) : whepUrl && isDeviceOnline ? (
                        <LiveStreamPlayer src={whepUrl} className="aspect-video w-full" />
                    ) : (
                        <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-2 text-center text-sm text-zinc-600">
                            <p className="font-medium text-zinc-700">Gravação em andamento</p>
                            <p>Aguardando stream do dispositivo...</p>
                        </div>
                    )}
                </div>
            </div>

            {!editing ? (
                <div className="mt-4 flex flex-row flex-wrap justify-end gap-2">
                    {canDownload ? (
                        <Button
                            variant="ghost"
                            className="flex-1 bg-blue-50 text-blue-700 hover:bg-blue-100 sm:flex-none"
                            title="Baixar vídeo"
                            onClick={handleDownload}
                        >
                            <Download className="mr-2 h-4 w-4" />
                            Baixar vídeo
                        </Button>
                    ) : null}
                </div>
            ) : (
                <form onSubmit={handleSubmitEdit} className="mt-4 space-y-3 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                    <input
                        value={recordEditForm.title}
                        onChange={(event) => onRecordEditChange({ ...recordEditForm, title: event.target.value })}
                        placeholder="Título"
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    />
                    <textarea
                        value={recordEditForm.description}
                        onChange={(event) => onRecordEditChange({ ...recordEditForm, description: event.target.value })}
                        placeholder="Descrição"
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                        rows={3}
                    />
                    <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                        <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancelar edição</Button>
                        <Button type="submit" disabled={savingRecord}>{savingRecord ? 'Salvando...' : 'Salvar'}</Button>
                    </div>
                </form>
            )}
        </Card>
    );
};
