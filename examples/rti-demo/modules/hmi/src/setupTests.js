// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// waitFor / findBy* give up after 1 s by default. The full suite runs its
// files in parallel, each in its own jsdom, and on a loaded machine a page
// test's fetch -> state -> render chain can take longer than that - tests
// then failed now and again (ACSIServer's OAuth and WS-field tests). A
// passing wait still returns as soon as its condition holds, so this only
// changes how long a genuinely failing one takes to report.
configure({ asyncUtilTimeout: 5000 });

// CodeMirror (JsonEditor) measures text ranges for the cursor and scrolling;
// jsdom has no layout, so its Ranges lack these.
const noRect = { x: 0, y: 0, top: 0, left: 0, bottom: 0, right: 0, width: 0, height: 0, toJSON: () => ({}) };
Range.prototype.getBoundingClientRect ??= () => noRect;
Range.prototype.getClientRects ??= () => Object.assign([], { item: () => null });
