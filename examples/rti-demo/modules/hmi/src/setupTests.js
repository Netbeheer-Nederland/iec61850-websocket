import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// waitFor / findBy* give up after 1 s by default. The full suite runs its
// files in parallel, each in its own jsdom, and on a loaded machine a page
// test's fetch -> state -> render chain can take longer than that - tests
// then failed now and again (ACSIServer's OAuth and WS-field tests). A
// passing wait still returns as soon as its condition holds, so this only
// changes how long a genuinely failing one takes to report.
configure({ asyncUtilTimeout: 5000 });
