import { Pencil } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import type { MarkApi } from '../../../lib/api/client';

type MarkViewPageProps = {
    mark: MarkApi;
    onBack: () => void;
    onEdit: (mark: MarkApi) => void;
};

export const MarkViewPage = ({ mark, onBack, onEdit }: MarkViewPageProps) => (
    <Card
        title="Detalhe da marca"
        onBack={onBack}
        headerActions={(
            <Button size="sm" variant="ghost" onClick={() => onEdit(mark)} title="Editar">
                <Pencil className="mr-1 h-4 w-4" />
                Editar
            </Button>
        )}
    >
        <div className="grid grid-cols-[110px,minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-sm sm:grid-cols-[130px,minmax(0,1fr)]">
            <p className="text-right text-zinc-600">ID</p>
            <p className="text-left">{mark.id}</p>
            <p className="text-right text-zinc-600">Nome</p>
            <p className="text-left">{mark.name}</p>
            <p className="text-right text-zinc-600">Status</p>
            <p className="text-left">{mark.is_active ? 'Ativa' : 'Desativada'}</p>
            <p className="text-right text-zinc-600">Criada em</p>
            <p className="text-left">{mark.created_at ? new Date(mark.created_at).toLocaleString() : '-'}</p>
        </div>
    </Card>
);

