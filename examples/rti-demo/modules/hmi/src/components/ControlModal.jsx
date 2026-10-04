/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025 Netbeheer Nederland
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

// src/components/ControlModal.jsx
import React, { useState, useEffect } from 'react';
import { executeApiCall, getApiById } from '../services/apiService';
import { controlValue, soAnswer } from '../utils/demoActions';

const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

const ControlModal = ({ objRef, objName, cdc, endpoint, cp, onClose, onSuccess, onError = () => {} }) => {
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
      // Through the BFF to the SO's /api/select, like Operate (this used to
      // POST a relative /api/control/select - the HMI's own server, which
      // has no such route). The SO answers like operate: { ok, error }.
      const endpointTarget = `${endpoint.host}:${endpoint.port}`;
      const response = await executeApiCall('select', endpointTarget, { objRef, cp });
      const answer = soAnswer(response, 'select');
      if (answer.ok) {
        setResult({ visible: true, success: true, message: 'Select successful - Now you can Operate' });
      } else {
        setResult({ visible: true, success: false, message: `Select failed: ${answer.message}` });
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
      // The SO answers a refused operate with HTTP 200 { ok: false, error } -
      // see soAnswer.
      const answer = soAnswer(response, 'operate');

      if (answer.ok) {
        setResult({ visible: true, success: true, message: 'Operate successful' });
        onSuccess(response?.payload);
      } else {
        setResult({ visible: true, success: false, message: `Operate failed: ${answer.message}` });
        onError(answer.message);
      }
    } catch (error) {
      setResult({ visible: true, success: false, message: `Operate error: ${error.message}` });
      onError(error.message);
    } finally {
      setIsOperating(false);
    }
  };

  const getControlParameters = () => {
    const { value, valueType } = controlValue(cdc, ctlVal);

    return {
      objRef,
      value,
      value_type: valueType,
      ctlNum: parseInt(ctlNum),
      origin: { orCat: parseInt(originCat), orIdent: originIdent },
      test: testMode,
      cp,
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
              cdc?.toUpperCase() === 'DPC' ? 'on or off' :
              cdc?.toUpperCase() === 'APC' ? 'Float value (e.g., 123.45)' :
              cdc?.toUpperCase() === 'INC' || cdc?.toUpperCase() === 'ENC' ? 'Integer value' :
              cdc?.toUpperCase() === 'BSC' ? 'step-up or step-down' :
              'Control value'
            }
          />
        </div>
        <div className="modal-buttons">
          {/* Select-before-operate controls (ctlModel sbo-with-*) need a
              Select first; direct ones don't, so it's only offered then. */}
          {/sbo/i.test(String(ctlModel)) && (
            <button className="btn-secondary" onClick={handleSelect} disabled={isSelecting || isOperating}>
              {isSelecting ? 'Selecting...' : 'Select'}
            </button>
          )}
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
