import { useQuery } from '@tanstack/react-query';
import { fetchDashboard } from '../../api/endpoints/dashboard';

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
  });
}
