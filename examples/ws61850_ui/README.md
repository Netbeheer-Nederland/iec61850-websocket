# RTI Demo UI Repository

This repository contains a React + TypeScript + Vite user interface for a Dutch RTI demo environment aligned to IEC
61850 concepts.

## Included working functions

- session connect/disconnect screen
- built-in `mock://demo` transport for local demos
- model snapshot loading and search
- live RTI event stream
- point detail page with recent history
- command flow for commandable points
- scenario runner
- diagnostics log with raw payload frames

## Run

```bash
cd ui
npm install
npm run dev
```

docker compose up rti-so --build

docker compose up bff --build

docker compose up --build