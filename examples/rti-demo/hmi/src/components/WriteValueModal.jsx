// src/components/WriteValueModal.jsx
import React, { useState, useEffect } from 'react';
import { executeApiCall, getApiById } from '../services/apiService';

const WriteValueModal = ({ objRef, fc, endpoint, cp, onClose, onSuccess }) => {
  const [value, setValue] = useState('');
  const [type, setType] = useState('Reading...');
  const [currentValue, setCurrentValue] = useState('Reading...');
  const [validation, setValidation] = useState('');
  const [result, setResult] = useState({ visible: false, success: false, message: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const fetchCurrentValue = async () => {
      try {
        const endpointTarget = `${endpoint.host}:${endpoint.port}`;
        const res = await executeApiCall('read', endpointTarget, { objRef, fc, cp });
        if (res?.ok && res.payload?.result?.value) {
          const values = Array.isArray(res.payload.result.value) ? res.payload.result.value : [res.payload.result.value];
          if (values.length > 0 && values[0]?.data) {
            const firstValue = values[0];
            if (Array.isArray(firstValue.data) && firstValue.data.length >= 2) {
              setType(firstValue.data[0]);
              setCurrentValue(JSON.stringify(firstValue.data[1]));
            } else if (typeof firstValue.data === 'object') {
              const typeKeys = Object.keys(firstValue.data).filter((k) => !['name', 'elementName'].includes(k));
              if (typeKeys.length > 0) {
                setType(typeKeys[0]);
                setCurrentValue(JSON.stringify(firstValue.data[typeKeys[0]]));
              }
            }
          }
        } else {
          setType('Unknown');
          setCurrentValue(res?.payload?.error || 'N/A');
        }
      } catch (error) {
        setType('Error');
        setCurrentValue(error.message);
      }
    };
    fetchCurrentValue();
  }, [objRef, fc, endpoint, cp]);

  const handleSubmit = async () => {
    if (!value.trim()) {
      setValidation('Please enter a value');
      return;
    }
    setValidation('');
    setIsSubmitting(true);
    try {
      const endpointTarget = `${endpoint.host}:${endpoint.port}`;
      await executeApiCall('write', endpointTarget, {
        objRef,
        fc,
        value,
        value_type: type,
        cp,
      });
      setResult({ visible: true, success: true, message: '✓ Write successful!' });
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1500);
    } catch (error) {
      setResult({ visible: true, success: false, message: `✗ Error: ${error.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000 }}>
      <div className="write-value-modal" style={{ background: '#1e1e1e', padding: '20px', borderRadius: '8px', maxWidth: '500px', margin: '50px auto' }}>
        <h2>Write Data Value</h2>
        <div>
          <label>Object Reference:</label>
          <div>{objRef}</div>
        </div>
        <div>
          <label>Type:</label>
          <div>{type}</div>
        </div>
        <div>
          <label>Current Value:</label>
          <div>{currentValue}</div>
        </div>
        <div style={{ margin: '16px 0' }}>
          <label>New Value:</label>
          <input
            style={{ margin: '0 16px' }}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Enter new value"
          />
          {validation && <div style={{ color: 'red', fontSize: '12px' }}>{validation}</div>}
        </div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          <button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? 'Writing...' : 'Write'}
          </button>
          <button onClick={onClose}>Cancel</button>
        </div>
        {result.visible && (
          <div
            style={{
              marginTop: '16px',
              padding: '8px',
              background: result.success ? '#2e7d32' : '#c62828',
              color: 'white',
              borderRadius: '4px',
            }}
          >
            {result.message}
          </div>
        )}
      </div>
    </div>
  );
};

export default WriteValueModal;