'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon';
import { usePreferences } from './PreferencesProvider';

export function Dialog({ open, onClose, title, children, id }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  id: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = usePreferences();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const before = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = before; };
  }, [open]);

  return <dialog ref={ref} className="dialog" aria-labelledby={`${id}-title`} onCancel={onClose} onClose={onClose} onClick={event => {
    if (event.target === event.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }
  }}>
    <div className="dialog-heading">
      <h2 id={`${id}-title`}>{title}</h2>
      <button type="button" className="icon-button" aria-label={t.close} onClick={onClose} autoFocus><Icon name="close" /></button>
    </div>
    {open ? children : null}
  </dialog>;
}
