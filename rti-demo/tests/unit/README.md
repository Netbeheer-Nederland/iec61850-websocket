# Unit Tests

This directory contains organized unit tests for the RTI 2.0 demo applications.

## Structure

```
tests/unit/
├── fsp/                              # FSP ACSI-Server_WebsocketActive tests
│   ├── __init__.py
│   └── test_bff_endpoint.py          # Server API tests
├── so/                               # SO ACSI-Client_WebsocketPassive tests
│   ├── __init__.py
│   └── test_bff_endpoint.py          # Client API tests
└── README.md                         # This file
```

## Running Tests

### All Tests

```bash
cd rti-demo
pytest tests/unit -v
```

### FSP ACSI-Server_WebsocketActive Tests Only

```bash
pytest tests/unit/fsp -v
```

### SO ACSI-Client_WebsocketPassive Tests Only

```bash
pytest tests/unit/so -v
```

### Specific Test

```bash
pytest tests/unit/fsp/test_bff_endpoint.py::test_status_returns_server_status -v
```

### With Coverage Report

```bash
pytest tests/unit --cov=rti_demo --cov-report=html
```

## Test Files

### FSP ACSI-Server_WebsocketActive Tests (`fsp/test_bff_endpoint.py`)

Tests for the FSP (server) BFF endpoint routes:
- Status endpoint
- Start/stop server
- Read/write values
- Model update
- Connection management
- HTTP method validation
- Error handling

### SO ACSI-Client_WebsocketPassive Tests (`so/test_bff_endpoint.py`)

Tests for the SO (client) BFF endpoint routes:
- Status endpoint
- Connection management (connect/disconnect)
- Read/write values
- Action/message logging
- HTTP method validation
- Error handling
- ACSI client integration

## Prerequisites

Install test dependencies:

```bash
pip install pytest pytest-cov flask
```

## CI/CD Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  run: pytest tests/unit -v --cov --cov-report=xml
```

## Best Practices

1. **Test Organization**: Tests are organized by module (fsp, so) for clarity
2. **Fixtures**: Common fixtures are defined at the top of each test file
3. **Naming**: Test functions and classes follow `test_<feature>_<scenario>` pattern
4. **Mocking**: External dependencies are mocked to isolate units under test
5. **Coverage**: Aim for high coverage of critical paths and error cases
