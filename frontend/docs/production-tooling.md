# Frontend production tooling

## Decision

Replace Create React App's retired build pipeline with Vite 7, while retaining React 18, the existing JSX-in-JavaScript source files and Jest component tests. Keeping CRA only as a development dependency would leave its outdated build dependency chain in the project. Vite emits the existing `build/` directory and hashed assets under `static/`, so the nginx runtime image and its cache rules keep the same interface.

Jest 30 uses Babel's current maintained JSX and JavaScript transforms. Tests run in jsdom with Node's text encoder/decoder, required by React Router. `backendOrigin` accepts an optional location snapshot and otherwise reads the browser location, letting origin tests exercise LAN, IPv6 and HTTPS behavior without redefining jsdom's immutable location object. ESLint is separate from the bundler and retains the Hooks checks plus accessibility checks that understand the project's custom form controls. Intentional autofocus on login and modal inputs remains allowed, matching the existing workflow and previous lint policy.

React Router 7.18.3 addresses the router advisories affecting all installed version 6 releases. The app uses declarative routing, absolute navigation paths and module-level lazy components. It does not use data-router fetchers, loaders or SSR hydration. Version 7 continues to support the `react-router-dom` compatibility exports, avoiding unrelated application changes.

## Commands and deployment contract

- Node 24 is used by both frontend Docker build images; the tooling requires Node 22.12 or newer.
- `npm ci` installs the locked dependencies and copies local scanner WASM assets.
- `npm run build` creates production static files in `build/`, targeting Chrome 80, Firefox 78 and Safari 13.1 syntax. Source maps are disabled.
- `npm test -- --runInBand` runs Jest once. Target individual suites with `--runTestsByPath`.
- `npm run lint` checks application and test sources separately from the build.
- `npm audit` checks all dependencies; `npm audit --omit=dev` checks the runtime dependency graph.
- `REACT_APP_BACKEND_URL` remains an optional build setting. Empty selects the current origin through the existing API client. No broad environment object or server secrets are inserted into browser code.

The production container includes nginx and generated static files only. Vite, Jest, Babel, ESLint, Node dependencies and their install scripts are not present in the served runtime image. Vite's development server is not a production server.

## Verification and maintenance

The replacement production build completed successfully in 3.20 seconds on a repeat run. Representative suites covering API origins, clinical workflows, printing, admin and scanner workers passed 33 tests; Layout's 3 tests also passed before the API test adaptation. Both complete and runtime-only npm audits reported zero known advisories on 2026-09-05. The lockfile is the reproducible version record; future advisory status must be checked again before release. Zero reported advisories does not prove absence of vulnerabilities.

Vite's build emits a benign warning when the client-side router's `use client` directive is ignored by Rollup; this SPA already runs entirely in the browser. No warning filter hides other build diagnostics. ESLint 9 is retained for the declared peer support of the React/accessibility plugins; move to the next ESLint major when those plugins support it. Deprecation notices in test-only transitive packages are not represented as zero risk, even though the current audit reports no advisories.

Sources: [Vite JavaScript transformation API](https://v7.vite.dev/guide/api-javascript#transformwithesbuild), [Vite build options](https://v7.vite.dev/config/build-options), [Jest configuration](https://jestjs.io/docs/30.0/configuration), [React Router upgrade documentation bundled with version 7](../node_modules/react-router/docs/upgrading/v6.md).
