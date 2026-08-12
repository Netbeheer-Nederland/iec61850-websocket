import React, { useEffect } from 'react';

function ConnectionModal({ 
  settings, 
  showModal, 
  onClose, 
  currentConnection, 
  formData, 
  onFormChange,
  onSave 
}) {
  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    onFormChange(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
  };

  // Sync ACSI and ws_mode when type changes or modal opens
  const syncAcsiAndWsMode = (type, acsi, ws_mode) => {
    if (type === 'RTI-SO' && (acsi !== 'client' || ws_mode !== 'passive')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'client',
        ws_mode: 'passive'
      }));
    } else if (type === 'RTI-FSP' && (acsi !== 'server' || ws_mode !== 'active')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'server',
        ws_mode: 'active'
      }));
    }
  };

  useEffect(() => {
    syncAcsiAndWsMode(formData.type, formData.acsi, formData.ws_mode);
  }, [formData.type, formData.acsi, formData.ws_mode]);

  const handleTypeChange = (e) => {
    const { value } = e.target;
    let newAcsi = formData.acsi;
    let newWsMode = formData.ws_mode;
    
    if (value === 'RTI-SO') {
      newAcsi = 'client';
      newWsMode = 'passive';
    } else if (value === 'RTI-FSP') {
      newAcsi = 'server';
      newWsMode = 'active';
    }
    
    onFormChange(prev => ({
      ...prev,
      type: value,
      acsi: newAcsi,
      ws_mode: newWsMode
    }));
  };

  const isGeneric = formData.type === 'Generic';

  return (
    <>
      {showModal && (
        <div className="modal active">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{currentConnection ? 'Edit Instance' : 'Register Instance'}</h2>
              <button className="btn-close" onClick={onClose}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="name">Name</label>
                <input 
                  type="text" 
                  id="name" 
                  value={formData.name} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="host">Host</label>
                <input 
                  type="text" 
                  id="host" 
                  value={formData.host} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="port">Port</label>
                <input 
                  type="number" 
                  id="port" 
                  value={formData.port} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="type">Type</label>
                <select 
                  id="type" 
                  value={formData.type} 
                  onChange={handleTypeChange}
                >
                  <option value="Generic">Generic</option>
                  <option value="RTI-SO">RTI-SO (WS Passive/ACSI Client)</option>
                  <option value="RTI-FSP">RTI-FSP (WS Active/ACSI Server)</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="acsi">ACSI</label>
                <select 
                  id="acsi" 
                  value={formData.acsi || 'server'}
                  onChange={handleInputChange}
                  disabled={!isGeneric}
                >
                  <option value="server">Server</option>
                  <option value="client">Client</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="ws_mode">WebSocket Mode</label>
                <select 
                  id="ws_mode" 
                  value={formData.ws_mode || ''}
                  onChange={handleInputChange}
                  disabled={!isGeneric}
                >
                  <option value="">Select mode...</option>
                  <option value="active">Active</option>
                  <option value="passive">Passive</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={onClose}>
                Close
              </button>
              <button className="btn-primary" onClick={onSave}>
                <i className="fas fa-save"></i>
                Save Instance
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ConnectionModal;
