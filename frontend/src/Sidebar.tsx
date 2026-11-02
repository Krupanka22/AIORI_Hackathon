import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Server,
  Globe,
  Activity,
  Brain,
  ShieldAlert,
  Link2,
  FlaskConical,
  Wifi,
  WifiOff,
} from 'lucide-react';

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/devices', icon: Server, label: 'Devices' },
  { to: '/ipv6', icon: Globe, label: 'IPv6 History' },
  { to: '/network', icon: Activity, label: 'Network' },
  { to: '/ai', icon: Brain, label: 'AI Analysis' },
  { to: '/alerts', icon: ShieldAlert, label: 'Alerts' },
  { to: '/blockchain', icon: Link2, label: 'Blockchain' },
  { to: '/experiments', icon: FlaskConical, label: 'Experiments' },
];

export default function Sidebar({ wsConnected }: { wsConnected: boolean }) {
  return (
    <aside
      className="app-sidebar"
    >
      {/* Logo */}
      <div
        className="brand-block"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className="brand-mark"><ShieldAlert size={18} /></span>
          <span className="brand-name">AIORI</span>
        </div>
        <p
          className="brand-subtitle"
        >
          IPv6 IoT Security Monitor
        </p>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `sidebar-link${isActive ? ' active' : ''}`
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Connection status */}
      <div className="connection-status">
        {wsConnected ? (
          <>
            <Wifi size={14} color="var(--color-cyber-green)" />
            <span style={{ color: 'var(--color-cyber-green)' }}>Live</span>
          </>
        ) : (
          <>
            <WifiOff size={14} />
            <span>Disconnected</span>
          </>
        )}
      </div>
    </aside>
  );
}
