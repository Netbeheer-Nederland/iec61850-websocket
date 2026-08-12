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
      case 'ING':
        valueType = 'int32';
        parsedCtlVal = parseInt(parsedCtlVal);
        if (isNaN(parsedCtlVal)) throw new Error('Invalid ING value. Must be an integer');
        break;
      case 'ASG':
        valueType = 'string';
        // ASG typically uses enumerated values
        break;
      case 'CTE':
        valueType = 'int32';
        parsedCtlVal = parseInt(parsedCtlVal);
        if (isNaN(parsedCtlVal)) throw new Error('Invalid CTE value. Must be an integer');
        break;
      case 'ENG':
        valueType = 'enumerated';
        // ENG typically uses enumerated values
        break;
      default:
        throw new Error('Unsupported CDC type for control');
    }

    return {
      objRef,
      value: parsedCtlVal,
      value_type: valueType,
      ctlNum: parseInt(ctlNum),
      origin: { orCat: parseInt(originCat), orIdent: originIdent },
      test: testMode,
    };
  };

  return (
    <div className="control-window">
      <div className="modal-content">
        <h2>Control Operation</h2>
        <div className="form-group">
          <label>Object Reference:</label>
          <div>{objRef}</div>
        </div>
        <div className="form-group">
          <label>CDC:</label>
          <div>{cdc || 'Unknown'}</div>
        </div>
        <div className="form-group">
          <label>ctlModel:</label>
          <div>{ctlModel}</div>
        </div>
        <div className="form-group">
          <label>ctlNum:</label>
          <input
            type="number"
            value={ctlNum}
            onChange={(e) => setCtlNum(parseInt(e.target.value) || 0)}
          />
        </div>
        <div className="form-group">
          <label>Origin Category:</label>
          <input
            type="number"
            value={originCat}
            onChange={(e) => setOriginCat(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>Origin Identifier:</label>
          <input
            type="text"
            value={originIdent}
            onChange={(e) => setOriginIdent(e.target.value)}
          />
        </div>
        <div className="test-mode-container">
          <input
            type="checkbox"
            id="testMode"
            checked={testMode}
            onChange={(e) => setTestMode(e.target.checked)}
          />
          <label htmlFor="testMode">Test Mode</label>
        </div>
        <div className="form-group">
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
        <div className="modal-buttons">
          <button className="btn-primary" onClick={handleOperate} disabled={isSelecting || isOperating}>
            {isOperating ? 'Operating...' : 'Operate'}
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
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