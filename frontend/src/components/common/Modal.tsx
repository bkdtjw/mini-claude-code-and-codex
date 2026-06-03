import { useEffect } from "react";
import type { ReactNode } from "react";

interface ModalProps {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ isOpen, title, onClose, children, footer }: ModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-2xl rounded-xl border border-[var(--as-border-strong)] bg-[var(--as-surface-raised)] text-[var(--as-text)] shadow-[var(--as-shadow)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--as-border)] px-4 py-3">
          <h3 className="text-base font-medium">{title}</h3>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]">
            关闭
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        {footer ? <div className="border-t border-[var(--as-border)] px-4 py-3">{footer}</div> : null}
      </div>
    </div>
  );
}
