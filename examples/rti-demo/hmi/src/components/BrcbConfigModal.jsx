// src/components/BrcbConfigModal.jsx
import React, { useState, useEffect } from 'react';
import { executeApiCall } from '../services/apiService';

// Default options for optFlds and trgOp checkboxes
const OPT_FLDS_OPTIONS = [
  { value: 'seqNum', label: 'Sequence Number' },
  { value: 'timeStamp', label: 'Time Stamp' },
  { value: 'dataSet', label: 'Data Set' },
  { value: 'reasonCode', label: 'Reason for Inclusion' },
  { value: 'dataRef', label: 'Data Reference' },
  { value: 'bufOvfl', label: 'Buffer Overflow' },
  { value: 'entryID', label: 'Entry ID' },
  { value: 'configRef', label: 'Config Rev' },
];

const TRG_OP_OPTIONS = [
  { value: 'dchg', label: 'Data Change' },
  { value: 'qchg', label: 'Quality Change' },
  { value: 'dupd', label: 'Data Update' },
  { value: 'integrity', label: 'Periodic' },
  { value: 'gi', label: 'General Interrogation' },
];

const BrcbConfigModal = ({
  objRef,
  rcbType = 'BRCB',
  endpoint,
  cp,
  onClose,
  onSuccess,
}) => {
  const [dataSet, setDataSet] = useState('');
  const [intgPd, setIntgPd] = useState(2000);
  const [rptEna, setRptEna] = useState(false);
  const [optFlds, setOptFlds] = useState({});
  const [trgOp, setTrgOp] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [result, setResult] = useState({
    visible: false,
    success: false,
    message: '',
  });

  // Initialize optFlds and trgOp from options
  useEffect(() => {
    const initialOptFlds = {};
    OPT_FLDS_OPTIONS.forEach((opt) => {
      initialOptFlds[opt.value] = false;
    });

    const initialTrgOp = {};
    TRG_OP_OPTIONS.forEach((opt) => {
      initialTrgOp[opt.value] = false;
    });

    setOptFlds(initialOptFlds);
    setTrgOp(initialTrgOp);
  }, []);

  // Fetch current BRCB/URCB values when modal opens
  useEffect(() => {
    const fetchRCBValues = async () => {
      if (!objRef || !endpoint || !rcbType) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);

        const endpointTarget = `${endpoint.host}:${endpoint.port}`;
        const apiId = rcbType === 'BRCB' ? 'brcb-read' : 'urcb-read';

        const result = await executeApiCall(apiId, endpointTarget, {
          objRef,
          cp,
        });

        if (result?.ok && result.payload?.result?.value) {
          const brcbData = result.payload.result.value;

          if (brcbData.dataSet) {
            setDataSet(brcbData.dataSet);
          }

          if (brcbData.intgPd) {
            setIntgPd(brcbData.intgPd);
          }

          if (brcbData.rptEna !== undefined) {
            setRptEna(brcbData.rptEna);
          }

          // Set optFlds checkboxes
          if (brcbData.optFlds) {
            setOptFlds((prev) => {
              const newOptFlds = { ...prev };

              Object.entries(brcbData.optFlds).forEach(([key, value]) => {
                if (Object.prototype.hasOwnProperty.call(newOptFlds, key)) {
                  newOptFlds[key] = value;
                }
              });

              return newOptFlds;
            });
          }

          // Set trgOp checkboxes
          if (brcbData.trgOp) {
            setTrgOp((prev) => {
              const newTrgOp = { ...prev };

              Object.entries(brcbData.trgOp).forEach(([key, value]) => {
                if (Object.prototype.hasOwnProperty.call(newTrgOp, key)) {
                  newTrgOp[key] = value;
                }
              });

              return newTrgOp;
            });
          }
        } else {
          console.error(
            'Failed to fetch BRCB values:',
            result?.payload?.error || 'Unknown error'
          );

          setDataSet('');
          setIntgPd(2000);
          setRptEna(false);
        }
      } catch (error) {
        console.error('Error fetching BRCB values:', error);

        setDataSet('');
        setIntgPd(2000);
        setRptEna(false);
      } finally {
        setIsLoading(false);
      }
    };

    fetchRCBValues();
  }, [objRef, endpoint, rcbType, cp]);

  const handleOptFldChange = (optionValue) => (e) => {
    setOptFlds((prev) => ({
      ...prev,
      [optionValue]: e.target.checked,
    }));
  };

  const handleTrgOpChange = (optionValue) => (e) => {
    setTrgOp((prev) => ({
      ...prev,
      [optionValue]: e.target.checked,
    }));
  };

  const handleSave = async () => {
    if (!objRef || !endpoint || !rcbType) return;

    setIsSaving(true);
    setResult({
      visible: false,
      success: false,
      message: '',
    });

    try {
      const endpointTarget = `${endpoint.host}:${endpoint.port}`;
      const apiId = rcbType === 'BRCB' ? 'brcb-write' : 'urcb-write';

      // Ensure all optFlds and trgOp values are properly set as booleans
      const normalizedOptFlds = {};
      OPT_FLDS_OPTIONS.forEach((opt) => {
        normalizedOptFlds[opt.value] = optFlds[opt.value] || false;
      });

      const normalizedTrgOp = {};
      TRG_OP_OPTIONS.forEach((opt) => {
        normalizedTrgOp[opt.value] = trgOp[opt.value] || false;
      });

      const result = await executeApiCall(apiId, endpointTarget, {
        objRef,
        data: {
          ref: objRef,
          dataSet,
          intgPd: parseInt(intgPd, 10) || 0,
          rptEna,
          optFlds: normalizedOptFlds,
          trgOp: normalizedTrgOp,
        },
        cp,
      });

      if (result?.ok) {
        setResult({
          visible: true,
          success: true,
          message: `${rcbType} configuration saved successfully!`,
        });

        if (onSuccess) {
          onSuccess();
        }

        setTimeout(() => {
          onClose();
        }, 1500);
      } else {
        const errorMsg =
          result?.payload?.error ||
          result?.rawText ||
          `Failed to save ${rcbType} configuration`;

        setResult({
          visible: true,
          success: false,
          message: `Error: ${errorMsg}`,
        });
      }
    } catch (error) {
      console.error(`Error saving ${rcbType} configuration:`, error);

      setResult({
        visible: true,
        success: false,
        message: `Error: ${error.message}`,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="brcb-modal">
      <div className="brcb-modal-content">
        {/* Header */}
        <div className="brcb-modal-header">
          <h2>{rcbType} Configuration</h2>

          <span
            className="brcb-close-modal"
            onClick={onClose}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                onClose();
              }
            }}
            aria-label="Close modal"
          >
            ×
          </span>
        </div>

        {/* Body */}
        <div className="brcb-modal-body">
          <div className="brcb-form-group">
            <label>Object Reference</label>

            <div className="brcb-form-control brcb-object-reference">
              {objRef}
            </div>
          </div>

          {isLoading ? (
            <div className="brcb-loading">
              Loading configuration...
            </div>
          ) : (
            <>
              <div className="brcb-form-group">
                <label htmlFor="brcb-data-set">Data Set</label>

                <input
                  id="brcb-data-set"
                  type="text"
                  className="brcb-form-control"
                  value={dataSet}
                  onChange={(e) => setDataSet(e.target.value)}
                  placeholder="Data set reference"
                />
              </div>

              <div className="brcb-form-group">
                <label htmlFor="brcb-intg-pd">
                  Integrity Period (ms)
                </label>

                <input
                  id="brcb-intg-pd"
                  type="number"
                  className="brcb-form-control"
                  value={intgPd}
                  onChange={(e) =>
                    setIntgPd(parseInt(e.target.value, 10) || 0)
                  }
                  min="0"
                  placeholder="Integrity period in milliseconds"
                />
              </div>

              <div className="brcb-form-group">
                <label className="brcb-checkbox-label">
                  <input
                    type="checkbox"
                    checked={rptEna}
                    onChange={(e) => setRptEna(e.target.checked)}
                  />

                  <span>Report Enabled</span>
                </label>
              </div>

              {/* Optional Fields */}
              <div className="brcb-form-group">
                <label>Optional Fields</label>

                <div className="brcb-checkbox-grid">
                  {OPT_FLDS_OPTIONS.map((opt) => (
                    <label key={opt.value}>
                      <input
                        type="checkbox"
                        checked={optFlds[opt.value] || false}
                        onChange={handleOptFldChange(opt.value)}
                      />

                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Trigger Options */}
              <div className="brcb-form-group">
                <label>Trigger Options</label>

                <div className="brcb-checkbox-grid">
                  {TRG_OP_OPTIONS.map((opt) => (
                    <label key={opt.value}>
                      <input
                        type="checkbox"
                        checked={trgOp[opt.value] || false}
                        onChange={handleTrgOpChange(opt.value)}
                      />

                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Result message */}
        {result.visible && (
          <div
            className={
              result.success
                ? 'brcb-result brcb-result-success'
                : 'brcb-result brcb-result-error'
            }
          >
            {result.message}
          </div>
        )}

        {/* Footer */}
        <div className="brcb-modal-footer">
          <button
            className="brcb-btn brcb-btn-primary"
            onClick={handleSave}
            disabled={isSaving || isLoading}
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>

          <button
            className="brcb-btn brcb-btn-secondary"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default BrcbConfigModal;

