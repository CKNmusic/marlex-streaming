import type { Record as RecordApi } from '../../../lib/api/client';

export type RecordLifecycleStatus = 'Recording' | 'Completed' | 'Failed' | 'CompletedByAdmin';

export type RecordStatusHelpItem = {
    status: RecordLifecycleStatus;
    title: string;
    description: string;
};

const STOP_REASON_LABELS: Record<string, string> = {
    user: 'Usuário',
    master: 'Administrador',
    timeout: 'Timeout',
    connection: 'Conexão',
    disconnect: 'Conexão',
    storage: 'Armazenamento',
};

const FINAL_STATUS_LABELS: Record<string, string> = {
    recording: 'Recording',
    stopped_user: 'Finalizado normalmente',
    stopped_master: 'Finalizado pelo administrador',
    error_connection: 'Conexão perdida',
    error_timeout: 'Timeout',
    error_storage: 'Espaço insuficiente',
};

const normalizeToken = (value?: string | null) => String(value || '').trim().toLowerCase();

const prettifyFallback = (value: string) => {
    const normalized = value.replace(/^error_/, '').replace(/^stopped_/, '').replace(/_/g, ' ').trim();
    return normalized || 'motivo não informado';
};

export const getRecordFailureReason = (record: Pick<RecordApi, 'final_status' | 'stop_reason'>) => {
    const finalStatus = normalizeToken(record.final_status);
    const stopReason = normalizeToken(record.stop_reason);

    if (FINAL_STATUS_LABELS[finalStatus]) {
        return FINAL_STATUS_LABELS[finalStatus];
    }
    if (STOP_REASON_LABELS[stopReason]) {
        return STOP_REASON_LABELS[stopReason];
    }
    if (finalStatus) {
        return prettifyFallback(finalStatus);
    }
    if (stopReason) {
        return prettifyFallback(stopReason);
    }
    return 'motivo não informado';
};

export const resolveRecordLifecycleStatus = (
    record: Pick<RecordApi, 'end_time' | 'final_status' | 'stop_reason'>,
): RecordLifecycleStatus => {
    if (!record.end_time) return 'Recording';

    const stopReason = normalizeToken(record.stop_reason);
    const finalStatus = normalizeToken(record.final_status);

    if (stopReason === 'master' || finalStatus === 'stopped_master') {
        return 'CompletedByAdmin';
    }

    const failedByFinalStatus = finalStatus.startsWith('error_');
    const failedByReason = ['timeout', 'connection', 'disconnect', 'error'].includes(stopReason);
    if (failedByFinalStatus || failedByReason) {
        return 'Failed';
    }

    return 'Completed';
};

export const getRecordStatusTitle = (
    status: RecordLifecycleStatus,
    record: Pick<RecordApi, 'final_status' | 'stop_reason'>,
) => {
    if (status === 'Recording') return 'Recording';
    if (status === 'Completed') return 'Finalizado normalmente';
    if (status === 'CompletedByAdmin') return 'Finalizado pelo administrador';
    return `Falha: ${getRecordFailureReason(record)}`;
};

export const getRecordStatusDescription = (
    status: RecordLifecycleStatus,
    record: Pick<RecordApi, 'final_status' | 'stop_reason'>,
) => {
    if (status === 'Recording') return 'Gravação em andamento.';
    if (status === 'Completed') return 'Encerrada sem falha.';
    if (status === 'CompletedByAdmin') return 'Encerrada manualmente pelo administrador.';
    return `Gravação encerrada com falha. Motivo: ${getRecordFailureReason(record)}.`;
};

export const getRecordStopReasonLabel = (record: Pick<RecordApi, 'end_time' | 'final_status' | 'stop_reason'>) => {
    if (!record.end_time) return '';
    const stopReason = normalizeToken(record.stop_reason);
    if (STOP_REASON_LABELS[stopReason]) return STOP_REASON_LABELS[stopReason];
    return getRecordFailureReason(record);
};

export const RECORD_STATUS_HELP: RecordStatusHelpItem[] = [
    {
        status: 'Recording',
        title: 'Recording',
        description: 'Gravação em andamento.',
    },
    {
        status: 'Completed',
        title: 'Finalizado normalmente',
        description: 'Encerrada sem falha.',
    },
    {
        status: 'Failed',
        title: 'Falha',
        description: 'Encerrada por erro com motivo registrado.',
    },
    {
        status: 'CompletedByAdmin',
        title: 'Finalizado pelo administrador',
        description: 'Encerrada manualmente pelo administrador.',
    },
];
