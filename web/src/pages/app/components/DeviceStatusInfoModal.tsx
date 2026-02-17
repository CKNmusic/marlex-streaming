import { Globe, Loader2 } from 'lucide-react';
import { Modal } from '../../../components/ui/Modal';
import { DEVICE_STATUS_HELP, type DeviceRuntimeStatus } from '../status';

type DeviceStatusInfoModalProps = {
    isOpen: boolean;
    status: DeviceRuntimeStatus;
    onClose: () => void;
};

const StatusIcon = ({ status }: { status: DeviceRuntimeStatus }) => {
    if (status === 'Recording') {
        return <Loader2 className="h-4 w-4 animate-spin text-red-600" />;
    }
    if (status === 'Starting') {
        return <Loader2 className="h-4 w-4 animate-spin text-blue-600" />;
    }
    if (status === 'Connecting') {
        return <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />;
    }
    if (status === 'Stopping') {
        return <Loader2 className="h-4 w-4 animate-spin text-amber-600" />;
    }
    if (status === 'Online') {
        return <Globe className="h-4 w-4 text-emerald-700" />;
    }
    return <Globe className="h-4 w-4 text-zinc-500" />;
};

export const DeviceStatusInfoModal = ({
    isOpen,
    status,
    onClose,
}: DeviceStatusInfoModalProps) => {
    const focused = DEVICE_STATUS_HELP.find((item) => item.status === status) || DEVICE_STATUS_HELP[0];
    const otherItems = DEVICE_STATUS_HELP.filter((item) => item.status !== focused.status);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Status do dispositivo">
            <div className="space-y-4 text-sm text-zinc-700">
                <div>
                    <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">Em destaque</p>
                    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                        <div className="flex items-center gap-2 font-semibold text-zinc-900">
                            <StatusIcon status={focused.status} />
                            <span>{focused.title}</span>
                        </div>
                        <p className="mt-1 text-xs text-zinc-700">{focused.description}</p>
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
