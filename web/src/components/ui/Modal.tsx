import * as React from 'react';
import { useEffect, useEffectEvent } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { uiTheme } from '../../theme/ui';

interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    children: React.ReactNode;
    size?: 'sm' | 'md' | 'lg' | 'xl';
}

export const Modal: React.FC<ModalProps> = ({
    isOpen,
    onClose,
    title,
    children,
    size = 'md',
}) => {
    const emitClose = useEffectEvent(() => {
        onClose();
    });

    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'unset';
        }

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                emitClose();
            }
        };

        if (isOpen) {
            window.addEventListener('keydown', onKeyDown);
        }

        return () => {
            window.removeEventListener('keydown', onKeyDown);
            document.body.style.overflow = 'unset';
        };
    }, [isOpen]);

    if (!isOpen) return null;

    const sizes = {
        sm: 'max-w-[calc(100vw-2rem)] sm:max-w-md',
        md: 'max-w-[calc(100vw-2rem)] sm:max-w-lg',
        lg: 'max-w-[calc(100vw-2rem)] sm:max-w-2xl',
        xl: 'max-w-[calc(100vw-2rem)] sm:max-w-4xl',
    };
    const panelClass = `relative w-full rounded-lg border p-4 sm:p-6 shadow-xl ${uiTheme.surface.panel}`;
    const titleClass = `text-lg sm:text-xl font-semibold ${uiTheme.text.primary}`;
    const closeButtonClass = `${uiTheme.text.muted} transition hover:text-zinc-800 active:text-zinc-900 min-h-[44px] min-w-[44px] flex items-center justify-center -mr-2 -mt-1`;

    return (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/40 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal */}
            <div className={cn(panelClass, sizes[size], 'relative z-10 max-h-[90dvh] sm:max-h-[85dvh] flex flex-col rounded-t-2xl sm:rounded-lg mx-0 sm:mx-4')}>
                {/* Header */}
                <div className="mb-3 sm:mb-4 flex items-center justify-between gap-2 shrink-0">
                    <h2 className={cn(titleClass, 'break-words')}>{title}</h2>
                    <button
                        onClick={onClose}
                        className={closeButtonClass}
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="overflow-y-auto overscroll-contain -mx-4 px-4 sm:-mx-6 sm:px-6 pb-1">{children}</div>
            </div>
        </div>
    );
};
