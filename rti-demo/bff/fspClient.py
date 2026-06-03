import logging
import requests

logger = logging.getLogger(__name__)

class FspClient:
    """Typed client for talking to the FSP (IEC61850 server) container."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def _get(self, path: str, **kwargs):
        return requests.get(f"{self.base_url}{path}", timeout=5, **kwargs)

    def _post(self, path: str, json=None, **kwargs):
        return requests.post(f"{self.base_url}{path}", json=json, timeout=5, **kwargs)

    def status(self) -> dict:
        r = self._get('/api/iec61850server/status')
        r.raise_for_status()
        return r.json()

    def model(self) -> dict:
        r = self._get('/api/iec61850server/model')
        r.raise_for_status()
        return r.json()

    def read_value(self, obj_ref: str, fc: str = None) -> dict:
        payload = {'objRef': obj_ref}
        if fc is not None:
            payload['fc'] = fc
        r = self._post('/api/iec61850server/readvalue', json=payload)
        r.raise_for_status()
        return r.json()

    def write_value(self, obj_ref: str, value, fc: str = None, da_type = None) -> dict:
        payload = {'objRef': obj_ref, 'value': value}
        if fc is not None:
            payload['fc'] = fc
        if da_type is not None:
            payload['dataType'] = da_type

        r = self._post('/api/iec61850server/writevalue', json=payload)
        r.raise_for_status()
        return r.json()

    def connections(self) -> dict:
        r = self._get('/api/iec61850server/connections')
        r.raise_for_status()
        return r.json()

    def update_model(self, new_model) -> dict:
        r = self._post(f'/api/iec61850server/update-iedmodel', json={'modelPy': new_model})
        r.raise_for_status()
        return r.json()

    def start_acsi_server(self, host, port, mode, cp) -> dict:
        payload = {}
        if host is not None:
            payload['host'] = host
        if port is not None:
            payload['port'] = port
        if mode is not None:
            payload['mode'] = mode
        if cp is not None:
            payload['cp'] = cp

        r = self._post(f'/api/iec61850server/start', json=payload)
        r.raise_for_status()
        return r.json()

    def stop_acsi_server(self) -> dict:
        r = self._post(f'/api/iec61850server/stop')
        r.raise_for_status()
        return r.json()

    def properties(self) -> dict:
        r = self._get('/api/iec61850server/properties')
        r.raise_for_status()
        return r.json()

    def actions(self) -> dict:
        r = self._get('/api/iec61850server/actions')
        r.raise_for_status()
        return r.json()

    def clear_actions(self) -> dict:
        r = self._post('/api/iec61850server/actions/clear')
        r.raise_for_status()
        return r.json()

    def protocol_messages(self) -> dict:
        r = self._get('/api/iec61850server/messages')
        r.raise_for_status()
        return r.json()

    def clear_protocol_messages(self) -> dict:
        r = self._post('/api/iec61850server/messages/clear')
        r.raise_for_status()
        return r.json()
