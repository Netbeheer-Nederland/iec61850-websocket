// src/components/ContextMenu.jsx
import React, { useEffect, useRef } from 'react';

const ContextMenu = ({ x, y, visible, onClose, items }) => {
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    };
    if (visible) {
      document.addEventListener('click', handleClickOutside);
    }
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [visible, onClose]);

  if (!visible) return null;

  return (
    <div
      ref={menuRef}
      className="context-menu"
      style={{
        position: 'fixed',
        left: `${x}px`,
        top: `${y}px`,
        border: '1px solid var(--border-color)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
        zIndex: 1000,
        minWidth: '150px',
        padding: '4px 0',
        fontSize: '14px',
      }}
    >
      {items.map((item, index) => (
        <div
          key={item.id || index}
          className={`context-menu-item${item.danger ? ' danger' : ''}`}
          onClick={() => {
            if (item.action) item.action();
            onClose();
          }}
          style={{ padding: '8px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
        >
          {item.icon && <i className={`fas ${item.icon}`} style={{ marginRight: '8px' }} />}
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
};

export default ContextMenu;