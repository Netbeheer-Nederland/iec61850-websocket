// src/components/WriteValueModal.jsx
import React, { useState, useEffect, useRef } from 'react';
import { executeApiCall } from '../services/apiService';

const WriteValueModal = ({ objRef, fc, endpoint, cp, onClose, onSuccess }) => {
  const [value, setValue] = useState('');
  const [type, setType] = useState('Reading...');
  const [currentValue, setCurrentValue] = useState('Reading...');
  const [validation, setValidation] = useState('');
  const [result, setResult] = useState({ visible: false, success: false, message: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    const fetchCurrentValue = async () => {
      try {
        const endpointTarget = `${endpoint.host}:${endpoint.port}`;
        const res = await executeApiCall('read', endpointTarget, {
          objRef,
          fc,
          ...(cp ? { cp } : {}),
        });

        if (res?.ok) {
          // FSP / ACSI Server shape: result.values = { type, value } (flat)
          if (res.payload?.result?.values) {
            const { type: valType, value: val } = res.payload.result.values;
            setType(valType || 'Unknown');
            setCurrentValue(val !== undefined ? JSON.stringify(val) : 'N/A');
            return;
          }

          // SO / ACSI Client shape: result.value = [ { data: [...] } ]
          if (res.payload?.result?.value) {
            const values = Array.isArray(res.payload.result.value)
              ? res.payload.result.value
              : [res.payload.result.value];
            if (values.length > 0 && values[0]?.data) {
              const firstValue = values[0];
              if (Array.isArray(firstValue.data) && firstValue.data.length >= 2) {
                setType(firstValue.data[0]);
                setCurrentValue(JSON.stringify(firstValue.data[1]));
                return;
              } else if (typeof firstValue.data === 'object') {
                const typeKeys = Object.keys(firstValue.data).filter(
                  (k) => !['name', 'elementName'].includes(k)
                );
                if (typeKeys.length > 0) {
                  setType(typeKeys[0]);
                  setCurrentValue(JSON.stringify(firstValue.data[typeKeys[0]]));
                  return;
                }
              }
            }
          }

          setType('Unknown');
          setCurrentValue('N/A');
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
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [objRef, fc, endpoint, cp]);

  const handleSubmit = async () => {
    const newValue = value.trim();
    if (!newValue) {
      setValidation('Please enter a value');
      return;
    }
    setValidation('');
    setIsSubmitting(true);
    try {
      const endpointTarget = `${endpoint.host}:${endpoint.port}`;

      let result = await executeApiCall('write', endpointTarget, {
        objRef,
        fc,
        value: newValue,      // send the raw string, like DataAccessPanel does
        dataType: type,
        ...(cp ? { cp } : {}),
      });

      if (!result?.ok) {
        setResult({ visible: true, success: false, message: 'x Write unsuccessful!' });
      } else {
        setResult({ visible: true, success: true, message: '✓ Write successful!' });
      }
      setTimeout(() => {
        if (onSuccess) onSuccess();
        onClose();
      }, 1500);
    } catch (error) {
      setResult({ visible: true, success: false, message: `✗ Error: ${error.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="control-window" style={{ display: 'flex' }}>
      <div className="modal-content">
        <h2 id="writeValueTitle">Write Data Value</h2>
        <div style={{ marginBottom: '16px', color: '#ccc' }}>
          <div><strong>Reference:</strong> <span style={{ color: '#4fc3f7' }}>{objRef}</span></div>
          <div><strong>Type:</strong> <span style={{ color: '#ffc107' }}>{type}</span></div>
          <div><strong>Current:</strong> <span style={{ color: '#8bc34a' }}>{currentValue}</span></div>
        </div>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Enter new value"
        />
        <div style={{ color: '#f44336', marginBottom: '16px', minHeight: '20px' }}>
          {validation}
        </div>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button className="btn-secondary" style={{ padding: '8px 16px' }} onClick={onClose} disabled={isSubmitting}>
            Cancel
          </button>
          <button className="btn-primary" style={{ padding: '8px 16px' }} onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? 'Writing...' : 'Write'}
          </button>
        </div>
        {result.visible && (
          <div
            style={{
              marginTop: '16px',
              padding: '12px',
              borderRadius: '4px',
              textAlign: 'center',
              background: result.success ? '#2e7d32' : '#c62828',
              color: '#fff',
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