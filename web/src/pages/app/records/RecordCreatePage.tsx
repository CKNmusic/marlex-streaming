import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { SelectField } from '../../../components/ui/SelectField';
import type { Device, DeviceStatus, Procedure } from '../../../lib/api/client';
import { getDeviceRuntimeStatusFromSnapshot, isOnlineDeviceRuntimeStatus, isReadyDeviceRuntimeStatus } from '../status';
import type { RecordFormState } from './types';

type DeviceFilter = 'online' | 'recording' | 'all';

type RecordCreatePageProps = {
    isAdmin: boolean;
    devices: Device[];
    deviceStatus: Record<number, DeviceStatus>;
    boundDevice: Device | null;
    recordForm: RecordFormState;
    procedures: Procedure[];
    recordingBusy: boolean;
    onRecordFormChange: (next: RecordFormState) => void;
    onStartRecord: (event: FormEvent) => Promise<void> | void;
    onCloseRecordsView: () => void;
};

export const RecordCreatePage = ({
    isAdmin,
    devices,
    deviceStatus,
    boundDevice,
    recordForm,
    procedures,
    recordingBusy,
    onRecordFormChange,
    onStartRecord,
    onCloseRecordsView,
}: RecordCreatePageProps) => {
    const [deviceFilter, setDeviceFilter] = useState<DeviceFilter>('online');

    const resolveDeviceLabel = (device: Device) => {
        const mark = String(device.mark_name || '').trim();
        const model = String(device.model || device.name || '').trim();
        return [mark, model].filter(Boolean).join(' ');
    };
    const selectableProcedures = procedures.filter((procedure) => procedure.is_active !== false);

    const selectableAdminDevices = devices.filter((device) => {
        if (!device.is_active) return false;
        const status = getDeviceRuntimeStatusFromSnapshot(deviceStatus[device.id]);
        if (!isOnlineDeviceRuntimeStatus(status)) return false;
        if (deviceFilter === 'online') return status === 'Online';
        if (deviceFilter === 'recording') return status === 'Recording';
        return true;
    });

    const selectedDeviceId = Number(recordForm.device_id || 0);
    const selectedAdminDevice = isAdmin ? selectableAdminDevices.find((device) => device.id === selectedDeviceId) : null;
    const boundStatus = boundDevice
        ? getDeviceRuntimeStatusFromSnapshot(deviceStatus[boundDevice.id])
        : 'Offline';
    const boundReady = isReadyDeviceRuntimeStatus(boundStatus);
    const canStart = isAdmin ? !!selectedAdminDevice : !!boundDevice && boundReady;
    const adminDeviceOptions = selectableAdminDevices.map((device) => {
        const status = getDeviceRuntimeStatusFromSnapshot(deviceStatus[device.id]);
        return {
            value: String(device.id),
            label: `${resolveDeviceLabel(device)} — ${status}`,
        };
    });
    const procedureOptions = selectableProcedures.map((procedure) => ({
        value: String(procedure.id),
        label: procedure.name,
    }));

    const deviceFilterOptions = [
        { value: 'online', label: 'Online (não gravando)' },
        { value: 'recording', label: 'Gravando' },
        { value: 'all', label: 'Todos (ativos online)' },
    ];

    return (
        <Card title="Nova gravação" onBack={onCloseRecordsView}>
            <form onSubmit={onStartRecord} className="space-y-4">
                {isAdmin ? (
                    <>
                        <SelectField
                            value={deviceFilter}
                            options={deviceFilterOptions}
                            onValueChange={(value) => {
                                setDeviceFilter(value as DeviceFilter);
                                onRecordFormChange({ ...recordForm, device_id: '' });
                            }}
                            className="w-full sm:w-[280px]"
                            triggerClassName="text-xs text-zinc-700"
                        />
                        <SelectField
                            value={recordForm.device_id}
                            options={adminDeviceOptions}
                            onValueChange={(value) => onRecordFormChange({ ...recordForm, device_id: value })}
                            placeholder="Selecione o dispositivo"
                        />
                    </>
                ) : null}
                {isAdmin && selectableAdminDevices.length === 0 ? (
                    <p className="text-xs text-zinc-500">
                        Nenhum dispositivo {deviceFilter === 'online' ? 'online' : deviceFilter === 'recording' ? 'gravando' : 'disponível'} para gravação.
                    </p>
                ) : null}
                {!isAdmin && boundDevice ? (
                    <p className="text-xs text-zinc-500">
                        Status do dispositivo vinculado: {boundStatus}
                    </p>
                ) : null}
                {!isAdmin && boundDevice && !boundReady ? (
                    <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                        Dispositivo conectando. Aguarde status Online para liberar REC.
                    </p>
                ) : null}
                <input
                    value={recordForm.title}
                    onChange={(event) => onRecordFormChange({ ...recordForm, title: event.target.value })}
                    placeholder="Título"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    required
                />
                <textarea
                    value={recordForm.description}
                    onChange={(event) => onRecordFormChange({ ...recordForm, description: event.target.value })}
                    placeholder="Descrição"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                    rows={3}
                />
                <SelectField
                    value={recordForm.procedure_id}
                    options={procedureOptions}
                    onValueChange={(value) => onRecordFormChange({ ...recordForm, procedure_id: value })}
                    placeholder="Selecione o procedimento"
                />

                <div className="flex justify-end gap-2">
                    <Button type="button" variant="ghost" onClick={onCloseRecordsView}>Cancelar</Button>
                    <Button type="submit" variant="danger" className="rounded-full px-5" disabled={!canStart || recordingBusy}>
                        <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-red-600 shadow-[0_0_0_4px_rgba(239,68,68,0.35)]" />
                        {recordingBusy ? 'Iniciando...' : 'REC iniciar gravação'}
                    </Button>
                </div>
                {!canStart ? (
                    <p className="text-xs text-zinc-500">
                        {isAdmin
                            ? 'Selecione um dispositivo para habilitar a gravação.'
                            : boundDevice
                                ? 'Aguarde o dispositivo ficar online para habilitar a gravação.'
                                : 'Vincule um dispositivo para habilitar a gravação.'}
                    </p>
                ) : null}
            </form>
        </Card>
    );
};
