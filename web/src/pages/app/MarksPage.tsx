import { useMemo, useState } from 'react';
import type { Dispatch, FormEvent, SetStateAction } from 'react';
import type { MarkApi } from '../../lib/api/client';
import { marksAPI } from '../../lib/api/client';
import { resolveApiErrorMessage } from './errorMessage';
import { MarkCreatePage } from './marks/MarkCreatePage';
import { MarksListPage } from './marks/MarksListPage';
import { MarkViewPage } from './marks/MarkViewPage';
import type { ConfirmState, StatusLevel } from './types';

type MarksPageProps = {
    marks: MarkApi[];
    markSearch: string;
    setMarkSearch: (value: string) => void;
    showInactiveMarks: boolean;
    setShowInactiveMarks: (value: boolean) => void;
    loadMarks: () => Promise<void>;
    showStatus: (level: StatusLevel, msg: string) => void;
    setConfirm: Dispatch<SetStateAction<ConfirmState>>;
};

type MarksView = 'list' | 'view' | 'create';

export const MarksPage = ({
    marks,
    markSearch,
    setMarkSearch,
    showInactiveMarks,
    setShowInactiveMarks,
    loadMarks,
    showStatus,
    setConfirm,
}: MarksPageProps) => {
    const [marksView, setMarksView] = useState<MarksView>('list');
    const [selectedMark, setSelectedMark] = useState<MarkApi | null>(null);
    const [markName, setMarkName] = useState('');
    const [savingMark, setSavingMark] = useState(false);

    const filteredMarks = useMemo(
        () => marks
            .filter((mark) => {
                if (showInactiveMarks) return mark.is_active === false;
                return mark.is_active !== false;
            })
            .filter((mark) => {
                const search = markSearch.trim().toLowerCase();
                if (!search) return true;
                return mark.name.toLowerCase().includes(search) || String(mark.id).includes(search);
            }),
        [marks, showInactiveMarks, markSearch],
    );

    const openList = () => {
        setMarksView('list');
        setSelectedMark(null);
        setMarkName('');
    };

    const handleOpenCreate = () => {
        setSelectedMark(null);
        setMarkName('');
        setMarksView('create');
    };

    const handleOpenView = (mark: MarkApi) => {
        setSelectedMark(mark);
        setMarksView('view');
    };

    const handleOpenEdit = (mark: MarkApi) => {
        setSelectedMark(mark);
        setMarkName(mark.name);
        setMarksView('create');
    };

    const handleSaveMark = async (event: FormEvent) => {
        event.preventDefault();
        if (!markName.trim()) {
            showStatus('error', 'Informe o nome da marca.');
            return;
        }
        setSavingMark(true);
        try {
            if (selectedMark) {
                await marksAPI.update(selectedMark.id, { name: markName.trim() });
                showStatus('info', 'Marca atualizada.');
            } else {
                await marksAPI.create({ name: markName.trim() });
                showStatus('info', 'Marca criada.');
            }
            await loadMarks();
            openList();
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao salvar marca.'));
        } finally {
            setSavingMark(false);
        }
    };

    const handleToggleMarkActive = (mark: MarkApi) => {
        const nextActive = !mark.is_active;
        if (nextActive) {
            void (async () => {
                try {
                    await marksAPI.update(mark.id, { is_active: true });
                    await loadMarks();
                    openList();
                    showStatus('info', 'Marca ativada.');
                } catch (error) {
                    showStatus('error', resolveApiErrorMessage(error, 'Falha ao ativar marca.'));
                }
            })();
            return;
        }

        setConfirm({
            open: true,
            title: 'Desativar marca',
            description: `Desativar ${mark.name}?`,
            confirmLabel: 'Desativar',
            errorFallback: 'Falha ao desativar marca.',
            onConfirm: async () => {
                await marksAPI.update(mark.id, { is_active: false });
                await loadMarks();
                openList();
                showStatus('info', 'Marca desativada.');
            },
        });
    };

    const handleDeleteMark = (mark: MarkApi) => {
        setConfirm({
            open: true,
            title: 'Excluir marca',
            description: `Excluir ${mark.name}?`,
            confirmLabel: 'Excluir',
            errorFallback: 'Falha ao excluir marca.',
            onConfirm: async () => {
                await marksAPI.delete(mark.id);
                await loadMarks();
                openList();
                showStatus('info', 'Marca excluída.');
            },
        });
    };

    if (marksView === 'view' && selectedMark) {
        return (
            <MarkViewPage
                mark={selectedMark}
                onBack={openList}
                onEdit={handleOpenEdit}
            />
        );
    }

    if (marksView === 'create') {
        return (
            <MarkCreatePage
                editingMark={selectedMark}
                markName={markName}
                saving={savingMark}
                onMarkNameChange={setMarkName}
                onSubmit={handleSaveMark}
                onBack={openList}
                onToggleActive={handleToggleMarkActive}
                onDelete={handleDeleteMark}
            />
        );
    }

    return (
        <MarksListPage
            markSearch={markSearch}
            onMarkSearchChange={setMarkSearch}
            showInactiveMarks={showInactiveMarks}
            onShowInactiveMarksChange={setShowInactiveMarks}
            marks={filteredMarks}
            totalMarks={marks.length}
            onOpenCreate={handleOpenCreate}
            onOpenView={handleOpenView}
            onToggleMarkActive={handleToggleMarkActive}
        />
    );
};
