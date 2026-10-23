/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// A JSON text field: CodeMirror 6 with JSON highlighting, bracket matching
// and folding, and a syntax error marked where it is while typing. The value
// stays text; the caller parses it (an empty one means "none").
import React, { useMemo } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { syntaxHighlighting } from '@codemirror/language';
import { linter, lintGutter } from '@codemirror/lint';
import { oneDarkHighlightStyle } from '@codemirror/theme-one-dark';
import { EditorView } from '@codemirror/view';

// Colours from the HMI's own variables (assets/styles.css), so the editor
// looks like the other inputs.
const theme = EditorView.theme({
  '&': {
    background: 'var(--bg-secondary)',
    color: 'var(--text-primary)',
    border: '1px solid var(--border-color)',
    borderRadius: '4px',
    fontSize: '13px',
  },
  '&.cm-focused': { outline: '2px solid var(--primary-light)' },
  '.cm-content': { caretColor: 'var(--text-primary)', fontFamily: 'monospace' },
  '.cm-gutters': { background: 'var(--bg-secondary)', color: 'var(--text-muted)', border: 'none' },
  '.cm-activeLine, .cm-activeLineGutter': { background: 'transparent' },
  '.cm-placeholder': { color: 'var(--text-muted)' },
  '.cm-tooltip': { background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' },
}, { dark: true });

// An empty field isn't an error: the caller takes it as no value.
const lintJson = (view) => (view.state.doc.length ? jsonParseLinter()(view) : []);

// The HMI is dark: One Dark's token colours, not CodeMirror's light default.
const extensions = [
  json(),
  linter(lintJson, { delay: 300 }),
  lintGutter(),
  theme,
  syntaxHighlighting(oneDarkHighlightStyle),
  EditorView.lineWrapping,
];

const setup = { lineNumbers: false, foldGutter: true, highlightActiveLine: false, highlightActiveLineGutter: false, autocompletion: false };

/**
 * @param {string} id - The wrapper's id
 * @param {string} value - The JSON text
 * @param {(text: string) => void} onChange - Called with the new text
 * @param {string} [placeholder]
 * @param {string} [label] - The editor's accessible name
 * @param {Object} [style] - The wrapper's style
 */
function JsonEditor({ id, value, onChange, placeholder, label, style }) {
  // The name goes on the editable element, where a screen reader is.
  const withLabel = useMemo(
    () => (label ? [...extensions, EditorView.contentAttributes.of({ 'aria-label': label })] : extensions),
    [label],
  );
  return (
    <CodeMirror
      id={id}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      theme="none"
      basicSetup={setup}
      extensions={withLabel}
      minHeight="48px"
      maxHeight="240px"
      style={style}
    />
  );
}

export default JsonEditor;
