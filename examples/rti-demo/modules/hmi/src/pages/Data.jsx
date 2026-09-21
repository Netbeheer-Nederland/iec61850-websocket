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

import React, { useState } from 'react';

function Data() {
  const [dataRef, setDataRef] = useState('');
  const [dataValue, setDataValue] = useState('');
  const [output, setOutput] = useState('');

  const handleRead = async () => {
    if (!dataRef) {
      setOutput('Please enter a data reference');
      return;
    }
    
    setOutput(`Reading data from: ${dataRef}\n...`);
    
  };

  const handleWrite = async () => {
    if (!dataRef) {
      setOutput('Please enter a data reference');
      return;
    }
    if (!dataValue) {
      setOutput('Please enter a value to write');
      return;
    }
    
    setOutput(`Writing data to: ${dataRef}\nValue: ${dataValue}\n...`);
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>Read / Write Data</h1>
      </div>
      <div className="data-section">
        <div className="data-input-group">
          <label htmlFor="data-ref">Data Reference (e.g., LD0/LLN0.Mod)</label>
          <div className="input-group">
            <input 
              type="text" 
              id="data-ref" 
              placeholder="Enter data reference"
              value={dataRef}
              onChange={(e) => setDataRef(e.target.value)}
            />
            <button className="btn-primary" id="btn-read-data" onClick={handleRead}>
              <i className="fas fa-download"></i>
              Read
            </button>
            <button className="btn-primary" id="btn-write-data" onClick={handleWrite}>
              <i className="fas fa-upload"></i>
              Write
            </button>
          </div>
        </div>
        <div className="data-value-group">
          <label htmlFor="data-value">Value</label>
          <input 
            type="text" 
            id="data-value" 
            placeholder="Enter value to write"
            value={dataValue}
            onChange={(e) => setDataValue(e.target.value)}
          />
        </div>
        <div className="data-output" id="data-output">
          {output || 'Enter a data reference and click Read/Write to see results.'}
        </div>
      </div>
    </section>
  );
}

export default Data;
