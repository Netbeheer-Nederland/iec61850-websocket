/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Tree from './Tree';

const MODEL = {
  children: [{
    name: 'LD0', ref: 'LD0', type: 'LDevice',
    children: [{
      name: 'CSWI1', ref: 'LD0/CSWI1', type: 'LogicalNode',
      children: [
        { name: 'Pos', ref: 'LD0/CSWI1.Pos', type: 'DO', cdc: 'DPC' },
        { name: 'Beh', ref: 'LD0/CSWI1.Beh', type: 'DO', cdc: 'ENS' },
      ],
    }],
  }],
};
const ALL_OPEN = { LD0: true, 'LD0/CSWI1': true };

describe('Tree - plugin claims', () => {
  it('names the plugin on the data object whose Operate it answers', () => {
    render(<Tree data={MODEL} expandedNodes={ALL_OPEN} onExpandToggle={() => {}} claimOwners={{ 'LD0/CSWI1.Pos.Oper.ctlVal': 'io' }} />);

    const tag = screen.getByTestId('plugin-claim-LD0/CSWI1.Pos');
    expect(tag.textContent.trim()).toBe('io');
    expect(tag.title).toBe("Operate answered by plugin 'io'");
    expect(screen.queryByTestId('plugin-claim-LD0/CSWI1.Beh')).not.toBeInTheDocument();
    expect(screen.queryByTestId('plugin-claim-LD0/CSWI1')).not.toBeInTheDocument();
  });

  it('marks nothing without claims', () => {
    render(<Tree data={MODEL} expandedNodes={ALL_OPEN} onExpandToggle={() => {}} />);
    expect(screen.queryByTestId(/plugin-claim-/)).not.toBeInTheDocument();
  });
});
