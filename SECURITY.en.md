# Security Policy

[简体中文](SECURITY.md)

## Supported Versions

Only the latest code on the default branch and the latest published package are supported. AKBridge
does not store user credentials; inject credentials through environment variables or MCP client
configuration.

Streamable HTTP enables Host/Origin validation and DNS rebinding protection by default; public
deployments still require TLS and access controls. Set `AKBRIDGE_HTTP_BEARER_TOKEN` to enable bearer
authentication, and use `AKBRIDGE_HTTP_ALLOWED_HOSTS` / `AKBRIDGE_HTTP_ALLOWED_ORIGINS` to configure
allowed hosts and cross-origin request origins. Do not put tokens in shell history, source code, or
public configuration.

Legacy SSE does not include these Host/Origin or bearer-token protections. Use it only on trusted
local networks or behind an authenticated reverse proxy.

## Reporting a Vulnerability

Do not disclose exploitable security issues in public Issues. Contact the maintainers through the
code-hosting platform's private security-advisory channel, including reproduction steps, affected
versions, and a minimal test case.

Remove tokens, cookies, passwords, API keys, and real user data from reports. After confirmation,
maintainers will coordinate the fix, testing, and public disclosure schedule.
