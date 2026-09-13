import {
  createClient,
  type SupabaseClient,
} from '@supabase/supabase-js';

let browserClient: SupabaseClient | null = null;

export class AdminConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AdminConfigurationError';
  }
}

export function getSupabaseClient(): SupabaseClient {
  if (typeof window === 'undefined') {
    throw new AdminConfigurationError(
      'Admin authentication is only available in the browser.'
    );
  }

  if (browserClient) {
    return browserClient;
  }

  const supabaseUrl = (
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? ''
  ).trim();

  const supabasePublishableKey = (
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? ''
  ).trim();

  if (!supabaseUrl || !supabasePublishableKey) {
    throw new AdminConfigurationError(
      'Admin authentication environment is not configured.'
    );
  }

  browserClient = createClient(
    supabaseUrl,
    supabasePublishableKey,
    {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    }
  );

  return browserClient;
}
