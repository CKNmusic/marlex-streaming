import type { FormEvent } from 'react';
import { Cloud, CloudOff } from 'lucide-react';
import { AutocompleteInput } from '../../../../components/ui/AutocompleteInput';
import { Button } from '../../../../components/ui/Button';

type CityCreatePageProps = {
    cityForm: { name: string; uf: string };
    onCityFormChange: (next: { name: string; uf: string }) => void;
    cityApiSearch: string;
    onCityApiSearchChange: (next: string) => void;
    cityApiOptions: Array<{ value: string; label: string }>;
    onSearchCityApi: () => Promise<void> | void;
    onSelectCityApiOption: (value: string) => void;
    searchingCityApi: boolean;
    cptecApiOnline: boolean | null;
    onSubmit: (event: FormEvent) => Promise<void> | void;
    onBack: () => void;
};

export const CityCreatePage = ({
    cityForm,
    onCityFormChange,
    cityApiSearch,
    onCityApiSearchChange,
    cityApiOptions,
    onSearchCityApi,
    onSelectCityApiOption,
    searchingCityApi,
    cptecApiOnline,
    onSubmit,
    onBack,
}: CityCreatePageProps) => (
    <form onSubmit={onSubmit} className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
        <div className="mb-3 text-sm font-medium text-zinc-800">Nova cidade</div>
        <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-[1fr,auto]">
                <AutocompleteInput
                    value={cityApiSearch}
                    options={cityApiOptions}
                    onValueChange={onCityApiSearchChange}
                    onSelectOption={(option) => onSelectCityApiOption(option.value)}
                    placeholder="Buscar cidade na API (ex.: Campinas)"
                    className="w-full"
                    emptyLabel="Nenhuma cidade retornada pela API."
                />
                <Button type="button" variant="ghost" className="h-10 px-3" onClick={onSearchCityApi} disabled={searchingCityApi}>
                    {cptecApiOnline === false ? (
                        <CloudOff className="h-4 w-4 text-red-300" />
                    ) : (
                        <Cloud className="h-4 w-4" />
                    )}
                </Button>
            </div>
            <p className="text-xs text-zinc-500">
                Selecione uma cidade retornada pela API para confirmar o cadastro. Cadastro manual somente quando a API estiver indisponível.
            </p>
            <div className="grid gap-2 md:grid-cols-[1fr,100px,auto]">
                <input
                    value={cityForm.name}
                    onChange={(event) => onCityFormChange({ ...cityForm, name: event.target.value })}
                    placeholder="Cidade"
                    className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                />
                <input
                    value={cityForm.uf}
                    onChange={(event) => onCityFormChange({ ...cityForm, uf: event.target.value })}
                    placeholder="UF"
                    className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm uppercase outline-none"
                    maxLength={2}
                />
                <div className="flex gap-2">
                    <Button type="submit" size="sm">Adicionar</Button>
                    <Button type="button" size="sm" variant="ghost" onClick={onBack}>Voltar</Button>
                </div>
            </div>
        </div>
    </form>
);
