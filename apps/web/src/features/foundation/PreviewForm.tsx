'use client';

import { useRef, useState, type FormEvent } from 'react';
import { usePreferences } from '@/components/PreferencesProvider';

export function PreviewForm({ kind, onSuccess }: { kind: 'opportunity' | 'cv'; onSuccess: () => void }) {
  const { t } = usePreferences();
  const form = useRef<HTMLFormElement>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [fileName, setFileName] = useState('');
  const [fileError, setFileError] = useState(false);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next: Record<string, string> = {};
    if (kind === 'opportunity') {
      if (!String(data.get('fullName') ?? '').trim()) next.fullName = t.required;
      const email = String(data.get('email') ?? '').trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) next.email = t.invalidEmail;
      if (!String(data.get('title') ?? '').trim()) next.title = t.required;
    } else {
      const file = data.get('cv');
      if (!(file instanceof File) || !file.size) next.cv = t.noFile;
      else if (file.size > 10 * 1024 * 1024 || !/\.(pdf|docx)$/i.test(file.name)) next.cv = t.fileInvalid;
      if (!data.get('consent')) next.consent = t.consentRequired;
    }
    setErrors(next);
    if (Object.keys(next).length) {
      const invalid = event.currentTarget.querySelector<HTMLElement>(`[name="${Object.keys(next)[0]}"]`);
      invalid?.focus();
      return;
    }
    onSuccess();
  };

  return <form ref={form} className="preview-form" noValidate onSubmit={submit} onReset={() => { setErrors({}); setFileName(''); setFileError(false); }}>
    <p className="muted form-help">{t.formDescription}</p>
    {kind === 'opportunity' ? <>
      <div className="field"><label htmlFor="preview-name">{t.fullName}</label>
        <input id="preview-name" name="fullName" placeholder={t.namePlaceholder} autoComplete="off" aria-invalid={Boolean(errors.fullName)} aria-describedby={errors.fullName ? 'name-error' : undefined} />
        {errors.fullName ? <p className="field-error" id="name-error">{errors.fullName}</p> : null}
      </div>
      <div className="field"><label htmlFor="preview-email">{t.email}</label>
        <input id="preview-email" name="email" type="email" dir="ltr" placeholder={t.emailPlaceholder} autoComplete="off" aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? 'email-error' : undefined} />
        {errors.email ? <p className="field-error" id="email-error">{errors.email}</p> : null}
      </div>
      <div className="field"><label htmlFor="preview-title">{t.opportunityName}</label>
        <input id="preview-title" name="title" placeholder={t.titlePlaceholder} autoComplete="off" aria-invalid={Boolean(errors.title)} aria-describedby={errors.title ? 'title-error' : undefined} />
        {errors.title ? <p className="field-error" id="title-error">{errors.title}</p> : null}
      </div>
    </> : <>
      <div className="field file-field"><label htmlFor="preview-cv">{t.fileLabel}</label>
        <input id="preview-cv" name="cv" type="file" accept=".pdf,.docx" aria-invalid={Boolean(errors.cv) || fileError} aria-describedby="file-help file-error" onChange={event => {
          const file = event.target.files?.[0];
          setFileName(file?.name ?? '');
          setFileError(Boolean(file && (file.size > 10 * 1024 * 1024 || !/\.(pdf|docx)$/i.test(file.name))));
          setErrors({});
        }} />
        <p className="muted small" id="file-help">{t.fileHelp}</p>
        {fileName ? <p className="small file-name">{t.fileChosen}: <bdi>{fileName}</bdi></p> : null}
        <p id="file-error" className="field-error" aria-live="polite">{fileError ? t.fileInvalid : errors.cv ?? ''}</p>
      </div>
      <label className="checkbox-field"><input name="consent" type="checkbox" aria-invalid={Boolean(errors.consent)} aria-describedby={errors.consent ? 'consent-error' : undefined} /><span>{t.consent}</span></label>
      {errors.consent ? <p id="consent-error" className="field-error">{errors.consent}</p> : null}
    </>}
    <div className="button-row"><button className="button primary" type="submit">{t.validate}</button><button className="button secondary" type="reset">{t.reset}</button></div>
  </form>;
}
