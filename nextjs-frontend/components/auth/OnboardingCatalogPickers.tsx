"use client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { MultiSelect } from "@/components/ui/multi-select";
import { CATEGORIA_ICON_BY_NOMBRE, DEFAULT_ZONA_CIUDAD } from "@/lib/catalogo-icons";
import type { CatalogoData, CatalogoZona } from "@/lib/load-catalogo";

function zonaLabel(zona: CatalogoZona) {
  return zona.localidad ? `${zona.ciudad} ${zona.localidad}` : zona.ciudad;
}

export function defaultZonaIds(zonas: CatalogoZona[]): string[] {
  const barranquilla = zonas.find(
    (zona) => zona.ciudad.toLowerCase() === DEFAULT_ZONA_CIUDAD.toLowerCase(),
  );
  return barranquilla ? [barranquilla.id] : [];
}

type OnboardingCatalogPickersProps = {
  catalog: CatalogoData | null;
  catalogFailed: boolean;
  zonaIds: string[];
  categoriaIds: string[];
  onZonaIdsChange: (ids: string[]) => void;
  onCategoriaIdsChange: (ids: string[]) => void;
  onRetry: () => void;
  retrying: boolean;
};

export function OnboardingCatalogPickers({
  catalog,
  catalogFailed,
  zonaIds,
  categoriaIds,
  onZonaIdsChange,
  onCategoriaIdsChange,
  onRetry,
  retrying,
}: OnboardingCatalogPickersProps) {
  if (catalogFailed || !catalog) {
    return (
      <div className="flex flex-col gap-3 text-left">
        <p className="text-sm text-red-500" role="alert">
          No pudimos cargar zonas y categorías.
        </p>
        <Button
          type="button"
          variant="outline"
          className="h-10 rounded-full"
          disabled={retrying}
          onClick={onRetry}
        >
          {retrying ? "Cargando…" : "Reintentar"}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 text-left">
      <div className="flex flex-col gap-2">
        <Label>Categorías</Label>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Elige todos los oficios que haces.
        </p>
        <MultiSelect
          value={categoriaIds}
          onValueChange={onCategoriaIdsChange}
          options={catalog.categorias.map((categoria) => ({
            value: categoria.id,
            label: categoria.nombre,
            icon: CATEGORIA_ICON_BY_NOMBRE[categoria.nombre],
          }))}
          searchLabel="Buscar oficio"
          emptyText="No encontramos oficios."
          listLabel="Oficios"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label>Zona</Label>
        <MultiSelect
          value={zonaIds}
          onValueChange={onZonaIdsChange}
          options={catalog.zonas.map((zona) => ({
            value: zona.id,
            label: zonaLabel(zona),
          }))}
          placeholder="Elige zonas"
          searchLabel="Buscar zona"
          emptyText="No encontramos zonas."
          listLabel="Zonas"
        />
      </div>
    </div>
  );
}
