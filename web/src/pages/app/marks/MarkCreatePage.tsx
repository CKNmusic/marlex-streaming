import type { FormEvent } from 'react';
import { PlayCircle, StopCircle, Trash2 } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import type { MarkApi } from '../../../lib/api/client';

type MarkCreatePageProps = {
    editingMark: MarkApi | null;
    markName: string;
    saving: boolean;
    onMarkNameChange: (value: string) => void;
    onSubmit: (event: FormEvent) => Promise<void> | void;
    onBack: () => void;
    onToggleActive: (mark: MarkApi) => void;
    onDelete: (mark: MarkApi) => void;
};

export const MarkCreatePage = ({
    editingMark,
    markName,
    saving,
    onMarkNameChange,
    onSubmit,
    onBack,
    onToggleActive,
    onDelete,
}: MarkCreatePageProps) => (
    <Card title={editingMark ? 'Editar marca' : 'Nova marca'} onBack={onBack}>
        <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
                <label htmlFor="mark-name" className="text-sm text-zinc-700">Nome da marca</label>
                <input
                    id="mark-name"
                    value={markName}
                    onChange={(event) => onMarkNameChange(event.target.value)}
                    placeholder="Ex.: ZowieTek"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                />
            </div>

            <div className="flex flex-wrap justify-end gap-2">
                {editingMark ? (
                    <>
                        <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() => onToggleActive(editingMark)}
                        >
                            {editingMark.is_active ? (
                                <StopCircle className="mr-2 h-4 w-4" />
                            ) : (
                                <PlayCircle className="mr-2 h-4 w-4" />
                            )}
                            {editingMark.is_active ? 'Desativar' : 'Ativar'}
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            onClick={() => onDelete(editingMark)}
                        >
                            <Trash2 className="mr-2 h-4 w-4" />
                            Excluir
                        </Button>
                    </>
                ) : null}
                <Button type="button" size="sm" variant="ghost" onClick={onBack}>
                    Cancelar
                </Button>
                <Button type="submit" size="sm" disabled={saving}>
                    {saving ? 'Salvando...' : (editingMark ? 'Salvar' : 'Adicionar')}
                </Button>
            </div>
        </form>
    </Card>
);

