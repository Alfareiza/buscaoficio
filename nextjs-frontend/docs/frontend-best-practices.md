# Frontend best practices (nextjs-frontend)

This file is project-specific conventions only — patterns this codebase has already chosen and you should match. For generic Next.js/React mechanics (RSC rules, async `params`/`cookies()`, Suspense boundaries for `useSearchParams`, image/font optimization, hydration errors, etc.), use the **`vercel:nextjs`** and **`vercel:react-best-practices`** skills instead of re-deriving them here.

## Rendering: Server Components by default
- Default every new file to a Server Component. Add `"use client"` only when the component genuinely needs interactivity, React hooks (`useState`, `useActionState`, `useFormStatus`), or browser APIs.
- Compare `app/dashboard/page.tsx` (Server Component, fetches data directly, no `"use client"`) with `app/dashboard/add-item/page.tsx` (`"use client"` because it needs `useActionState`).
- Fetch data in Server Components or Server Actions, not client-side `useEffect`. There is no react-query/SWR/client fetch layer in this app by design — every backend call is server-to-server (see `.CLAUDE.md` § Auth architecture). Don't introduce one for a single feature; if a real client-only need shows up (live updates, optimistic UI beyond what Server Actions give you), raise it rather than quietly adding a fetch library.
- `params`/`searchParams` are `Promise`s (Next 15+ API) — always `await` them, as in `app/dashboard/page.tsx`'s `DashboardPageProps`.

## Data mutations: Server Actions, never a client-side fetch to FastAPI
- New backend-touching operations belong in `components/actions/*.ts` (`"use server"` at the top of the file), calling the generated SDK functions from `app/clientService.ts` / `app/openapi-client` — never `fetch()` FastAPI directly from a client component, and don't add a `route.ts` Route Handler for this (none exist in this codebase; the Server Action is the established seam).
- Established action shape (see `components/actions/items-action.ts`):
  1. Read `accessToken` from `await cookies()`; if missing, return an error object (don't throw).
  2. Call the typed SDK function, destructure `{ data, error }`.
  3. On error: if `isUnauthorizedError(result)` (`lib/api-errors.ts`) → `clearAuthCookies(cookieStore)` (`lib/auth-cookies.ts`) then `return redirect("/login")`. Otherwise return `{ message: ... }` for the caller to render.
  4. On success: `revalidatePath(...)` and/or `redirect(...)` as needed.
- Always `return redirect(...)` / `return notFound()` — a bare `redirect(...)` call without `return` lets execution fall through in tests (Jest's mock doesn't throw like the real implementation does) and can run downstream code with an undefined token.

## Forms: native `<form>` + `useActionState`, not react-hook-form
`react-hook-form` and `@hookform/resolvers` are installed and shadcn's `components/ui/form.tsx` wraps them, but **no page in this app currently uses that primitive** — it came in with the shadcn template and is unused. The actual pattern every existing form follows:
- `"use client"` component: `const [state, dispatch] = useActionState(actionFn, initialState)`.
- `<form action={dispatch}>` with plain `name` attributes on native inputs — no `register()`/`Controller`.
- `<SubmitButton>` (`components/ui/submitButton.tsx`) wraps `useFormStatus()` for the pending/disabled state — reuse it instead of a bespoke loading button.
- Validation happens **server-side, inside the Server Action**, with a Zod schema from `lib/definitions.ts` (`schema.safeParse(formData-derived object)`), returning `{ errors: validatedFields.error.flatten().fieldErrors }` on failure.
- Field errors render inline (`state.errors?.fieldName`) or via `FormError`/`FieldError` (`components/ui/FormError.tsx`).

Follow this pattern for new forms. Only reach for `components/ui/form.tsx` + react-hook-form if a form's client-side needs (e.g. complex cross-field live validation) genuinely outgrow it — and treat that as a first for the codebase worth calling out, not a silent default.

## Styling
- Tailwind utility classes directly in JSX. Reach for `cn()` (`lib/utils.ts` — `clsx` + `tailwind-merge`) when classes are conditional or need merging with a caller-provided `className`, not as a default wrapper around every class list.
- Brand colors are named Tailwind tokens in `tailwind.config.js` (`naranja`, `naranja-hover`, `naranja-claro`, `durazno`, `durazno-pale`, `azul`, `azul-oscuro`, `azul-pale`, `verde`, `verde-pale`, `hueso`, `hueso-borde`) plus the standard shadcn CSS-variable tokens (`primary`, `secondary`, `muted`, `destructive`, `border`, etc.). Use these instead of hardcoded hex values so a future palette change stays a one-file edit.
- `darkMode: ["class"]` is configured and `dark:` variants are already used ad hoc (e.g. `add-item/page.tsx`) — match the existing `dark:` usage in a file you're touching rather than introducing a new theming mechanism.
- Add new shadcn primitives via the shadcn CLI (`components.json` holds its config) into `components/ui/`, rather than hand-writing new Radix wrappers from scratch.

## Types & the generated OpenAPI client
- Import response/request types from `app/openapi-client` (e.g. `ReadItemResponse`) instead of redeclaring shapes the backend's schema already defines.
- Never hand-edit anything under `app/openapi-client/` — it's generated (see `.CLAUDE.md` § OpenAPI client sync). If a type or field is missing, the fix is a backend schema/route change followed by regeneration, not a local patch.

## Before adding a new pattern
Check whether an existing action or component already solves the same shape of problem (auth-aware Server Action, paginated list + `PagePagination`/`PageSizeSelector`, form submit with field errors) and mirror it, rather than introducing a new data-fetching or state-management approach for one feature.
