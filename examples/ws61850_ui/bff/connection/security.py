import os
import ssl
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ws61850.security.oauth import get_access_token
from ws61850.security.tls import TLSConfiguration


@dataclass
class SecurityContext:
    tls_config: TLSConfiguration | None = None
    oauth_enable: bool | None = None
    certificate_url: str | None = None
    token_issuer: str | None = None
    kc_cert: str | None = None
    access_token: str | None = None
    token_refresh_enabled: bool = False
    token_request_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    temp_files: list[str] = field(default_factory=list)

    def cleanup(self) -> None:
        for path in self.temp_files:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        self.temp_files.clear()


class SecurityFactory:
    async def build(self, profile_security: dict[str, Any] | None, *, transport_role: str) -> SecurityContext:
        if not profile_security:
            return SecurityContext()

        context = SecurityContext(
            oauth_enable=profile_security.get("enableOAuth"),
            token_refresh_enabled=bool(profile_security.get("enableTokenRefresh")),
            token_request_url=profile_security.get("oauthUrl"),
            client_id=profile_security.get("oauthClientId"),
            client_secret=profile_security.get("oauthClientSecret"),
        )

        if profile_security.get("enableTLS"):
            if transport_role == "ws_client":
                cert_path = self._write_temp_file(context, "ws_server_ca_", ".pem", profile_security.get("tlsCACert", ""))
                context.tls_config = TLSConfiguration(is_ws_server=False, cert_path=cert_path, key_path=None)
            else:
                cert_path = self._write_temp_file(context, "ws_server_cert_", ".pem", profile_security.get("certificate", ""))
                key_path = self._write_temp_file(context, "ws_server_key_", ".pem", profile_security.get("privateKey", ""))
                context.tls_config = TLSConfiguration(is_ws_server=True, cert_path=cert_path, key_path=key_path)
                if profile_security.get("tlsVersion") == "1.2":
                    context.tls_config.set_min_and_max_version(
                        min_version=ssl.TLSVersion.TLSv1_2,
                        max_version=ssl.TLSVersion.TLSv1_2,
                    )
                else:
                    context.tls_config.set_min_and_max_version(
                        min_version=ssl.TLSVersion.TLSv1_3,
                        max_version=ssl.TLSVersion.TLSv1_3,
                    )
                context.tls_config.ssl_context.keylog_filename = os.path.join(tempfile.gettempdir(), "ws61850_gui_tlskeys.log")

        if profile_security.get("enableOAuth"):
            context.kc_cert = self._write_temp_file(context, "kc_root_ca_", ".pem", profile_security.get("oauthCACert", ""))
            if transport_role == "ws_client":
                context.access_token = await get_access_token(
                    context.token_request_url,
                    context.client_id,
                    context.client_secret,
                    context.kc_cert,
                    None,
                )
            else:
                context.certificate_url = profile_security.get("oauthCertEndpoint")
                context.token_issuer = profile_security.get("oauthIssuer")

        return context

    def _write_temp_file(self, context: SecurityContext, prefix: str, suffix: str, content: str) -> str | None:
        if not content:
            return None
        with tempfile.NamedTemporaryFile("w", delete=False, prefix=prefix, suffix=suffix) as handle:
            handle.write(content)
            path = handle.name
        context.temp_files.append(path)
        return path
