import { NavLink, useLocation, useParams } from 'react-router-dom';
import { ChevronRight, Monitor, Users } from 'lucide-react';
import type { AccountSummary } from '../types';
import { Button } from '../components/ui/button';
import {
  ACCOUNT_SUB_NAV,
  accountSubNavPath,
  buildAccountNavItems,
} from './navItems';

type SidebarProps = {
  accounts: AccountSummary[];
  collapsed: boolean;
  onToggle: () => void;
};

function isAccountRouteActive(pathname: string, accountId: string): boolean {
  return pathname === `/accounts/${accountId}` || pathname.startsWith(`/accounts/${accountId}/`);
}

export function Sidebar({ accounts, collapsed, onToggle }: SidebarProps) {
  const location = useLocation();
  const params = useParams();
  const activeAccountId = params.accountId;
  const accountItems = buildAccountNavItems(accounts);
  const activeCount = accounts.filter((a) => a.status === 'active').length;

  return (
    <aside
      className={`${
        collapsed ? 'w-16' : 'w-70'
      } flex-shrink-0 bg-neutral-900 border-r border-neutral-700 transition-all duration-300 h-full overflow-y-auto`}
    >
      <div className="p-4">
        <div className="flex items-center justify-between mb-8">
          <div className={collapsed ? 'hidden' : 'block'}>
            <h1 className="text-orange-500 font-bold text-lg tracking-wider">SOCIAL MEDIA OPS</h1>
            <p className="text-neutral-500 text-xs">AUTONOMOUS AGENTS</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="text-neutral-400 hover:text-orange-500"
          >
            <ChevronRight
              className={`w-4 h-4 transition-transform ${collapsed ? '' : 'rotate-180'}`}
            />
          </Button>
        </div>

        <nav className="space-y-2" aria-label="Dashboard navigation">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `w-full flex items-center gap-3 p-3 rounded transition-colors no-underline ${
                isActive
                  ? 'bg-orange-500 text-white'
                  : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
              }`
            }
          >
            <Monitor className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span className="text-sm font-medium tracking-wider">OVERVIEW</span>}
          </NavLink>

          {accountItems.map((item) => {
            const accountActive = isAccountRouteActive(location.pathname, item.accountId);
            return (
              <div key={item.accountId}>
                <NavLink
                  to={`/accounts/${item.accountId}`}
                  aria-current={activeAccountId === item.accountId ? 'page' : undefined}
                  className={`w-full flex items-center gap-3 p-3 rounded transition-colors no-underline ${
                    accountActive
                      ? 'bg-orange-500 text-white'
                      : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
                  }`}
                >
                  <Users className="w-5 h-5 flex-shrink-0" />
                  {!collapsed && (
                    <span className="min-w-0">
                      <span className="block text-sm font-medium tracking-wider uppercase truncate">
                        {item.label}
                      </span>
                      {item.subtitle ? (
                        <span
                          className={`block text-xs truncate ${
                            accountActive ? 'text-orange-100' : 'text-neutral-600'
                          }`}
                        >
                          {item.subtitle}
                        </span>
                      ) : null}
                    </span>
                  )}
                </NavLink>

                {accountActive && !collapsed ? (
                  <div className="mt-1 mb-2 ml-4 border-l border-neutral-700 space-y-0.5">
                    {ACCOUNT_SUB_NAV.map((sub) => (
                      <NavLink
                        key={sub.segment || 'hq'}
                        to={accountSubNavPath(item.accountId, sub.segment)}
                        end={sub.end}
                        className={({ isActive }) =>
                          `block py-1.5 pl-4 pr-2 text-xs tracking-wider uppercase no-underline transition-colors border-l-2 -ml-px ${
                            isActive
                              ? 'border-orange-500 text-orange-500'
                              : 'border-transparent text-neutral-500 hover:text-white'
                          }`
                        }
                      >
                        {sub.label}
                      </NavLink>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </nav>

        {!collapsed && (
          <div className="mt-8 p-4 bg-neutral-800 border border-neutral-700 rounded">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
              <span className="text-xs text-white">SYSTEM ONLINE</span>
            </div>
            <div className="text-xs text-neutral-500 space-y-0.5">
              <div>ACCOUNTS: {accounts.length} TRACKED</div>
              <div>ACTIVE: {activeCount}</div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
