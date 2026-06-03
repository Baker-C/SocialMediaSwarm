import type { NavItem, TabId } from './tabs';
import { tabEquals, tabKey } from './tabs';

type SidebarProps = {
  items: NavItem[];
  activeTab: TabId;
  onSelect: (id: TabId) => void;
};

export function Sidebar({ items, activeTab, onSelect }: SidebarProps) {
  return (
    <aside className="sidebar">
      <p className="sidebar__brand">SMA Agents</p>
      <nav className="sidebar__nav" aria-label="Dashboard navigation">
        <ul className="sidebar__list" role="tablist">
          {items.map((item) => {
            const active = tabEquals(activeTab, item.id);
            const tabId = tabKey(item.id);
            return (
              <li key={tabId} className="sidebar__item" role="presentation">
                <button
                  type="button"
                  role="tab"
                  id={`tab-${tabId}`}
                  aria-selected={active}
                  aria-controls={`panel-${tabId}`}
                  className={`sidebar__tab${active ? ' sidebar__tab--active' : ''}`}
                  onClick={() => onSelect(item.id)}
                >
                  <span className="sidebar__tab-label">{item.label}</span>
                  {item.subtitle ? (
                    <span className="sidebar__tab-sub">{item.subtitle}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
