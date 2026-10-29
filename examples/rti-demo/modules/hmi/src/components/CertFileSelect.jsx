/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// The BFF's certificate directory (GET /api/certs), shared by the TLS and
// OAuth dialogs: a select per PEM field that puts `file:<name>` in it, and a
// note saying where the instance reads that file from.
import React, { useState, useEffect } from 'react';
import { log } from '../utils/log';

const FILE_REF_PREFIX = 'file:';

// Files in the BFF's certificate directory (/certs) while `isOpen`. Empty
// when the BFF has no such directory (or predates /api/certs).
export function useCertDir(isOpen, bffBaseUrl) {
  const [certDir, setCertDir] = useState({ path: null, files: [] });
  useEffect(() => {
    if (!isOpen) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${bffBaseUrl}/api/certs`);
        if (!response.ok) return;
        const body = await response.json();
        if (!cancelled && body?.available) {
          setCertDir({ path: body.cert_dir, files: Array.isArray(body.files) ? body.files : [] });
        }
      } catch (error) {
        log.warn('Certificate directory not available:', error);
      }
    })();
    return () => { cancelled = true; };
  }, [isOpen, bffBaseUrl]);
  return certDir;
}

// One option per file in the BFF's certificate directory (GET /api/certs).
function certFileLabel(file) {
  if (file.kind !== 'certificate') return file.name;
  const expires = file.not_after ? `, expires ${file.not_after.slice(0, 10)}` : '';
  return `${file.name} - ${file.subject}${file.is_ca ? ' (CA)' : ''}${expires}`;
}

// Pick a file from the certificate directory: the field then holds `file:<name>`,
// which the instance reads from its own /certs mount, so the PEM text (and a
// private key) never passes through the browser. Hidden when the directory has
// nothing that fits.
export function CertFileSelect({ id, files, value, onChange, style }) {
  if (!files.length) return null;
  const selected = files.some((f) => f.reference === value) ? value : '';
  return (
    <select
      id={id}
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      style={{ ...style, marginBottom: '10px' }}
      aria-label="From the certificate directory"
    >
      <option value="">From the certificate directory...</option>
      {files.map((f) => (
        <option key={f.reference} value={f.reference}>{certFileLabel(f)}</option>
      ))}
    </select>
  );
}

export function CertReferenceNote({ value, certDir }) {
  if (!value || !value.startsWith(FILE_REF_PREFIX)) return null;
  const name = value.slice(FILE_REF_PREFIX.length);
  return (
    <div style={{ marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
      Read by the instance from {certDir || '/certs'}/{name} in its own certificate directory.
    </div>
  );
}
