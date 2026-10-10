/*
 * SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025-2026 Netbeheer Nederland
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';

// Whether the sidebar is collapsed to icons, remembered per browser.
export const COLLAPSED_KEY = 'rti-hmi-sidebar-collapsed';

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

function saveCollapsed(collapsed) {
  try {
    localStorage.setItem(COLLAPSED_KEY, String(collapsed));
  } catch {
    // Storage blocked (private window, site data off): it just isn't remembered.
  }
}

function Sidebar() {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggle = () => {
    setCollapsed((was) => {
      saveCollapsed(!was);
      return !was;
    });
  };

  const navItems = [
    { path: '/overview', icon: 'fa-diagram-project', label: 'Overview' },
    { path: '/connections', icon: 'fa-gear', label: 'Connections' },
    { path: '/model', icon: 'fa-sitemap', label: 'Model' },
    { path: '/traffic', icon: 'fa-exchange-alt', label: 'Traffic' },
    { path: '/diagnostics', icon: 'fa-stethoscope', label: 'Diagnostics' },
    { path: '/tools', icon: 'fa-tools', label: 'Tools' },
    { path: '/settings', icon: 'fa-cog', label: 'Settings' },
  ];

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="logo">
          <i className="fas fa-network-wired"></i>
          <span>IEC 61850</span>
        </div>
        <p className="subtitle">RTI Demo UI</p>
        <button
          type="button"
          className="sidebar-toggle"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <i className={`fas ${collapsed ? 'fa-angles-right' : 'fa-angles-left'}`}></i>
        </button>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => 
              `nav-item ${isActive ? 'active' : ''}`
            }
            aria-label={item.label}
            title={collapsed ? item.label : undefined}
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
