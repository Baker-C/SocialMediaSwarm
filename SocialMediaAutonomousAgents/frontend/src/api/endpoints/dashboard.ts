import type { DashboardPayload } from '../../types';
import { apiFetch } from '../client';

export async function fetchDashboard(): Promise<DashboardPayload> {
  return apiFetch<DashboardPayload>('/dashboard');
}
