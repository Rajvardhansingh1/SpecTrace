import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

// Plex Mono keeps 0/O and 1/l visibly different, which matters for entity keys and line numbers.
const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "SpecTrace", template: "%s | SpecTrace" },
  description:
    "Compare two versions of OpenAPI files and Markdown docs, and see which docs, requirements and examples depend on each change, with the source line that proves it.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
};

// Runs before the first paint so a stored choice never flashes the other theme.
const THEME_SCRIPT = `try{var t=localStorage.getItem("spectrace-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        <header className="site-header">
          <div className="wrap site-header__inner">
            <Link href="/" className="wordmark">
              SpecTrace
            </Link>
            <nav aria-label="Main">
              <ul className="site-nav">
                <li>
                  <Link href="/">Compare</Link>
                </li>
                <li>
                  <Link href="/benchmark">Benchmark</Link>
                </li>
              </ul>
            </nav>
            <ThemeToggle />
          </div>
        </header>
        <main id="main" className="wrap">
          {children}
        </main>
      </body>
    </html>
  );
}
