import Image from "next/image";

// Shared shell for /login and /register. Living in a layout (not each
// page) means it persists across navigation between the two routes — only
// <AuthCard> underneath swaps, so toggling "Registrarme" ↔ "Iniciar Sesión"
// never re-mounts the background/frame and reads as instant, not a reload.
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-hueso p-4 dark:bg-gray-950">
      <div className="flex w-full max-w-4xl overflow-hidden rounded-2xl border border-hueso-borde bg-white shadow-2xl dark:border-gray-800 dark:bg-gray-900">
        <div className="w-full md:w-1/2">{children}</div>
        <div className="relative hidden w-1/2 bg-azul-oscuro md:block">
          <Image
            src="/images/auth/stacked-waves-haikei.svg"
            alt=""
            fill
            className="object-cover"
            priority
          />
        </div>
      </div>
    </div>
  );
}
