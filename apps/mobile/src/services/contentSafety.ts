import AsyncStorage from '@react-native-async-storage/async-storage';

import { supabase } from '../lib/supabase';

const BLOCKED_EMPLOYERS_PREFIX =
  'internmatch.blockedEmployerCompanies.v1';

function normalizeCompany(value: unknown): string {
  return typeof value === 'string'
    ? value.trim().toLocaleLowerCase()
    : '';
}

async function getStorageKey(): Promise<string | null> {
  try {
    const { data } = await supabase.auth.getSession();
    const userId = data.session?.user?.id;

    if (!userId) return null;

    return `${BLOCKED_EMPLOYERS_PREFIX}:${userId}`;
  } catch {
    return null;
  }
}

export async function getBlockedEmployerCompanies(): Promise<string[]> {
  const key = await getStorageKey();

  if (!key) return [];

  try {
    const raw = await AsyncStorage.getItem(key);

    if (!raw) return [];

    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed)) return [];

    return Array.from(
      new Set(
        parsed
          .map(normalizeCompany)
          .filter(Boolean)
      )
    );
  } catch {
    return [];
  }
}

export async function blockEmployerCompany(
  company: string
): Promise<void> {
  const normalized = normalizeCompany(company);

  if (!normalized) return;

  const key = await getStorageKey();

  if (!key) return;

  const existing = await getBlockedEmployerCompanies();

  if (existing.includes(normalized)) return;

  await AsyncStorage.setItem(
    key,
    JSON.stringify([...existing, normalized])
  );
}

export async function filterBlockedInternships<
  T extends { company?: string | null }
>(items: T[]): Promise<T[]> {
  const blocked = new Set(
    await getBlockedEmployerCompanies()
  );

  if (blocked.size === 0) return items;

  return items.filter(
    (item) => !blocked.has(normalizeCompany(item?.company))
  );
}

export async function filterBlockedSavedInternships<
  T extends {
    internship?: {
      company?: string | null;
    } | null;
  }
>(items: T[]): Promise<T[]> {
  const blocked = new Set(
    await getBlockedEmployerCompanies()
  );

  if (blocked.size === 0) return items;

  return items.filter(
    (item) =>
      !blocked.has(
        normalizeCompany(item?.internship?.company)
      )
  );
}

export async function filterBlockedMatches<
  T extends {
    internship?: {
      company?: string | null;
    } | null;
  }
>(items: T[]): Promise<T[]> {
  const blocked = new Set(
    await getBlockedEmployerCompanies()
  );

  if (blocked.size === 0) return items;

  return items.filter(
    (item) =>
      !blocked.has(
        normalizeCompany(item?.internship?.company)
      )
  );
}
