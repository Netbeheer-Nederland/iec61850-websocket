/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { diagnosticCount } from '@codemirror/lint';
import { EditorView } from '@codemirror/view';
import JsonEditor from './JsonEditor';

const view = () => EditorView.findFromDOM(document.querySelector('#json .cm-editor'));

describe('JsonEditor', () => {
  it('shows the text, and names the editable element', () => {
    render(<JsonEditor id="json" label="Settings (JSON)" value={'{"rotate": 90}'} onChange={() => {}} />);
    expect(screen.getByRole('textbox', { name: 'Settings (JSON)' })).toBeInTheDocument();
    expect(view().state.doc.toString()).toBe('{"rotate": 90}');
  });

  it('passes on what is typed, as text', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<JsonEditor id="json" label="Settings (JSON)" value="" onChange={onChange} />);
    await user.click(screen.getByRole('textbox', { name: 'Settings (JSON)' }));
    await user.keyboard('1');
    expect(onChange).toHaveBeenLastCalledWith('1', expect.anything());
  });

  it('marks text that is not JSON', async () => {
    render(<JsonEditor id="json" value='{"rotate": }' onChange={() => {}} />);
    await waitFor(() => expect(diagnosticCount(view().state)).toBe(1));
  });

  it('marks nothing in valid JSON, or in an empty field', async () => {
    const { unmount } = render(<JsonEditor id="json" value='{"rotate": 90}' onChange={() => {}} />);
    await new Promise((r) => setTimeout(r, 400));
    expect(diagnosticCount(view().state)).toBe(0);
    unmount();

    render(<JsonEditor id="json" value="" onChange={() => {}} />);
    await new Promise((r) => setTimeout(r, 400));
    expect(diagnosticCount(view().state)).toBe(0);
  });
});
