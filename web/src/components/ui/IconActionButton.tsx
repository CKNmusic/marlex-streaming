import type { ButtonHTMLAttributes } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Button } from './Button';

type IconActionButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & {
    icon: LucideIcon;
    variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
    size?: 'sm' | 'md' | 'lg';
    iconClassName?: string;
};

export const IconActionButton = ({
    icon: Icon,
    variant = 'ghost',
    size = 'sm',
    className,
    iconClassName,
    ...props
}: IconActionButtonProps) => (
    <Button
        size={size}
        variant={variant}
        className={cn('shrink-0 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0', className)}
        {...props}
    >
        <Icon className={cn('h-5 w-5 sm:h-4 sm:w-4', iconClassName)} />
    </Button>
);

