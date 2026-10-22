# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""A plugin service for the tests: implements the plugin API (openapi.yaml)
in memory, and records what the host sends it."""

from __future__ import annotations

from typing import Any

import httpx2 as httpx
from fastapi import FastAPI, Request, Response


class FakePlugin:
    def __init__(
        self,
        name: str = "demo",
        *,
        version: str = "1.0.0",
        api: int = 2,
        claims: list[str] | None = None,
        answer: dict | None = None,
        routes: bool = True,
        attached: Any = None,
    ):
        self.description: dict[str, Any] = {
            "name": name,
            "version": version,
            "api": api,
            "claims": list(claims or []),
        }
        if routes:
            self.description["routes"] = "routes"
        self.answer = answer
        # GET /plugin/attached answers this; None: 404, the route isn't there.
        self.attached = attached
        self.calls: list[tuple[str, Any]] = []
        self.up = True
        self.app = self._app()

    def events(self) -> list[dict]:
        return [body["event"] for path, body in self.calls if path == "events"]

    def _app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/plugin")
        def describe():
            return self.description

        @app.get("/plugin/attached")
        def attached():
            self.calls.append(("attached", None))
            if self.attached is None:
                return Response(status_code=404)
            return self.attached

        @app.post("/plugin/{action}")
        async def act(action: str, request: Request):
            body = await request.json()
            self.calls.append((action, body))
            if action == "control":
                if self.answer is None:
                    return Response(status_code=204)
                return self.answer
            return {"ok": True}

        @app.get("/plugin/routes/hello")
        def hello(who: str = "world"):
            return {"hello": who}

        @app.post("/plugin/routes/echo")
        async def echo(request: Request):
            return {"body": await request.json()}

        return app

    def client(self) -> httpx.AsyncClient:
        """A client that reaches this plugin at http://plugin.test, while it is up."""
        if not self.up:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(_refuse), base_url="http://plugin.test"
            )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://plugin.test"
        )


URL = "http://plugin.test/plugin"


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)
