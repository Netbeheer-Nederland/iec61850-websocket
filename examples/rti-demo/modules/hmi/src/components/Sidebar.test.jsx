// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import Sidebar, { COLLAPSED_KEY } from './Sidebar';

function renderSidebar() {
  return render(
    <MemoryRouter initialEntries={['/overview']}>
      <Sidebar />
    </MemoryRouter>
  );
}

const aside = () => screen.getByRole('complementary');

describe('Sidebar collapse button', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('is expanded by default', () => {
    renderSidebar();
    const button = screen.getByRole('button', { name: 'Collapse sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(aside()).not.toHaveClass('collapsed');
    expect(screen.getByText('IEC 61850')).toBeVisible();
  });

  it('collapses to icons, and expands again', () => {
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));

    expect(aside()).toHaveClass('collapsed');
    const button = screen.getByRole('button', { name: 'Expand sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(button);
    expect(aside()).not.toHaveClass('collapsed');
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument();
  });

  it('keeps each page reachable by name, with its label as tooltip, when collapsed', () => {
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));

    const link = screen.getByRole('link', { name: 'Connections' });
    expect(link).toHaveAttribute('href', '/connections');
    expect(link).toHaveAttribute('title', 'Connections');
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveClass('active');
  });

  it('has no tooltips while expanded', () => {
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Connections' })).not.toHaveAttribute('title');
  });

  it('remembers the choice for the next visit', () => {
    const { unmount } = renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(localStorage.getItem(COLLAPSED_KEY)).toBe('true');
    unmount();

    renderSidebar();
    expect(aside()).toHaveClass('collapsed');
  });

  it('still works when the browser blocks storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    renderSidebar();
    expect(aside()).not.toHaveClass('collapsed');
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(aside()).toHaveClass('collapsed');
  });
});
