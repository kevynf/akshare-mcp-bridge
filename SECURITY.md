# 安全策略

[English](SECURITY.en.md)

## 支持版本

仅支持默认分支上的最新代码和最新发布包。AKBridge 不存储用户凭据；凭据应通过环境变量或 MCP 客户端配置注入。

Streamable HTTP 默认启用 Host/Origin 校验和 DNS rebinding 防护；公网部署仍必须配置 TLS 与访问控制。可通过 `AKBRIDGE_HTTP_BEARER_TOKEN` 启用 bearer-token 验证，并用 `AKBRIDGE_HTTP_ALLOWED_HOSTS` / `AKBRIDGE_HTTP_ALLOWED_ORIGINS` 配置允许的 Host 与跨域来源。不要把 token 写入 shell 历史、源码或公开配置。

旧版 SSE transport 不包含这些 Host/Origin 与 bearer-token 防护；仅在可信本机环境使用，或放在已完成身份验证的反向代理之后。

## 报告漏洞

请不要在公开 Issue 中披露可利用的安全问题。请通过代码托管平台的私密安全报告渠道联系维护者，并提供复现步骤、受影响版本和最小化测试样例。

报告中请移除 Token、Cookie、密码、API Key 和真实用户数据。维护者会在确认后协调修复、测试和公开披露时间。
