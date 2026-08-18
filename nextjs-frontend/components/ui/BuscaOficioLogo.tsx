import Link from "next/link";

interface BuscaOficioMarkProps {
  size?: number;
  className?: string;
}

/** The svg-only brand mark — same artwork as `busca-oficio-logo-principal.svg`. */
export function BuscaOficioMark({
  size = 40,
  className = "",
}: BuscaOficioMarkProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      aria-hidden="true"
      className={`drop-shadow-sm ${className}`}
    >
      <circle cx="24" cy="18" r="12.5" fill="#F55F20" />
      <circle cx="24" cy="30" r="12.5" fill="#1A3C6E" fillOpacity="0.5" />
      <path
        d="M19.5 24l3.4 3.4 6-6.6"
        stroke="#fff"
        strokeWidth="2.8"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface BuscaOficioWordmarkProps {
  size?: number;
  className?: string;
}

/** The text-only wordmark — "Busca" in azul, "Oficio" in naranja. */
export function BuscaOficioWordmark({
  size = 20,
  className = "",
}: BuscaOficioWordmarkProps) {
  return (
    <span
      style={{ fontSize: size }}
      className={`inline-flex items-center leading-none gap-0.5 ${className}`}
    >
      <span className="font-bold text-azul dark:text-white">Busca</span>
      <span className="font-bold text-naranja">Oficio</span>
    </span>
  );
}

interface BuscaOficioLogoProps {
  width?: number;
  height?: number;
  href?: string;
  className?: string;
  ariaLabel?: string;
}

/**
 * BuscaOficio branding lockup — combines `BuscaOficioMark` and
 * `BuscaOficioWordmark` side by side. Flexible, responsive, dark-mode aware.
 *
 * Usage:
 * - As static branding: <BuscaOficioLogo width={80} height={80} />
 * - As a clickable link: <BuscaOficioLogo width={80} height={80} href="/" />
 */
export function BuscaOficioLogo({
  width = 80,
  height = 80,
  href,
  className = "",
  ariaLabel = "BuscaOficio — inicio",
}: BuscaOficioLogoProps) {
  const markSize = width * 0.5;
  const fontSize = width * 0.22;

  const logoContent = (
    <div
      className={`inline-flex items-center justify-center gap-0 transition-transform duration-300 ${
        href ? "hover:scale-105 active:scale-95" : ""
      } ${className}`}
      style={{
        width,
        height,
      }}
    >
      <BuscaOficioMark size={markSize} />
      <BuscaOficioWordmark size={fontSize} />
    </div>
  );

  if (href) {
    return (
      <Link href={href} aria-label={ariaLabel}>
        {logoContent}
      </Link>
    );
  }

  return logoContent;
}
