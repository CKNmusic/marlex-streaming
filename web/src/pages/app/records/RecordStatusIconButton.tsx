import { AlertTriangle, CheckCircle2, Loader2, ShieldCheck } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import type { RecordLifecycleStatus } from './status';

type RecordStatusIconButtonProps = {
    status: RecordLifecycleStatus;
    title: string;
    onClick: () => void;
};

export const RecordStatusIconButton = ({
    status,
    title,
    onClick,
}: RecordStatusIconButtonProps) => {
    if (status === 'Recording') {
        return (
            <Button type="button" size="sm" variant="ghost" title={title} aria-label={title} onClick={onClick} className="h-8 w-8 p-0">
                <Loader2 className="h-4 w-4 animate-spin text-red-600" />
            </Button>
        );
    }

    if (status === 'Completed') {
        return (
            <Button type="button" size="sm" variant="ghost" title={title} aria-label={title} onClick={onClick} className="h-8 w-8 p-0">
                <CheckCircle2 className="h-4 w-4 text-emerald-700" />
            </Button>
        );
    }

    if (status === 'CompletedByAdmin') {
        return (
            <Button type="button" size="sm" variant="ghost" title={title} aria-label={title} onClick={onClick} className="h-8 w-8 p-0">
                <ShieldCheck className="h-4 w-4 text-sky-700" />
            </Button>
        );
    }

    return (
        <Button type="button" size="sm" variant="ghost" title={title} aria-label={title} onClick={onClick} className="h-8 w-8 p-0">
            <AlertTriangle className="h-4 w-4 text-amber-700" />
        </Button>
    );
};
