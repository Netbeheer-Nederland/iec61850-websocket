import logging
import requests
import time

logger = logging.getLogger(__name__)

class SOClient:
    """Typed client for talking to the SO (IEC61850 client) container."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def _get(self, path: str, **kwargs):
        return requests.get(f"{self.base_url}{path}", timeout=10, **kwargs)

    def _post(self, path: str, json=None, **kwargs):
        return requests.post(f"{self.base_url}{path}", json=json, timeout=10, **kwargs)

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
        """Request model with longer timeout and simple retries because building the model can take longer.

        Strategy:
        - Query the SO internal diagnostic endpoint first; if it reports 'building' or 'error', return that status immediately.
        - Otherwise, attempt to GET the model tree with a longer timeout and a few retries on read timeouts.
        """
        status_url = f"{self.base_url}/internal/model/status"
        try:
            sr = requests.get(status_url, timeout=2)
            if sr.ok:
                payload = sr.json()
                if isinstance(payload, dict) and payload.get('ok'):
                    model_status = payload.get('model_status')
                    progress = payload.get('model_progress')
                    model_error = payload.get('model_error')
                    if model_status == 'building':
                        logger.info("SOClient.model: SO reports building via diagnostic endpoint")
                        return {'status': 'building', 'progress': progress}
                    if model_status == 'error':
                        logger.warning(f"SOClient.model: SO reports error via diagnostic endpoint: {model_error}")
                        return {'status': 'error', 'error': model_error}
        except Exception:
            # Diagnostic probe failed — continue to attempt the model GET
            logger.debug("SOClient.model: diagnostic probe failed or not available; will attempt model GET")

        # Fall back to direct GET with retries
        attempts = 3
        timeout = 30
        path = '/api/iec61850client/model/tree'
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                r = requests.get(url, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except requests.exceptions.ReadTimeout as e:
                logger.warning(f"SOClient.model read timeout attempt {attempt}/{attempts}: {e}")
                last_exc = e
                # On read timeout, re-check the diagnostic endpoint once quickly
                try:
                    sr = requests.get(status_url, timeout=2)
                    if sr.ok:
                        payload = sr.json()
                        if isinstance(payload, dict) and payload.get('ok'):
                            model_status = payload.get('model_status')
                            progress = payload.get('model_progress')
                            model_error = payload.get('model_error')
                            if model_status == 'building':
                                return {'status': 'building', 'progress': progress}
                            if model_status == 'error':
                                return {'status': 'error', 'error': model_error}
                except Exception:
                    pass
                if attempt < attempts:
                    time.sleep(1)
                    continue
                # final attempt exhausted: return a building envelope rather than raising an exception
                logger.warning("SOClient.model: all read-timeout attempts exhausted; returning building envelope")
                return {'status': 'building', 'progress': None, 'note': 'read-timeout'}
            except requests.exceptions.RequestException:
                # propagate other request errors directly
                raise

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