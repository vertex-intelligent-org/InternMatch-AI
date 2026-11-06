export const statuses = ['saved', 'applied', 'interviewing', 'rejected', 'accepted'] as const;
export type ApplicationStatus = typeof statuses[number];
export type Internship = { id: string; title: string; company: string; location: string; work_type: string; required_skills: string[]; preferred_skills: string[]; publication_status: 'draft' | 'under_review' | 'published' | 'closed'; is_active: boolean; posted_at: string };
export type InternshipDetail = Internship & { description: string; languages: string[]; min_education: string | null; experience_requirements: string | null };
export type Application = { id: string; internship_id: string | null; company_name: string | null; job_title: string | null; status: ApplicationStatus; generated_cover_letter: string | null; applied_date: string | null; notes: string | null };
export type ApplicationDetail = Application & { created_at: string; updated_at: string; interview_scheduled_at: string | null; interview_mode: 'online' | 'onsite' | null; interview_location: string | null; interview_message: string | null; timeline: { status: ApplicationStatus; occurred_at: string }[] };
export type Saved = { id: string; internship_id: string; saved_at: string; internship: Internship };
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type StudentCode = 'unavailable' | 'notFound' | 'unauthorized' | 'forbidden' | 'invalid' | 'conflict' | 'rateLimited' | 'uncertain' | 'notConfigured';
export class StudentFailure extends Error { constructor(public code: StudentCode, public status: number) { super(code); } }
export const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const object = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string';
const optionalText = (v: unknown) => v === null || text(v);
const arrayText = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
const date = (v: unknown) => text(v) && Number.isFinite(Date.parse(v));
export function internship(v: unknown): v is Internship {
  return object(v) && uuid(v.id) && [v.title,v.company,v.location,v.work_type].every(text) && arrayText(v.required_skills) && arrayText(v.preferred_skills) && ['draft','under_review','published','closed'].includes(String(v.publication_status)) && typeof v.is_active === 'boolean' && date(v.posted_at);
}
export function internshipDetail(v: unknown): v is InternshipDetail { return object(v) && text(v.description) && arrayText(v.languages) && optionalText(v.min_education) && optionalText(v.experience_requirements) && internship(v); }
export function application(v: unknown): v is Application { return object(v) && uuid(v.id) && (v.internship_id === null || uuid(v.internship_id)) && optionalText(v.company_name) && optionalText(v.job_title) && statuses.includes(v.status as ApplicationStatus) && optionalText(v.generated_cover_letter) && optionalText(v.applied_date) && optionalText(v.notes); }
export function applicationDetail(v: unknown): v is ApplicationDetail { return object(v) && date(v.created_at) && date(v.updated_at) && optionalText(v.interview_scheduled_at) && [null,'online','onsite'].includes(v.interview_mode as null | string) && optionalText(v.interview_location) && optionalText(v.interview_message) && Array.isArray(v.timeline) && v.timeline.every(e=>object(e) && statuses.includes(e.status as ApplicationStatus) && date(e.occurred_at)) && application(v); }
export function saved(v: unknown): v is Saved { return object(v) && uuid(v.id) && uuid(v.internship_id) && date(v.saved_at) && internship(v.internship) && v.internship_id === v.internship.id; }
export function pageOf<T>(v: unknown, guard: (v: unknown)=>v is T): v is Page<T> { return object(v) && Array.isArray(v.items) && v.items.every(guard) && Number.isSafeInteger(v.total) && Number(v.total)>=0 && Number.isSafeInteger(v.limit) && Number(v.limit)>=1 && Number.isSafeInteger(v.offset) && Number(v.offset)>=0; }
export function applications(v: unknown): v is { applications: Application[] } { return object(v) && Array.isArray(v.applications) && v.applications.every(application); }
export function pagination(search: URLSearchParams) {
  const allowed = new Set(['limit','offset','work_type','location','skill']);
  for (const key of search.keys()) if (!allowed.has(key) || search.getAll(key).length !== 1) throw new StudentFailure('invalid',400);
  const limit = search.get('limit') ?? '12'; const offset = search.get('offset') ?? '0';
  if (!/^\d+$/.test(limit) || !/^\d+$/.test(offset) || Number(limit)<1 || Number(limit)>50 || !Number.isSafeInteger(Number(offset)) || Number(offset)>1000000) throw new StudentFailure('invalid',400);
  const result=new URLSearchParams({ limit, offset });
  for (const key of ['location','skill','work_type']) { const value=search.get(key)?.trim(); if (!value) continue; if(value.length>200 || (key==='work_type' && !['remote','onsite','hybrid'].includes(value))) throw new StudentFailure('invalid',400); result.set(key,value); }
  return result;
}
export function submission(v: unknown): { cover_letter?: string; notes?: string } {
  if (!object(v) || Object.keys(v).some(k=>!['cover_letter','notes'].includes(k))) throw new StudentFailure('invalid',400);
  for(const key of ['cover_letter','notes']) if (v[key]!==undefined && (typeof v[key]!=='string' || String(v[key]).length>(key==='notes'?4000:20000))) throw new StudentFailure('invalid',400);
  return v as {cover_letter?:string;notes?:string};
}
