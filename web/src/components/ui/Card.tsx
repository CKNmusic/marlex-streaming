import * as React from 'react';
import { ChevronLeft } from 'lucide-react';
import { cn } from '../../lib/utils';
import { uiTheme } from '../../theme/ui';

export interface CardProps {
    children: React.ReactNode;
    className?: string;
    title?: string;
    titleClassName?: string;
    onBack?: () => void;
    backLabel?: string;
    headerActions?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
    children,
    className,
    title,
    titleClassName,
    onBack,
    backLabel = 'Voltar',
    headerActions,
}) => {
    const panelClass = `rounded-lg border p-4 sm:p-6 ${uiTheme.surface.panel}`;
    const backButtonClass = `inline-flex h-11 w-11 sm:h-8 sm:w-8 items-center justify-center rounded-md border transition-colors hover:bg-zinc-100 active:bg-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-300 ${uiTheme.surface.panel} ${uiTheme.text.secondary}`;
    const titleClass = `text-lg font-semibold ${uiTheme.text.primary}`;
    return (
        <div className={cn(panelClass, className)}>
            {title ? (
                <div className="mb-4 flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                        {onBack ? (
                            <button
                                type="button"
                                onClick={onBack}
                                aria-label={backLabel}
                                title={backLabel}
                                className={backButtonClass}
                            >
                                <ChevronLeft className="h-4 w-4" />
                            </button>
                        ) : null}
                        <h3 className={cn(titleClass, titleClassName)}>{title}</h3>
                    </div>
                    {headerActions ? (
                        <div className="shrink-0">
                            {headerActions}
                        </div>
                    ) : null}
                </div>
            ) : null}
            {children}
        </div>
    );
};
