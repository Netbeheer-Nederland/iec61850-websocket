import logging
import requests

logger = logging.getLogger(__name__)

class SOClient:
    """Typed client for talking to the SO (IEC61850 client) container."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def _get(self, path: str, **kwargs):
        return requests.get(f"{self.base_url}{path}", timeout=5, **kwargs)

    def _post(self, path: str, json=None, **kwargs):
        return requests.post(f"{self.base_url}{path}", json=json, timeout=5, **kwargs)

    def status(self) -> dict:
        r = self._get('/api/iec61850client/status')
        r.raise_for_status()
        return r.json()

    def connections(self) -> dict:
        r = self._get('/api/iec61850client/connections')
        r.raise_for_status()
        return r.json()

    def connect(self, host: str, port: int, cp: str) -> dict:
        payload = {}
        if host:
            payload["host"] = host
        if port:
            payload["port"] = port
        if cp:
            payload["cp"] = cp

        r = self._post('/api/iec61850client/connect', json=payload)
        r.raise_for_status()
        return r.json()

    def disconnect(self) -> dict:
        r = self._post('/api/iec61850client/disconnect')
        r.raise_for_status()
        return r.json()

    def properties(self) -> dict:
        r = self._get('/api/iec61850client/properties')
        r.raise_for_status()
        return r.json()

    def model(self) -> dict:
        r = self._get('/api/iec61850client/model/tree')
        r.raise_for_status()
        return r.json()

    def actions(self) -> dict:
        r = self._get('/api/iec61850client/actions')
        r.raise_for_status()
        return r.json()

    def clear_actions(self) -> dict:
        r = self._post('/api/iec61850client/actions/clear')
        r.raise_for_status()
        return r.json()

    def protocol_messages(self) -> dict:
        r = self._get('/api/iec61850client/messages')
        r.raise_for_status()
        return r.json()

    def clear_protocol_messages(self) -> dict:
        r = self._post('/api/iec61850client/messages/clear')
        r.raise_for_status()
        return r.json()


    def read_value(self, obj_ref: str, fc: str = None) -> dict:
        payload = {'objRef': obj_ref}
        if fc is not None:
            payload['fc'] = fc
        r = self._post('/api/iec61850client/readvalue', json=payload)
        r.raise_for_status()
        return r.json()

    def write_value(self, obj_ref: str, value, fc: str = None, da_type = None) -> dict:
        payload = {'objRef': obj_ref, 'value': value}
        if fc is not None:
            payload['fc'] = fc
        if da_type is not None:
            payload['value_type'] = da_type

        r = self._post('/api/iec61850client/writevalue', json=payload)
        r.raise_for_status()
        return r.json()