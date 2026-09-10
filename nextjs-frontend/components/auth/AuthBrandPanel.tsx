import Image from "next/image";

// Decorative half of the auth shell: brand copy and a rotating sample of the
// catalog over a slowly drifting gradient. Motion stays in CSS — see
// `brand-rotate` / `brand-cycle` in globals.css, and the per-duration
// `brand-card-*` keyframes emitted below — so this remains a Server
// Component: no interval, no hydration, no client state.

/** Palette pairs the backdrop cycles through. Every pair keeps a warm anchor
 * so the panel still reads as buscaoficio at any point in the cycle. */
const GRADIENTS = [
  { from: "#F55F20", to: "#FBCBA4" }, // naranja → durazno
  { from: "#1A3C6E", to: "#FF8C42" }, // azul → naranja claro
  { from: "#059669", to: "#FBCBA4" }, // verde → durazno
];

type Servicio = {
  icon: string;
  titulo: string;
  descripcion: string;
  /** Seconds this card holds a slot, fade included. Falls back to
   * `DEFAULT_STEP_SECONDS` when omitted. */
  durationSeconds?: number;
};

/** Seconds a service holds a frame when it does not set `durationSeconds`. */
const DEFAULT_STEP_SECONDS = 9;

/** Fade in/out on each handoff. Kept shorter than the shortest hold. */
const FADE_SECONDS = 0.8;

const SERVICIOS: Servicio[] = [
  {
    icon: "/images/auth/icons/rodillo.png",
    titulo: "Pintura",
    descripcion:
      "Pintores verificados, cotización gratis y precio cerrado antes de empezar.",
  },
  {
    icon: "/images/auth/icons/escoba.png",
    titulo: "Limpieza",
    descripcion:
      "Aseo por horas o profundo, con personal de confianza y garantía.",
  },
  {
    icon: "/images/auth/icons/segueta.png",
    titulo: "Carpintería",
    descripcion: "Muebles a la medida, reparación y montaje sin sorpresas.",
  },
  {
    icon: "/images/auth/icons/rayo.png",
    titulo: "Electricidad",
    descripcion:
      "Tomas, luminarias y fallas eléctricas con técnicos certificados.",
  },
  {
    icon: "/images/auth/icons/llave.png",
    titulo: "Cerrajería",
    descripcion:
      "Apertura de puertas, cambio de guardas y copias de llave a domicilio.",
  },
  {
    icon: "/images/auth/icons/taladro.png",
    titulo: "Instalaciones",
    descripcion:
      "Montaje de TV, repisas y muebles, con anclajes seguros a la pared.",
  },
  {
    icon: "/images/auth/icons/martillo.png",
    titulo: "Reparaciones",
    descripcion:
      "Arreglos del hogar por horas, con diagnóstico previo sin costo.",
  },
  {
    icon: "/images/auth/icons/programacion.png",
    titulo: "Programación",
    descripcion:
      "Páginas web, apps y automatizaciones, con alcance claro antes de escribir código.",
    durationSeconds: 12,
  },
  {
    icon: "/images/auth/icons/obra-blanca.png",
    titulo: "Obra blanca",
    descripcion:
      "Estuco, drywall y acabados, con visita técnica y precio cerrado.",
  },
  {
    icon: "/images/auth/icons/aire.png",
    titulo: "Aires acondicionados",
    descripcion:
      "Instalación, mantenimiento y arreglo, con técnicos que dejan el equipo listo.",
  },
  {
    icon: "/images/auth/icons/jardineria.png",
    titulo: "Jardinería",
    descripcion:
      "Poda de árboles, césped y jardines, con retiro de residuos incluido.",
  },
];

function durationOf(servicio: Servicio) {
  return servicio.durationSeconds ?? DEFAULT_STEP_SECONDS;
}

/** Cards on screen at once. Each one is a fixed frame the services rotate
 * through, so the panel's height never changes as they swap. */
const VISIBLE_SLOTS = 3;

/** One full pass through every service, from a single slot's point of view. */
const CYCLE_SECONDS = SERVICIOS.reduce(
  (total, servicio) => total + durationOf(servicio),
  0,
);

/** Slots turn over a third of a default step apart, so the three never swap
 * at once even when several services share the same hold. */
const SLOT_STAGGER_SECONDS = DEFAULT_STEP_SECONDS / VISIBLE_SLOTS;

/** Order in which a slot walks the list: it starts at its own index and moves
 * in strides of VISIBLE_SLOTS. The stride and the service count are coprime,
 * so every slot eventually shows all services, and since the three cursors
 * stay a fixed distance apart no service is ever on screen twice. */
function serviceOrderFor(slot: number) {
  return SERVICIOS.map(
    (_, step) => (slot + step * VISIBLE_SLOTS) % SERVICIOS.length,
  );
}

function cardKeyframeName(holdSeconds: number) {
  return `brand-card-${String(holdSeconds).replace(".", "-")}`;
}

/** One keyframe set per distinct hold. The card is visible for
 * `holdSeconds / CYCLE_SECONDS` of the loop; `animation-delay` shifts that
 * window to the service's place in the slot's timeline. */
function cardKeyframesCss() {
  const holds = new Set(SERVICIOS.map(durationOf));
  return [...holds]
    .map((holdSeconds) => {
      const fade = Math.min(FADE_SECONDS, holdSeconds / 4);
      const fadeIn = ((fade / CYCLE_SECONDS) * 100).toFixed(3);
      const holdVisible = (
        ((holdSeconds - fade) / CYCLE_SECONDS) *
        100
      ).toFixed(3);
      const holdEnd = ((holdSeconds / CYCLE_SECONDS) * 100).toFixed(3);
      const name = cardKeyframeName(holdSeconds);
      return `@keyframes ${name} {
  0% {
    opacity: 0;
    transform: translateY(8px);
  }
  ${fadeIn}%,
  ${holdVisible}% {
    opacity: 1;
    transform: translateY(0);
  }
  ${holdEnd}%,
  100% {
    opacity: 0;
    transform: translateY(-8px);
  }
}`;
    })
    .join("\n");
}

function slotTimeline(slot: number) {
  let elapsed = 0;
  return serviceOrderFor(slot).map((servicioIndex) => {
    const hold = durationOf(SERVICIOS[servicioIndex]);
    const start = elapsed;
    elapsed += hold;
    return { servicioIndex, start, hold };
  });
}

export function AuthBrandPanel() {
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden bg-hueso p-8">
      <style>{cardKeyframesCss()}</style>
      {/* Oversized so the rotation never sweeps a corner into view. Each layer
          runs the same spin but enters the fade cycle 8s after the last. */}
      {GRADIENTS.map((gradient, index) => (
        <div
          key={gradient.from + gradient.to}
          className="brand-layer absolute inset-[-50%]"
          style={{
            background: `linear-gradient(0deg, ${gradient.from}, ${gradient.to})`,
            animation:
              "brand-rotate 40s linear infinite, brand-cycle 24s ease-in-out infinite",
            animationDelay: `0s, ${index * 8}s`,
          }}
        />
      ))}

      {/* 1px scanlines every 2px — breaks up the flat gradient so it reads as
          a surface rather than a wash. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "repeating-linear-gradient(0deg, rgba(18,43,80,0.14) 0px, rgba(18,43,80,0.14) 1px, transparent 2px, transparent 2px)",
        }}
      />

      <div className="relative w-full max-w-sm space-y-7">
        <h2 className="text-2xl font-bold leading-tight tracking-tight text-azul-oscuro lg:text-3xl">
          El profesional que necesitas, cuando lo necesitas
        </h2>

        <ul className="space-y-2.5">
          {Array.from({ length: VISIBLE_SLOTS }, (_, slot) => (
            // The frame stays put — border, fill and blur belong to the slot,
            // not to the card — so a handoff only swaps the contents instead
            // of stacking two translucent panes mid-crossfade.
            <li
              key={slot}
              className="relative h-24 rounded-xl border border-white/60 bg-white/40 backdrop-blur-sm"
            >
              {slotTimeline(slot).map(({ servicioIndex, start, hold }) => {
                const servicio = SERVICIOS[servicioIndex];
                return (
                  <div
                    key={servicio.titulo}
                    className="brand-card absolute inset-0 flex items-center gap-3.5 p-3.5"
                    style={{
                      animation: `${cardKeyframeName(hold)} ${CYCLE_SECONDS}s ease-in-out infinite both`,
                      animationDelay: `${start - slot * SLOT_STAGGER_SECONDS}s`,
                    }}
                    // Every service is stacked in all three slots, so expose
                    // each one from the slot that owns it — otherwise a screen
                    // reader walks the same catalog three times.
                    aria-hidden={servicioIndex % VISIBLE_SLOTS !== slot}
                  >
                    <div className="relative h-14 w-14 shrink-0">
                      <Image
                        src={servicio.icon}
                        alt=""
                        fill
                        sizes="56px"
                        className="object-contain p-1"
                      />
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-azul-oscuro">
                        {servicio.titulo}
                      </p>
                      {/* Clamped so a long description can never outgrow the
                          fixed frame height on a narrow viewport. */}
                      <p className="line-clamp-2 text-xs leading-relaxed text-azul-oscuro/70">
                        {servicio.descripcion}
                      </p>
                    </div>
                  </div>
                );
              })}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
