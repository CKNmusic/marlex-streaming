import { AlertTriangle, CheckCircle2, Dot, ShieldCheck } from 'lucide-react';
import { Modal } from '../../../components/ui/Modal';
import type { Record as RecordApi } from '../../../lib/api/client';
import {
    RECORD_STATUS_HELP,
    getRecordStatusDescription,
    getRecordStatusTitle,
    resolveRecordLifecycleStatus,
    type RecordLifecycleStatus,
} from './status';

type RecordStatusInfoModalProps = {
    isOpen: boolean;
    record: RecordApi | null;
    onClose: () => void;
};

const StatusIcon = ({ status }: { status: RecordLifecycleStatus }) => {
    if (status === 'Recording') {
        return <Dot className="h-5 w-5 animate-pulse text-red-600" />;
    }
    if (status === 'Completed') {
        return <CheckCircle2 className="h-4 w-4 text-emerald-700" />;
    }
    if (status === 'CompletedByAdmin') {
        return <ShieldCheck className="h-4 w-4 text-sky-700" />;
    }
    return <AlertTriangle className="h-4 w-4 text-amber-700" />;
};

export const RecordStatusInfoModal = ({
    isOpen,
    record,
    onClose,
}: RecordStatusInfoModalProps) => {
    const fallbackRecord = { end_time: null, final_status: null, stop_reason: null };
    const currentRecord = record || fallbackRecord;
    const focusedStatus = resolveRecordLifecycleStatus(currentRecord);
    const focusedTitle = getRecordStatusTitle(focusedStatus, currentRecord);
    const focusedDescription = getRecordStatusDescription(focusedStatus, currentRecord);
    const otherItems = RECORD_STATUS_HELP.filter((item) => item.status !== focusedStatus);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Status da gravação">
            <div className="space-y-4 text-sm text-zinc-700">
                <div>
                    <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Em destaque</p>
                    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="flex items-center gap-2 font-semibold text-zinc-900">
                            <StatusIcon status={focusedStatus} />
                            <span>{focusedTitle}</span>
                        </div>
                        <p className="mt-1 text-xs text-zinc-700">{focusedDescription}</p>
                    </div>
                </div>

                <div>
                    <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Outros status</p>
                    <div className="space-y-2">
                        {otherItems.map((item) => (
                            <div key={item.status} className="rounded-md border border-zinc-200 bg-white p-3">
                                <div className="flex items-center gap-2 font-medium text-zinc-900">
                                    <StatusIcon status={item.status} />
                                    <span>{item.title}</span>
                                </div>
                                <p className="mt-1 text-xs text-zinc-600">{item.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </Modal>
    );
};
