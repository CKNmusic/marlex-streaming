import { Globe, Loader2 } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import type { DeviceRuntimeStatus } from '../status';

type DeviceStatusIconButtonProps = {
    status: DeviceRuntimeStatus;
    onClick: () => void;
};

export const DeviceStatusIconButton = ({
    status,
    onClick,
}: DeviceStatusIconButtonProps) => {
    const isRecording = status === 'Recording';
    const isConnecting = status === 'Connecting';
    const isStarting = status === 'Starting';
    const isStopping = status === 'Stopping';
    const isOnline = status === 'Online';
    const title = isRecording
        ? 'Recording'
        : isConnecting
            ? 'Connecting'
        : isStarting
            ? 'Starting'
            : isStopping
                ? 'Stopping'
                : isOnline
                    ? 'Online'
                    : 'Offline';

    if (status === 'Recording') {
        return (
            <Button
                size="sm"
                variant="ghost"
                title={title}
                aria-label={title}
                onClick={onClick}
            >
                <Loader2 className="h-4 w-4 animate-spin text-red-600" />
            </Button>
        );
    }

    if (status === 'Starting') {
        return (
            <Button
                size="sm"
                variant="ghost"
                title={title}
                aria-label={title}
                onClick={onClick}
            >
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
            </Button>
        );
    }

    if (status === 'Connecting') {
        return (
            <Button
                size="sm"
                variant="ghost"
                title={title}
                aria-label={title}
                onClick={onClick}
            >
                <Loader2 className="h-4 w-4 animate-spin text-cyan-600" />
            </Button>
        );
    }

    if (status === 'Stopping') {
        return (
            <Button
                size="sm"
                variant="ghost"
                title={title}
                aria-label={title}
                onClick={onClick}
            >
                <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
            </Button>
        );
    }

    return (
        <Button
            size="sm"
            variant="ghost"
            title={title}
            aria-label={title}
            onClick={onClick}
        >
            <Globe className={`h-4 w-4 ${isOnline ? 'text-emerald-600' : 'text-zinc-500'}`} />
        </Button>
    );
};
