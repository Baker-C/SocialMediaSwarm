import { NavLink, useLocation, useParams } from 'react-router-dom';
import type { AccountSummary } from '../types';
import {
  ACCOUNT_SUB_NAV,
  accountSubNavPath,
  buildAccountNavItems,
} from './navItems';

type SidebarProps = {
  accounts: AccountSummary[];
};

function isAccountRouteActive(pathname: string, accountId: string): boolean {
  return pathname === `/accounts/${accountId}` || pathname.startsWith(`/accounts/${accountId}/`);
}

export function Sidebar({ accounts }: SidebarProps) {
  const location = useLocation();
  const params = useParams();
  const activeAccountId = params.accountId;
  const accountItems = buildAccountNavItems(accounts);

  return (
    <aside className="sidebar">
      <p className="sidebar__brand">SMA Agents</p>
      <nav className="sidebar__nav" aria-label="Dashboard navigation">
        <ul className="sidebar__list" role="tablist">
          <li className="sidebar__item" role="presentation">
            <NavLink
              to="/"
              end
              role="tab"
              aria-selected={location.pathname === '/'}
              className={({ isActive }) =>
                `sidebar__tab${isActive ? ' sidebar__tab--active' : ''}`
              }
            >
              <span className="sidebar__tab-label">Overview</span>
            </NavLink>
          </li>

          {accountItems.map((item) => {
            const accountActive = isAccountRouteActive(location.pathname, item.accountId);
            const tabSelected = activeAccountId === item.accountId;
            return (
              <li key={item.accountId} className="sidebar__item" role="presentation">
                <NavLink
                  to={`/accounts/${item.accountId}`}
                  role="tab"
                  aria-selected={tabSelected}
                  className={() =>
                    `sidebar__tab${accountActive ? ' sidebar__tab--active' : ''}`
                  }
                >
                  <span className="sidebar__tab-label">{item.label}</span>
                  {item.subtitle ? (
                    <span className="sidebar__tab-sub">{item.subtitle}</span>
                  ) : null}
                </NavLink>

                {accountActive ? (
                  <ul className="sidebar__sublist" aria-label={`${item.accountId} sections`}>
                    {ACCOUNT_SUB_NAV.map((sub) => (
                      <li key={sub.segment || 'hq'} className="sidebar__subitem">
                        <NavLink
                          to={accountSubNavPath(item.accountId, sub.segment)}
                          end={sub.end}
                          className={({ isActive }) =>
                            `sidebar__subtab${isActive ? ' sidebar__subtab--active' : ''}`
                          }
                        >
                          {sub.label}
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
