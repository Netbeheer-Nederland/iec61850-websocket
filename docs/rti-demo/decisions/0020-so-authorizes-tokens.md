<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 20. The SO checks what a token allows, not only that it's genuine

- Status: proposed
- Date: 2026-10-07

## Context

With OAuth on, an FSP connects to the SO's WebSocket at `/<cp>` (for example `/cp1`) with a bearer token. The SO
(`ws61850.endpoint.PassiveEndpoint`) checks the token's signature against the IDP's published keys (JWKS), its issuer,
its expiry and not-before, and its audience. It closes the connection when the token expires. That is
**authentication**: the token is genuine. There is no **authorization**:

- The audience the SO expects is fixed to `account`. `account` is Keycloak's audience for its own account console, and
  under Keycloak's defaults it ends up in every client's token. Any client of the realm passes.
- Nothing ties a token to the connection point it opens. A valid token for one FSP can connect as any CP, and take
  another FSP's place.
- Scopes, roles and the client identity (`azp`, `sub`) are read but not used.

A test with forged tokens and a local key (2026-10-07) confirmed this: a token issued to another client of the same
realm was accepted.

Smaller problems found at the same time:

- The validator takes the signing algorithm from the token's own (unverified) header. `alg: none` and an HS256 token
  signed with the public key are refused, but with an exception that the SO turns into `503`, not `401`.
- The SO registers a client entry for the requested CP **before** it checks the token, so rejected attempts still add
  entries.
- A `refreshToken` during a session is checked by an older function (`ws61850.security.oauth`). It also uses
  `account` and the header's algorithm, and fetches the JWKS synchronously on every refresh. It gets the IDP settings
  only from the constructor, so after OAuth is turned on by reconfiguration (how the demo's BFF does it), a refresh
  can't be validated.

## Decision

1. **A dedicated audience.** The SO accepts only tokens whose `aud` contains its own audience, default `rti-so`. The
   IDP adds it to the tokens of the clients that may connect to the SO (Keycloak: an audience mapper). Configurable:
   `PassiveEndpoint(token_audience=...)`; in the demo SO, `SO_OAUTH_AUDIENCE`.
2. **Connection points come from the token.** The token carries the CPs its client may use, as a list claim, default
   name `rti_cps` (Keycloak: a hard-coded claim mapper per client). The SO accepts a connection to `/<cp>` only when
   `<cp>` is in that list, and answers `403` otherwise. The IDP stays the single place where access is granted; the
   SO keeps no list of its own (as in [0007](0007-bff-reapplies-security-config.md), it holds no security state).
   Configurable: `PassiveEndpoint(cp_claim=...)`; in the demo SO, `SO_OAUTH_CP_CLAIM`. An empty claim name turns the
   CP check off, with a warning in the log, for IDPs that can't add such a claim.
3. **One validator for connect and refresh.** A `refreshToken` is checked by the same validator and the same CP rule
   as the connection that started the session, with the settings that are current after a reconfiguration. A refresh
   that fails is refused, as now, and the session ends when the old token expires.
4. **Hardening.**
   - Only asymmetric algorithms are accepted: RS256/384/512, PS256/384/512 and ES256/384/512. The header can choose
     among these, but `none` and HMAC never pass.
   - Every malformed or unverifiable token gives `401`. `503` is kept for a JWKS that can't be fetched.
   - The CP's client entry is registered only after the token passes.
5. **The demo realm** gives each FSP its own client: `rti-fsp01` may use `cp1` and `rti-fsp02` may use `cp2`. The
   existing `ws-client` keeps working for the test scenarios, for `cp1`. The FT23 provisioning script adds the same two
   mappers to every client it creates, for its own CP.

## Consequences

- A token for another client, or for another CP, is refused. A stolen FSP token can only be used as that FSP.
- **Breaking for existing setups:** tokens without `rti-so` in `aud`, or without the `rti_cps` claim, are refused
  after the upgrade. The realm in `scripts/keycloak/data` gets the mappers. A running Keycloak only imports the realm
  when it is created, so it has to be recreated. A third-party IDP needs the same two mappers, or the SO setting
  `SO_OAUTH_AUDIENCE` / `SO_OAUTH_CP_CLAIM` changed.
- The FSPs need their own client IDs and secrets in the HMI's OAuth settings (`rti-fsp01`, `rti-fsp02`).
- `ws61850.security.oauth.check_token_validity_and_expiry` is removed. Token acquisition (`get_access_token`) stays.
- Scopes and roles are still not used. If a CP ever needs finer rights, such as read-only access, that is a new
  decision.

## In the code

- `ws61850.security.oauth2.validator` (`JwtValidator`, `TokenClaims`)
- `ws61850.endpoint.passive_endpoint` (`process_request`, `reconfigure_oauth`), `ws61850.endpoint.association_handler`
- `examples/rti-demo/modules/so/src/so/bff_endpoint.py` (`/reconfig-oauth`)
- `scripts/keycloak/data/realm-test.json`, `tests/performance/FT23/client_credentials/utils/keycloak_client_provisioner.py`
