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
    
    // Simulate API call
    try {
      // This would be replaced with actual API call
      // const response = await fetch(`/api/data/read?ref=${encodeURIComponent(dataRef)}`);
      // const data = await response.json();
      // setOutput(JSON.stringify(data, null, 2));
      
      // Mock response
      setTimeout(() => {
        setOutput(`Read successful:\n{\n  "reference": "${dataRef}",\n  "value": "sample-value",\n  "timestamp": "${new Date().toISOString()}"\n}`);
      }, 1000);
    } catch (error) {
      setOutput(`Error reading data: ${error.message}`);
    }
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
    
    // Simulate API call
    try {
      // This would be replaced with actual API call
      // const response = await fetch('/api/data/write', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify({ ref: dataRef, value: dataValue })
      // });
      // const data = await response.json();
      // setOutput(JSON.stringify(data, null, 2));
      
      // Mock response
      setTimeout(() => {
        setOutput(`Write successful:\n{\n  "reference": "${dataRef}",\n  "value": "${dataValue}",\n  "timestamp": "${new Date().toISOString()}"\n}`);
      }, 1000);
    } catch (error) {
      setOutput(`Error writing data: ${error.message}`);
    }
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
