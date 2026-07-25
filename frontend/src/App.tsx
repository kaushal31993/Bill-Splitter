import { Link, Outlet } from "react-router-dom";

export default function App() {
  return (
    <div className="min-h-screen">
      {/* Frosted chrome: content scrolls beneath it rather than being clipped. */}
      <header className="material sticky top-0 z-40 border-b border-separator">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-5">
          <Link
            to="/"
            className="group flex items-center gap-2.5 text-headline font-semibold text-label"
          >
            <span
              aria-hidden
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-white transition-transform duration-300 ease-spring group-hover:scale-105"
            >
              {/* A receipt torn down the middle: the whole app in one mark. */}
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" aria-hidden>
                <path
                  d="M5.5 3.2h9a.8.8 0 0 1 .8.8v12.3l-2-1.1-2 1.1-2-1.1-2 1.1-2-1.1-1.6.9V4a.8.8 0 0 1 .8-.8Z"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
                <path
                  d="M10 5.4v9.2"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                  strokeDasharray="1.6 1.9"
                />
              </svg>
            </span>
            Bill Splitter
          </Link>
          <span className="text-footnote text-label-3">Local · USD</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 pb-24 pt-8">
        <Outlet />
      </main>
    </div>
  );
}
