"use server";

import { loadCatalogo, type CatalogoResult } from "@/lib/load-catalogo";

export async function loadCatalogoAction(): Promise<CatalogoResult> {
  return loadCatalogo();
}
