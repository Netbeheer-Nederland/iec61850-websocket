import React from 'react';
import { NavLink } from 'react-router-dom';

function Sidebar() {
  const navItems = [
    { path: '/setup', icon: 'fa-gear', label: 'Setup' },
    { path: '/tools', icon: 'fa-tools', label: 'Tools' },
    { path: '/monitoring', icon: 'fa-satellite-dish', label: 'Monitoring' },
    { path: '/settings', icon: 'fa-cog', label: 'Settings' },
    // Hidden items from original HTML
    // { path: '/reports', icon: 'fa-file-pdf', label: 'Reports', hidden: true },
    // { path: '/diagnostics', icon: 'fa-stethoscope', label: 'Diagnostics', hidden: true },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <i className="fas fa-network-wired"></i>
          <span>IEC 61850</span>
        </div>
        <p className="subtitle">RTI Demo UI</p>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => 
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <i className={`fas ${item.icon}`}></i>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer items (hidden by default) */}
      <div className="sidebar-footer" style={{ display: 'none' }}>
        <a href="#" className="sidebar-footer-item">
          <i className="fas fa-question-circle"></i>
          <span>Help</span>
        </a>
        <a href="#" className="sidebar-footer-item">
          <i className="fas fa-user"></i>
          <span>Profile</span>
        </a>
      </div>
    </aside>
  );
}

export default Sidebar;
