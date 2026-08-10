// src/components/ControlModal.jsx
import React, { useState, useEffect } from 'react';
import { executeApiCall, getApiById } from '../services/apiService';

const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

const ControlModal = ({ objRef, objName, cdc, endpoint, cp, onClose, onSuccess }) => {
  const [ctlVal, setCtlVal] = useState('');
  const [ctlNum, setCtlNum] = useState(0);
  const [originCat, setOriginCat] = useState('1');
  const [originIdent, setOriginIdent] = useState('0');
  const [testMode, setTestMode] = useState(false);
  const [ctlModel, setCtlModel] = useState('Loading...');
  const [isSelecting, setIsSelecting] = useState(false);
  const [isOperating, setIsOperating] = useState(false);
  const [result, setResult] = useState({ visible: false, success: false, message: '' });

  const ctlModelMap = {
    0: 'status-only',
    1: 'direct-with-normal-security',
    2: 'sbo-with-normal-security',
    3: 'direct-with-enhanced-security',
    4: 'sbo-with-enhanced-security',
  };

  useEffect(() => {
    const fetchCtlModel = async () => {
      try {
        const endpointTarget = `${endpoint.host}:${endpoint.port}`;
        const ctlModelRef = `${objRef}.ctlModel`;
        const res = await executeApiCall('read', endpointTarget, { objRef: ctlModelRef, fc: 'cf', cp });
        if (res?.ok) {
          let ctlModelValue = 'N/A';
          if (res.payload?.result?.value) {
            const value = res.payload.result.value;
            if (Array.isArray(value) && value[0]?.data) {
              const dataObj = value[0].data;
              if (Array.isArray(dataObj) && dataObj.length === 2) {
                ctlModelValue = dataObj[1];
              } else if (dataObj?.enumerated) {
                ctlModelValue = dataObj.enumerated;
              } else if (typeof dataObj === 'object') {
                ctlModelValue = Object.values(dataObj)[0];
              }
            }
            if (typeof ctlModelValue === 'number' && ctlModelMap[ctlModelValue]) {
              setCtlModel(`${ctlModelValue} (${ctlModelMap[ctlModelValue]})`);
            } else if (typeof ctlModelValue === 'string' && !isNaN(ctlModelValue)) {
              const numValue = parseInt(ctlModelValue);
              setCtlModel(numValue in ctlModelMap ? `${numValue} (${ctlModelMap[numValue]})` : ctlModelValue);
            } else {
              setCtlModel(ctlModelValue);
            }
          }
        }
      } catch (error) {
        console.error('Error fetching ctlModel:', error);
        setCtlModel('N/A');
      }
    };
    fetchCtlModel();
  }, [objRef, endpoint, cp]);

  const handleSelect = async () => {
    setIsSelecting(true);
    try {
      const params = getControlParameters();
      const response = await fetch('/api/control/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      const result = await response.json();
      if (response.ok) {
        setResult({ visible: true, success: true, message: 'Select successful - Now you can Operate' });
      } else {
        setResult({ visible: true, success: false, message: `Select failed: ${result.error || 'Unknown error'}` });
      }
    } catch (error) {
      setResult({ visible: true, success: false, message: `Select error: ${error.message}` });
    } finally {
      setIsSelecting(false);
    }
  };

  const handleOperate = async () => {
    setIsOperating(true);
    try {
      const params = getControlParameters();
      const endpointTarget = `${endpoint.host}:${endpoint.port}`;
      const response = await executeApiCall('operate', endpointTarget, params);
      if (response?.ok) {
        setResult({ visible: true, success: true, message: 'Operate successful' });
        onSuccess();
      } else {
        setResult({ visible: true, success: false, message: `Operate failed: ${response.error || 'Unknown error'}` });
      }
    } catch (error) {
      setResult({ visible: true, success: false, message: `Operate error: ${error.message}` });
    } finally {
      setIsOperating(false);
    }
  };

  const getControlParameters = () => {
    let parsedCtlVal = ctlVal.trim();
    let valueType = 'unknown';

    switch (cdc?.toUpperCase()) {
      case 'SPC':
        valueType = 'boolean';
        if (['true', '1', 'on'].includes(parsedCtlVal.toLowerCase())) parsedCtlVal = true;
        else if (['false', '0', 'off'].includes(parsedCtlVal.toLowerCase())) parsedCtlVal = false;
        else throw new Error('Invalid SPC value. Use true/false or on/off');
        break;
      case 'DPC':
        valueType = 'enumerated';
        const dpcMap = { on: 'on', off: 'off', intermediate: 'intermediateState' };
        parsedCtlVal = dpcMap[parsedCtlVal.toLowerCase()];
        if (!parsedCtlVal) throw new Error('Invalid DPC value. Use on, off, or intermediate-state');
        break;
      case 'APC':
        valueType = 'float32';
        parsedCtlVal = parseFloat(parsedCtlVal);
        if (isNaN(parsedCtlVal)) throw new Error('Invalid APC value. Must be a number');
        break;
      case 'INC':
      case 'ENC':
        valueType = 'int32';
        parsedCtlVal = parseInt(parsedCtlVal);
        if (isNaN(parsedCtlVal)) throw new Error('Invalid value. Must be an integer');
        break;
      case 'BSC':
        valueType = 'string';
        const bscMap = { up: 'stepUp', down: 'stepDown' };
        parsedCtlVal = bscMap[parsedCtlVal.toLowerCase()];
        if (!parsedCtlVal) throw new Error('Invalid BSC value. Use step-up or step-down');
        break;
      default:
        throw new Error('Unsupported CDC type for control');
    }

    return {
      objRef,
      value: parsedCtlVal,
      value_type: valueType,
      ctlNum: parseInt(ctlNum),
      origin: { orCat: parseInt(originCat), orIdent },
      test: testMode,
    };
  };

  return (
    <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000 }}>
      <div className="control-modal" style={{ background: 'white', padding: '20px', borderRadius: '8px', maxWidth: '500px', margin: '50px auto' }}>
        <h2>Control Operation</h2>
        <div>
          <label>Object Reference:</label>
          <div>{objRef}</div>
        </div>
        <div>
          <label>CDC:</label>
          <div>{cdc || 'Unknown'}</div>
        </div>
        <div>
          <label>ctlModel:</label>
          <div>{ctlModel}</div>
        </div>
        <div style={{ margin: '16px 0' }}>
          <label>Value:</label>
          <input
            type={cdc?.toUpperCase() === 'APC' ? 'number' : cdc?.toUpperCase() === 'INC' || cdc?.toUpperCase() === 'ENC' ? 'number' : 'text'}
            value={ctlVal}
            onChange={(e) => setCtlVal(e.target.value)}
            placeholder={
              cdc?.toUpperCase() === 'SPC' ? 'true or false' :
              cdc?.toUpperCase() === 'DPC' ? 'on, off, or intermediate-state' :
              cdc?.toUpperCase() === 'APC' ? 'Float value (e.g., 123.45)' :
              cdc?.toUpperCase() === 'INC' || cdc?.toUpperCase() === 'ENC' ? 'Integer value' :
              cdc?.toUpperCase() === 'BSC' ? 'step-up or step-down' :
              'Control value'
            }
          />
        </div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          <button onClick={handleSelect} disabled={isSelecting}>
            {isSelecting ? 'Selecting...' : 'Select'}
          </button>
          <button onClick={handleOperate} disabled={isOperating}>
            {isOperating ? 'Operating...' : 'Operate'}
          </button>
          <button onClick={onClose}>Cancel</button>
        </div>
        {result.visible && (
          <div className={`control-result ${result.success ? 'success' : 'error'}`}>
            {result.message}
          </div>
        )}
      </div>
    </div>
  );
};

export default ControlModal;