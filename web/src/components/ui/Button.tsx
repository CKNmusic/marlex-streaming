import * as React from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';
import { uiTheme } from '../../theme/ui';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
    size?: 'sm' | 'md' | 'lg';
}

export const Button: React.FC<ButtonProps> = ({
    children,
    variant = 'primary',
    size = 'md',
    className,
    ...props
}) => {
    const baseStyles = `${uiTheme.button.base} ${uiTheme.focus.ring}`;

    const variants = {
        primary: uiTheme.button.variants.primary,
        secondary: uiTheme.button.variants.secondary,
        danger: uiTheme.button.variants.danger,
        ghost: uiTheme.button.variants.ghost,
    };

    const sizes = {
        sm: 'px-3 py-2 text-sm min-h-[40px] sm:min-h-0 sm:py-1.5',
        md: 'px-4 py-2.5 text-sm min-h-[44px] sm:min-h-0 sm:py-2',
        lg: 'px-6 py-3 text-base min-h-[48px] sm:min-h-0',
    };

    return (
        <button
            className={cn(baseStyles, variants[variant], sizes[size], className)}
            {...props}
        >
            {children}
        </button>
    );
};
