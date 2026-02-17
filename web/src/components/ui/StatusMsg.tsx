import { useEffect, useEffectEvent } from 'react';
import { uiTheme } from '../../theme/ui';

type StatusLevel = 'error' | 'warn' | 'info';

type StatusMsgProps = {
    level: StatusLevel;
    msg: string;
    time_sec?: number;
    onClear?: () => void;
};

const levelStyles: Record<StatusLevel, string> = {
    error: uiTheme.status.error,
    warn: uiTheme.status.warn,
    info: uiTheme.status.info,
};

export const StatusMsg = ({ level, msg, time_sec = 3, onClear }: StatusMsgProps) => {
    const emitClear = useEffectEvent(() => {
        onClear?.();
    });

    useEffect(() => {
        if (!msg) return;
        const timeout = window.setTimeout(() => {
            emitClear();
        }, time_sec * 1000);
        return () => window.clearTimeout(timeout);
    }, [level, msg, time_sec]);

    if (!msg) return null;

    return (
        <div className={`rounded-md border px-4 py-3 text-sm ${levelStyles[level]}`}>
            {msg}
        </div>
    );
};
