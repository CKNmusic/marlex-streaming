import type { ReactNode } from 'react';
import { Button } from './Button';
import { Modal } from './Modal';

type ConfirmActionModalProps = {
    isOpen: boolean;
    title: string;
    description?: ReactNode;
    errorMessage?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    loading?: boolean;
    confirmVariant?: 'primary' | 'secondary' | 'danger' | 'ghost';
    onClose: () => void;
    onConfirm: () => void;
};

export const ConfirmActionModal = ({
    isOpen,
    title,
    description,
    errorMessage,
    confirmLabel = 'Confirmar',
    cancelLabel = 'Cancelar',
    loading = false,
    confirmVariant = 'danger',
    onClose,
    onConfirm,
}: ConfirmActionModalProps) => (
    <Modal isOpen={isOpen} onClose={onClose} title={title}>
        <div className="space-y-4 text-sm text-zinc-700">
            <p>{description}</p>
            {errorMessage ? (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700">
                    {errorMessage}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button variant="ghost" onClick={onClose} disabled={loading} className="w-full sm:w-auto">
                    {cancelLabel}
                </Button>
                <Button variant={confirmVariant} onClick={onConfirm} disabled={loading} className="w-full sm:w-auto">
                    {loading ? 'Processando...' : confirmLabel}
                </Button>
            </div>
        </div>
    </Modal>
);

