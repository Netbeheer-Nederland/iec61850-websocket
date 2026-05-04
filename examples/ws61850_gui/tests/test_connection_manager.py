import asyncio
import time
import unittest

import gui.connection_manager as cm
from gui.state import RuntimeState


class FakeWebSocket:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeWebSocketInfo:
    def __init__(self, websocket: FakeWebSocket, cp: str) -> None:
        self.websocket = websocket
        self.cp = cp
        self.invoke_id = 1
        self.associate_id = "assoc-1"


class FakeClient:
    def __init__(self, cp: str) -> None:
        self.cp = cp
        self.is_connected = False
        self.ready_event = asyncio.Event()
        self.send_msg_callback = None
        self.disconnect_event = asyncio.Event()


class FakeServer:
    def __init__(self, *args) -> None:
        if len(args) == 1:
            self.ied_model = None
            self.cp = args[0]
        elif len(args) == 2:
            self.ied_model = args[0]
            self.cp = args[1]
        else:
            raise TypeError("FakeServer expects cp or (ied_model, cp)")
        self.ready_event = asyncio.Event()
        self.send_msg_callback = None
        self.recv_msg_callback = None


class FakeEndpoint:
    def __init__(self, is_direct=False, tls_config=None, oauth_enable=None, cert_endpoint=None, token_issuer=None, kc_cert=None):
        self.is_direct = is_direct
        self.client_list = []
        self.server_list = []
        self.websocket_info_list = []
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.server = None
        self._passive_running = False

    def add_iec61850_client(self, client: FakeClient) -> None:
        self.client_list.append(client)

    def add_iec61850_server(self, server: FakeServer) -> None:
        self.server_list.append(server)

    async def start(self, mode, hostname, port, cp=None, access_token=None, protocol=None, *args):
        if mode == "passive":
            self.server = object()
            self._passive_running = True
            while self._passive_running:
                await asyncio.sleep(0.01)
            return

        websocket = FakeWebSocket()
        ws_info = FakeWebSocketInfo(websocket, cp)
        self.websocket_info_list = [ws_info]
        if self.client_list:
            client = self.client_list[0]
            client.is_connected = True
            client.ready_event.set()
        if self.server_list:
            self.server_list[0].ready_event.set()
        while not websocket.closed:
            await asyncio.sleep(0.01)
        if self.client_list:
            self.client_list[0].is_connected = False

    async def stop_passive(self) -> None:
        self._passive_running = False

    def get_websocket_info(self, client: FakeClient):
        for ws_info in self.websocket_info_list:
            if ws_info.cp == client.cp:
                return ws_info
        return None


class FailingEndpoint(FakeEndpoint):
    async def start(self, mode, hostname, port, cp=None, access_token=None, protocol=None, *args):
        raise RuntimeError("boom")


def wait_for(predicate, timeout=2.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class ConnectionManagerTests(unittest.TestCase):
    def test_active_connection_reaches_connected_and_disconnects_cleanly(self) -> None:
        manager = cm.ConnectionManager(RuntimeState(), endpoint_cls=FakeEndpoint, client_cls=FakeClient)
        manager.start_connection("localhost", 8765, "cp1", is_direct=True, mode="active", security=None)

        self.assertTrue(wait_for(lambda: manager.status()["state"] == "connected"))
        status = manager.status()
        self.assertEqual(status["state"], "connected")
        self.assertEqual(status["detail"]["cp"], "cp1")

        self.assertEqual(manager.disconnect(), "disconnected")
        self.assertTrue(wait_for(lambda: manager.status()["state"] == "not-connected"))

        actions = manager.snapshot_actions()
        self.assertTrue(any(action["message"].startswith("connect ok") for action in actions))
        self.assertTrue(any(action["message"] == "Disconnected from server" for action in actions))

    def test_passive_connection_stays_listening_until_disconnect(self) -> None:
        manager = cm.ConnectionManager(RuntimeState(), endpoint_cls=FakeEndpoint, client_cls=FakeClient)
        manager.start_connection("0.0.0.0", 8765, "cp1", is_direct=False, mode="passive", security=None)

        self.assertTrue(wait_for(lambda: manager.status()["state"] == "listening"))
        self.assertTrue(wait_for(lambda: any(action["message"].startswith("connect ok") for action in manager.snapshot_actions())))
        self.assertIsNotNone(manager.state.endpoint)
        self.assertIsNotNone(manager.state.endpoint_task)

        self.assertEqual(manager.disconnect(), "disconnected")
        self.assertTrue(wait_for(lambda: manager.status()["state"] == "not-connected"))

        actions = manager.snapshot_actions()
        self.assertTrue(any(action["message"].startswith("connect ok") for action in actions))
        self.assertTrue(any(action["message"] == "Passive server stopped" for action in actions))

    def test_startup_failure_marks_connect_action_as_error(self) -> None:
        manager = cm.ConnectionManager(RuntimeState(), endpoint_cls=FailingEndpoint, client_cls=FakeClient)
        manager.start_connection("localhost", 8765, "cp1", is_direct=True, mode="active", security=None)

        self.assertTrue(wait_for(lambda: manager.status()["state"] == "not-connected"))
        self.assertTrue(wait_for(lambda: manager.snapshot_actions() and manager.snapshot_actions()[-1]["status"] == "error"))
        actions = manager.snapshot_actions()
        self.assertEqual(actions[-1]["status"], "error")
        self.assertIn("connect error: boom", actions[-1]["message"])
        self.assertIsNone(manager.state.endpoint)
        self.assertIsNone(manager.state.client)

    def test_ws_client_with_iec_server_uses_server_binding(self) -> None:
        manager = cm.ConnectionManager(
            RuntimeState(),
            endpoint_cls=FakeEndpoint,
            client_cls=FakeClient,
            server_factory=FakeServer,
        )
        manager.start_connection(
            "localhost",
            8765,
            "cp1",
            is_direct=False,
            mode="active",
            security=None,
            application_role="iec_server",
        )

        self.assertTrue(wait_for(lambda: manager.status(target="client-server")["state"] in {"connecting", "connected"}))
        client_server_state = manager.states["client-server"]
        self.assertIsNone(client_server_state.client)
        self.assertIsNotNone(client_server_state.server)
        self.assertEqual(client_server_state.application_role, "iec_server")

        self.assertEqual(manager.disconnect(target="client-server"), "disconnected")
        self.assertTrue(wait_for(lambda: manager.status(target="client-server")["state"] == "not-connected"))

    def test_ws_client_with_iec_server_uses_default_server_factory(self) -> None:
        original_server_cls = cm.IEC61850Server
        cm.IEC61850Server = FakeServer
        try:
            manager = cm.ConnectionManager(
                RuntimeState(),
                endpoint_cls=FakeEndpoint,
                client_cls=FakeClient,
            )
            manager.start_connection(
                "localhost",
                8765,
                "cp1",
                is_direct=False,
                mode="active",
                security=None,
                application_role="iec_server",
            )

            self.assertTrue(
                wait_for(lambda: manager.status(target="client-server")["state"] in {"connecting", "connected"})
            )
            client_server_state = manager.states["client-server"]
            self.assertIsNone(client_server_state.client)
            self.assertIsNotNone(client_server_state.server)
            self.assertEqual(client_server_state.server.cp, "cp1")
            self.assertIsNotNone(client_server_state.server.ied_model)
            self.assertEqual(client_server_state.application_role, "iec_server")

            self.assertEqual(manager.disconnect(target="client-server"), "disconnected")
            self.assertTrue(wait_for(lambda: manager.status(target="client-server")["state"] == "not-connected"))
        finally:
            cm.IEC61850Server = original_server_cls


if __name__ == "__main__":
    unittest.main()
