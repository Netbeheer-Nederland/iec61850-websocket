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

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  listPlaybooks, getPlaybook, savePlaybook, uploadPlaybook, deletePlaybook, runPlaybook, stopPlaybook,
  playbookFileUrl, uploadName, uploadFormat, recordingName,
} from '../utils/playbooks';
import { usePlaybookRun } from '../hooks/usePlaybookRun';
import {
  usePlaybookRecorder, startRecording, stopRecording, clearRecording, recordedPlaybook,
} from '../hooks/usePlaybookRecorder';

const LAST_KEY = 'traffic-playbook';
const buttonStyle = { padding: '4px 10px', fontSize: '12px' };

const remembered = () => {
  try {
    return localStorage.getItem(LAST_KEY) || '';
  } catch {
    return '';
  }
};
const remember = (name) => {
  try {
    localStorage.setItem(LAST_KEY, name);
  } catch {
    // storage unavailable - only the convenience is lost
  }
};

function StepMark({ status }) {
  if (status === 'running') return <i className="fas fa-spinner fa-spin" style={{ fontSize: '10px' }}></i>;
  if (status === 'ok') return <span style={{ color: 'var(--success-color)' }}>{'✓'}</span>;
  if (status === 'failed') return <span style={{ color: 'var(--danger-color)' }}>{'✗'}</span>;
  if (status === 'recorded') return <span style={{ color: 'var(--danger-color)' }}>{'●'}</span>;
  return <span style={{ color: 'var(--text-muted)' }}>{'·'}</span>;
}

/**
 * Traffic's playbook block: pick a playbook the BFF keeps (built-in or saved),
 * run it in the BFF and follow each step; download / upload / delete; and
 * record one from clicks on the pinned demo buttons below it.
 */
function PlaybookBar() {
  const [playbooks, setPlaybooks] = useState([]);
  const [selected, setSelected] = useState(remembered);
  const [loaded, setLoaded] = useState(null); // { name, builtin, labels }
  const [error, setError] = useState('');
  const [title, setTitle] = useState('');
  const [saveName, setSaveName] = useState('');
  const run = usePlaybookRun();
  const recorder = usePlaybookRecorder();
  const fileInput = useRef(null);

  const running = run?.state === 'running';
  const unsaved = !recorder.recording && recorder.steps.length > 0;
  const busy = recorder.recording || unsaved;

  const refresh = useCallback(async () => {
    try {
      setPlaybooks(await listPlaybooks());
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  // A run (started here or elsewhere) shows the playbook it runs.
  useEffect(() => {
    if (run?.name && run.state === 'running' && run.name !== selected) setSelected(run.name);
  }, [run, selected]);

  useEffect(() => {
    if (!selected) {
      setLoaded(null);
      return;
    }
    remember(selected);
    let alive = true;
    getPlaybook(selected)
      .then((p) => { if (alive) setLoaded({ name: p.name, builtin: p.builtin, labels: p.labels }); })
      .catch((e) => { if (alive) { setLoaded(null); setError(e.message); } });
    return () => { alive = false; };
  }, [selected]);

  const attempt = async (fn) => {
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
  };

  const onUpload = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    attempt(async () => {
      const name = uploadName(file.name);
      await uploadPlaybook(name, await file.text(), uploadFormat(file.name));
      await refresh();
      setSelected(name);
    });
  };

  const onStopRecording = () => {
    stopRecording();
    if (recorder.steps.length === 0) {
      clearRecording();
      return;
    }
    setSaveName(recordingName());
    setTitle('');
  };

  const onSave = () => attempt(async () => {
    await savePlaybook(saveName, recordedPlaybook(title || saveName));
    clearRecording();
    await refresh();
    setSelected(saveName);
  });

  const onDiscard = () => {
    if (window.confirm('Discard this recording?')) clearRecording();
  };

  const onDelete = () => {
    if (!window.confirm(`Delete playbook "${selected}"?`)) return;
    attempt(async () => {
      await deletePlaybook(selected);
      setSelected('');
      await refresh();
    });
  };

  // What the step list shows: the recording, the run of this playbook, or
  // the loaded playbook's steps.
  let rows = [];
  if (busy) {
    rows = recorder.steps.map((s, i) => ({ index: i + 1, label: s.label, status: 'recorded', message: s.expect === 'fail' ? 'expects a refusal' : '' }));
  } else if (run && run.name === selected) {
    rows = run.steps;
  } else if (loaded) {
    rows = loaded.labels.map((label, i) => ({ index: i + 1, label, status: 'pending', message: '' }));
  }

  return (
    <div className="playbook-bar" style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', marginBottom: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <select
          aria-label="Playbook"
          value={selected}
          disabled={running || busy}
          onChange={(e) => setSelected(e.target.value)}
          style={{ fontSize: '12px', padding: '3px 6px' }}
        >
          <option value="">Choose a playbook…</option>
          {playbooks.map((p) => (
            <option key={p.name} value={p.name} disabled={Boolean(p.error)} title={p.error || ''}>
              {p.title}{p.title !== p.name ? ` (${p.name})` : ''}{p.builtin ? ' - built-in' : ''}
            </option>
          ))}
        </select>
        <button className="btn-primary" style={buttonStyle} disabled={!loaded || running || busy}
          onClick={() => attempt(() => runPlaybook(selected))} title="Run this playbook in the BFF">
          <i className="fas fa-play" style={{ fontSize: '10px' }}></i>Run
        </button>
        {running && (
          <button className="btn-secondary" style={buttonStyle} onClick={() => attempt(stopPlaybook)} title="Stop after the current step">
            <i className="fas fa-stop" style={{ fontSize: '10px' }}></i>Stop
          </button>
        )}
        {loaded && (
          <a className="btn-secondary" style={buttonStyle} href={playbookFileUrl(selected)} download>
            <i className="fas fa-download" style={{ fontSize: '10px' }}></i>Download
          </a>
        )}
        <button className="btn-secondary" style={buttonStyle} disabled={running || busy}
          onClick={() => fileInput.current?.click()} title="Upload a .yaml or .json playbook">
          <i className="fas fa-upload" style={{ fontSize: '10px' }}></i>Upload
        </button>
        <input ref={fileInput} type="file" accept=".yaml,.yml,.json" aria-label="Upload a playbook file"
          style={{ display: 'none' }} onChange={onUpload} />
        {loaded && !loaded.builtin && (
          <button className="btn-secondary" style={buttonStyle} disabled={running || busy} onClick={onDelete} title="Delete this playbook">
            <i className="fas fa-trash" style={{ fontSize: '10px' }}></i>
          </button>
        )}
        <span style={{ flex: 1 }} />
        {recorder.recording ? (
          <button className="btn-secondary" style={{ ...buttonStyle, color: 'var(--danger-color)' }} onClick={onStopRecording}>
            <i className="fas fa-stop" style={{ fontSize: '10px' }}></i>Stop recording
          </button>
        ) : (
          <button className="btn-secondary" style={buttonStyle} disabled={running || unsaved} onClick={startRecording}
            title="Record clicks on the demo buttons below as a playbook">
            <i className="fas fa-circle" style={{ fontSize: '10px', color: 'var(--danger-color)' }}></i>Record
          </button>
        )}
      </div>

      {unsaved && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <label>Name <input aria-label="Name" value={saveName} onChange={(e) => setSaveName(e.target.value)} style={{ fontSize: '12px' }} /></label>
          <label>Title <input aria-label="Title" value={title} placeholder={saveName} onChange={(e) => setTitle(e.target.value)} style={{ fontSize: '12px' }} /></label>
          <button className="btn-primary" style={buttonStyle} disabled={!saveName} onClick={onSave}>Save</button>
          <button className="btn-secondary" style={buttonStyle} onClick={onDiscard}>Discard</button>
        </div>
      )}

      {error && <div style={{ color: 'var(--danger-color)' }}>{error}</div>}
      {run?.name === selected && run.state === 'error' && run.error && (
        <div style={{ color: 'var(--danger-color)' }}>Couldn't run: {run.error}</div>
      )}
      {recorder.notes.map((note) => <div key={note} style={{ color: 'var(--text-muted)' }}>{note}</div>)}
      {recorder.recording && rows.length === 0 && (
        <div style={{ color: 'var(--text-muted)' }}>Recording - click the demo buttons below.</div>
      )}

      {rows.length > 0 && (
        <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {rows.map((step) => (
            <li key={step.index} data-testid={`playbook-step-${step.index}`} style={{ display: 'flex', gap: '6px', alignItems: 'baseline' }}>
              <span style={{ minWidth: '20px', textAlign: 'right', color: 'var(--text-muted)' }}>{step.index}</span>
              <StepMark status={step.status} />
              <span>{step.label}</span>
              {step.message && <span style={{ color: 'var(--text-muted)' }}>· {step.message}</span>}
              {step.seconds != null && step.status !== 'running' && step.status !== 'pending' && (
                <span style={{ color: 'var(--text-muted)' }}>({step.seconds}s)</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default PlaybookBar;
