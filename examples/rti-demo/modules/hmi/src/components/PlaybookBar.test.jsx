import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

const pushes = new Map();
vi.mock('../services/liveSocket', () => ({
  subscribe: (type, fn) => {
    pushes.set(type, fn);
    return () => pushes.delete(type);
  },
}));
vi.mock('../utils/playbooks', async (importOriginal) => ({
  ...(await importOriginal()),
  listPlaybooks: vi.fn(),
  getPlaybook: vi.fn(),
  savePlaybook: vi.fn(async () => ({ ok: true })),
  uploadPlaybook: vi.fn(async () => ({ ok: true })),
  deletePlaybook: vi.fn(async () => ({ ok: true })),
  runPlaybook: vi.fn(),
  stopPlaybook: vi.fn(async () => ({ ok: true })),
  getPlaybookRun: vi.fn(),
  playbookFileUrl: (name) => `http://bff/api/playbooks/${name}/file`,
  uploadName: (n) => n.replace(/\.ya?ml$/, ''),
  uploadFormat: () => 'yaml',
  recordingName: () => 'recording-20261005-0900',
}));

import PlaybookBar from './PlaybookBar';
import * as api from '../utils/playbooks';
import { startRecording, recordClick, resetPlaybookRecorderStore } from '../hooks/usePlaybookRecorder';

const LIST = [
  { name: 'demo', builtin: true, title: 'SO with two FSPs', steps: 2 },
  { name: 'rec1', builtin: false, title: 'Rec', steps: 1 },
];
const DEMO = { name: 'demo', builtin: true, playbook: { steps: [{}, {}] }, labels: ['FSP01 dials the SO', 'Read status'] };
const runState = (state, statuses, extra = {}) => ({
  name: 'demo', title: 'SO with two FSPs', state, current: null, error: null,
  steps: statuses.map((status, i) => ({ index: i + 1, label: DEMO.labels[i], status, message: status === 'ok' ? 'fine' : '', seconds: 0.1 })),
  ...extra,
});

// The select only takes a value once its options have loaded.
const pick = async (value) => {
  await waitFor(() => expect(screen.getByLabelText('Playbook').querySelector(`option[value="${value}"]`)).not.toBeNull());
  fireEvent.change(screen.getByLabelText('Playbook'), { target: { value } });
};

describe('PlaybookBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetPlaybookRecorderStore();
    localStorage.clear();
    api.listPlaybooks.mockResolvedValue(LIST);
    api.getPlaybook.mockResolvedValue(DEMO);
    api.getPlaybookRun.mockResolvedValue(null);
  });

  it('loads a playbook and shows its steps', async () => {
    render(<PlaybookBar />);
    await pick('demo');
    expect(await screen.findByText('FSP01 dials the SO')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Download/ })).toHaveAttribute('href', 'http://bff/api/playbooks/demo/file');
    expect(screen.queryByTitle('Delete this playbook')).not.toBeInTheDocument(); // built-in
  });

  it('runs and follows the pushed progress', async () => {
    api.runPlaybook.mockResolvedValue(runState('running', ['pending', 'pending']));
    render(<PlaybookBar />);
    await pick('demo');
    await screen.findByText('FSP01 dials the SO');
    fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await waitFor(() => expect(api.runPlaybook).toHaveBeenCalledWith('demo'));

    act(() => pushes.get('playbook-run')({ type: 'playbook-run', data: runState('running', ['ok', 'running']) }));
    expect(screen.getByTestId('playbook-step-1').textContent).toContain('✓');
    expect(screen.getByTestId('playbook-step-1').textContent).toContain('fine');
    expect(screen.getByRole('button', { name: /Run/ })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Stop/ }));
    expect(api.stopPlaybook).toHaveBeenCalled();

    act(() => pushes.get('playbook-run')({ type: 'playbook-run', data: runState('error', ['ok', 'failed'], { error: "FSP 'X' is not registered" }) }));
    expect(screen.getByText(/FSP 'X' is not registered/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run/ })).not.toBeDisabled();
  });

  it('shows a run already going on load', async () => {
    api.getPlaybookRun.mockResolvedValue(runState('running', ['ok', 'running']));
    render(<PlaybookBar />);
    expect(await screen.findByTestId('playbook-step-1')).toHaveTextContent('✓');
    await waitFor(() => expect(screen.getByLabelText('Playbook')).toHaveValue('demo'));
    expect(screen.getByRole('button', { name: /Run/ })).toBeDisabled();
  });

  it('records, then saves under a name and title', async () => {
    render(<PlaybookBar />);
    fireEvent.click(await screen.findByRole('button', { name: /Record/ }));
    act(() => recordClick([{
      action: { label: 'Read', service: 'read', soTarget: 'so:1', soName: 'SO', objRef: 'R', fc: 'st' },
      fsp: 'F1', result: { ok: true, message: 'ok' },
    }]));
    expect(screen.getByText('Read')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Stop recording/ }));

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'My demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.savePlaybook).toHaveBeenCalledWith('recording-20261005-0900', {
      name: 'My demo', so: 'SO', pace: '2s', steps: [{ label: 'Read', read: { fsp: 'F1', ref: 'R', fc: 'st' } }],
    }));
  });

  it('ends an empty recording without asking to save', async () => {
    render(<PlaybookBar />);
    fireEvent.click(await screen.findByRole('button', { name: /Record/ }));
    fireEvent.click(screen.getByRole('button', { name: /Stop recording/ }));
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument();
  });

  it('shows an upload refused by the BFF', async () => {
    api.uploadPlaybook.mockRejectedValueOnce(new Error("'demo' is a built-in playbook - save under another name"));
    render(<PlaybookBar />);
    const file = new File(['steps: []'], 'demo.yaml');
    fireEvent.change(await screen.findByLabelText('Upload a playbook file'), { target: { files: [file] } });
    expect(await screen.findByText(/built-in playbook/)).toBeInTheDocument();
  });

  it('deletes a saved playbook after confirming', async () => {
    api.getPlaybook.mockResolvedValue({ ...DEMO, name: 'rec1', builtin: false });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<PlaybookBar />);
    await pick('rec1');
    fireEvent.click(await screen.findByTitle('Delete this playbook'));
    await waitFor(() => expect(api.deletePlaybook).toHaveBeenCalledWith('rec1'));
  });
});
