import { listCategorias, listZonas } from "@/app/clientService";

export type CatalogoCategoria = {
  id: string;
  nombre: string;
};

export type CatalogoZona = {
  id: string;
  ciudad: string;
  localidad: string | null;
};

export type CatalogoData = {
  categorias: CatalogoCategoria[];
  zonas: CatalogoZona[];
};

export type CatalogoResult =
  | { ok: true; data: CatalogoData }
  | { ok: false };

export async function loadCatalogo(): Promise<CatalogoResult> {
  try {
    const [categoriasResult, zonasResult] = await Promise.all([
      listCategorias(),
      listZonas(),
    ]);
    if (
      categoriasResult.error ||
      zonasResult.error ||
      !categoriasResult.data ||
      !zonasResult.data
    ) {
      return { ok: false };
    }
    const categorias = categoriasResult.data.map((categoria) => ({
      id: categoria.id,
      nombre: categoria.nombre,
    }));
    const zonas = zonasResult.data.map((zona) => ({
      id: zona.id,
      ciudad: zona.ciudad,
      localidad: zona.localidad ?? null,
    }));
    if (categorias.length === 0 || zonas.length === 0) {
      return { ok: false };
    }
    return { ok: true, data: { categorias, zonas } };
  } catch {
    return { ok: false };
  }
}
