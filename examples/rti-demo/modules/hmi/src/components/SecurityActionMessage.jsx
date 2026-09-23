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

// SecurityActionMessage.jsx
import React, { useEffect } from 'react';

const DISMISS_AFTER_MS = 5000;

// Result of a TLS Config / Enable OAuth action (success or error), rendered
// directly under those buttons - not under the ACSI Client/Server section,
// which is about something else entirely. Clears itself after a few seconds;
// see the ACSI screens in docs/rti-demo/design/wireframe.html.
const SecurityActionMessage = ({ message, onDismiss, id }) => {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onDismiss, DISMISS_AFTER_MS);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  if (!message) return null;

  const isSuccess = message.type === 'success';
  return (
    <div
      id={id}
      className="alert"
      role="status"
      style={{
        marginTop: '-12px',
        marginBottom: '24px',
        padding: '12px',
        // Not var(--success-bg)/var(--danger-bg) - neither token is defined
        // in styles.css, so the box rendered with no background at all.
        // Same low-opacity tint + border as TLSConfigModal's errorBox.
        background: isSuccess ? 'rgba(76, 175, 80, 0.15)' : 'rgba(244, 67, 54, 0.15)',
        border: `1px solid ${isSuccess ? 'var(--success-color)' : 'var(--danger-color)'}`,
        color: isSuccess ? 'var(--success-color)' : 'var(--danger-color)',
        borderRadius: '4px',
        display: 'flex',
        alignItems: 'center'
      }}
    >
      <i className={`fas fa-${isSuccess ? 'check-circle' : 'exclamation-circle'}`} style={{ marginRight: '8px' }}></i>
      {message.text}
    </div>
  );
};

export default SecurityActionMessage;
