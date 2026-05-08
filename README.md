# x402 Financial MCP Server

An MCP (Model Context Protocol) server + REST wrapper that exposes the x402 Financial Data API as callable tools for AI agents.

## What it does

AI agents call tools → server handles x402 payment with USDC on Base → returns result.

## Quick Start

```bash
cd /home/banned/.openclaw/workspace/x402-mcp-server
pip install mcp requests

# MCP Server mode (for AI agents that support MCP)
python mcp_server.py

# REST Server mode (for any HTTP client)
python rest_server.py --port 8080
```

## REST API

```bash
# List all tools
curl http://localhost:8080/tools

# Call a FREE tool
curl "http://localhost:8080/call/merchant_clean?description=NTUC%20FINANCE"

# Call a PAID tool (returns 402 with payment info if no wallet)
curl -X POST http://localhost:8080/call/sgx_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "DBS"}'
```

## Tools

- **47 paid tools** (SGX stocks, CPF calculators, tax, property, etc.)
- **4 free tools** (merchant name cleaning, Singapore holidays, compound calculator)
- **Full x402 payment protocol** — agents pay with USDC on Base automatically

## MCP Protocol

Works with any MCP-compatible client (Claude Desktop, OpenClaw agents, etc.)

```python
from mcp.server import Server
from mcp.types import Tool

server = Server("x402-financial-api")
# Exposes 51 financial tools
```

## Repository

https://github.com/nebmil569/x402-mcp-server
