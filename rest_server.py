#!/usr/bin/env python3
"""
x402 Financial API — REST Wrapper Server
==========================================
A simple HTTP REST wrapper around the x402 Financial Data API.
Agents call JSON endpoints → server handles x402 payment → returns result.

Usage:
    python rest_server.py --port 8080

Endpoints:
    GET  /tools                    — list all available tools
    GET  /tools/free               — list free tools (no payment)
    POST /call/{tool_name}         — call a tool (add x-wallet-seed header for payment)
    GET  /health                   — health check

Examples:
    # Free tool
    curl http://localhost:8080/call/merchant_clean?description=NTUC%20FINANCE

    # Paid tool (needs wallet seed)
    curl -X POST http://localhost:8080/call/sgx_price \
      -H "Content-Type: application/json" \
      -H "x-wallet-seed: 0x..." \
      -d '{"symbol": "DBS"}'

    # List all tools
    curl http://localhost:8080/tools
"""

import os
import json
import base64
import argparse
from typing import Optional, List, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# x402 Financial API
import requests

API_BASE = "https://x402-financial-api.life.conway.tech"  # Primary (Conway)
# Backup: apinew-nine.vercel.app (Vercel — currently dead, token expired)
WALLET = "0x50F9D979b825670A9936D992F5db8AEd9497208A"
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NETWORK = "eip155:8453"

# Price map
PRICES = {
    "parse_pdf": 0.02, "extract_transactions": 0.01, "summary": 0.01,
    "spending_report": 0.01, "cash_flow_report": 0.01, "subscriptions_report": 0.01,
    "billing_calendar": 0.01, "tax_report": 0.02, "cpf_calculator": 0.02,
    "srs_calculator": 0.01, "hdb_resale": 0.01, "invoice": 0.02,
    "financial_insights": 0.01, "portfolio_summary": 0.05, "batch_clean_21_100": 0.005,
    "sgx_stock": 0.02, "sgx_portfolio": 0.03, "sgx_price": 0.005,
    "coe_prices": 0.01, "singapore_holidays": 0.005, "singapore_benefits": 0.01,
    "property_tax": 0.01, "condo_maintenance": 0.01, "absd_calculator": 0.01,
    "bto_affordability": 0.02, "car_loan_parf": 0.01, "financial_health_score": 0.01,
    "forex_convert": 0.005, "ssb_rates": 0.01, "ssb_calculator": 0.01,
    "utilities_estimate": 0.005, "electricity_compare": 0.01, "fire_calculator": 0.01,
    "school_nearby": 0.01, "school_nearby_secondary": 0.01, "hawker_nearby": 0.01,
    "goal_plan": 0.01, "retirement_community": 0.01, "mortgage_compare": 0.01,
    "business_lookup": 0.02, "salary_benchmark": 0.01, "rental_yield": 0.01,
    "tax_income": 0.02, "refinance": 0.015, "sgx_fundamentals": 0.02,
    "savings_optimize": 0.02, "cpf_topup": 0.01,
}

FREE_TOOLS = {
    "merchant_clean": "/merchant/clean",
    "merchant_batch_clean": "/merchant/batch-clean",
    "holidays_singapore": "/holidays/singapore",
    "singapore_compound": "/singapore/compound",
}

# Endpoint map
ENDPOINT_MAP = {
    "parse_pdf": "/parse/{bank}", "sgx_stock": "/sgx/stock",
    "sgx_portfolio": "/sgx/portfolio", "sgx_price": "/sgx/price",
    "sgx_fundamentals": "/sgx/fundamentals", "cpf_calculator": "/cpf/calculator",
    "tax_income": "/tax/income", "fire_calculator": "/fire/calculator",
    "bto_affordability": "/bto/topup-suggestions", "refinance": "/refinance",
    "school_nearby": "/school/nearby", "school_nearby_secondary": "/school/nearby-secondary",
    "business_lookup": "/business/lookup", "forex_convert": "/forex/convert",
    "utilities_estimate": "/utilities/estimate", "electricity_compare": "/electricity/compare",
    "property_tax": "/property/tax", "absd_calculator": "/absd/calculator",
    "financial_health_score": "/financial/health-score", "salary_benchmark": "/salary/benchmark",
    "rental_yield": "/rental/yield", "cpf_topup": "/cpf/topup",
    "goal_plan": "/goal/plan", "retirement_community": "/retirement/community",
    "mortgage_compare": "/mortgage/compare", "savings_optimize": "/savings/optimize",
    "summary": "/summary", "spending_report": "/report/spending",
    "cash_flow_report": "/report/cash-flow", "subscriptions_report": "/report/subscriptions",
    "billing_calendar": "/billing/calendar", "tax_report": "/report/tax",
    "hdb_resale": "/hdb/resale", "condo_maintenance": "/condo/maintenance",
    "car_loan_parf": "/car/loan-parf", "ssb_rates": "/ssb/rates",
    "ssb_calculator": "/ssb/calculator", "coe_prices": "/coe/prices",
    "singapore_benefits": "/singapore/benefits", "portfolio_summary": "/report/portfolio",
    "invoice": "/invoice/generate", "srs_calculator": "/srs/calculator",
    "financial_insights": "/financial/insights", "extract_transactions": "/extract/transactions",
    "merchant_clean": "/merchant/clean", "merchant_batch_clean": "/merchant/batch-clean",
    "holidays_singapore": "/holidays/singapore", "singapore_compound": "/singapore/compound",
    "hawker_nearby": "/hawker/nearby",
}


def get_all_tools() -> List[Dict[str, Any]]:
    tools = []
    for name, price in PRICES.items():
        tools.append({"name": name, "price_usd": price, "category": "paid", "endpoint": ENDPOINT_MAP.get(name, f"/{name}")})
    for name, path in FREE_TOOLS.items():
        tools.append({"name": name, "price_usd": 0, "category": "free", "endpoint": path})
    return tools


def call_tool(tool_name: str, arguments: Dict[str, Any], wallet_seed: Optional[str] = None) -> Dict[str, Any]:
    """Call an x402 tool, handling payment if wallet is provided"""
    
    # Check if free
    is_free = tool_name in FREE_TOOLS
    
    # Build URL
    if tool_name in ENDPOINT_MAP:
        endpoint = ENDPOINT_MAP[tool_name]
    else:
        endpoint = f"/{tool_name.replace('_', '/')}"
    
    url = f"{API_BASE}{endpoint}"
    
    # Special handling for parse_pdf
    if tool_name == "parse_pdf" and "bank" in arguments:
        bank = arguments.pop("bank")
        url = f"{API_BASE}/parse/{bank}"
    
    # Special handling for merchant_batch_clean (descriptions param)
    if tool_name == "merchant_batch_clean":
        url = f"{API_BASE}/merchant/batch-clean"
    
    headers = {"Accept": "application/json"}
    
    # Add payment headers for paid tools
    if not is_free:
        price = PRICES.get(tool_name, 0)
        headers.update({
            "Content-Type": "application/json",
            "x402-version": "2",
            "x402-network": NETWORK,
            "x402-asset": ASSET,
            "x402-price": str(int(price * 10**18)),
            "x402-recipient": WALLET,
        })
        
        # If wallet seed provided, add payment authorization
        if wallet_seed:
            # Sign payment token
            payload = json.dumps(arguments, sort_keys=True)
            token = _sign_payment(wallet_seed, payload, int(price * 10**18))
            headers["x402-token"] = token
    
    try:
        if is_free:
            # Free tools use GET with query params
            if arguments:
                url += "?" + urllib.parse.urlencode(arguments)
            response = requests.get(url, headers=headers, timeout=30)
        else:
            response = requests.post(url, json=arguments, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return {"success": True, "data": response.json(), "tool": tool_name, "price_usd": 0 if is_free else PRICES.get(tool_name, 0)}
        
        if response.status_code == 402:
            result = response.json()
            return {
                "success": False,
                "error": "payment_required",
                "message": "Payment required",
                "required_amount": result.get("error", {}).get("amount", str(int(PRICES.get(tool_name, 0) * 10**18))),
                "price_usd": PRICES.get(tool_name, 0),
                "network": NETWORK,
                "asset": ASSET,
                "recipient": WALLET,
                "tool": tool_name,
            }
        
        return {"success": False, "error": f"HTTP {response.status_code}", "message": response.text[:500]}
    
    except Exception as e:
        return {"success": False, "error": "request_failed", "message": str(e)}


def _sign_payment(wallet_seed: str, payload: str, price: int) -> str:
    """Sign x402 payment token"""
    import struct, hashlib, hmac
    import struct as s
    
    # Simple HMAC signing (in production, use proper ECDSA)
    to_sign = hashlib.sha256(hashlib.sha256(payload.encode()).digest() + s.pack('<Q', price)).digest()
    sig = hmac.new(bytes.fromhex(wallet_seed.strip('0x')), to_sign, hashlib.sha256).digest()
    import base64
    return base64.b64encode(sig).decode()


class Handler(BaseHTTPRequestHandler):
    
    def log_message(self, fmt, *args):
        pass  # Silent unless debug
    
    def send_json(self, data: Dict[str, Any], status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-wallet-seed, x402-token")
        self.end_headers()
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/health":
            self.send_json({
                "status": "healthy",
                "service": "x402 Financial REST Wrapper",
                "api_base": API_BASE,
                "tools_count": len(PRICES) + len(FREE_TOOLS),
                "paid_tools": len(PRICES),
                "free_tools": len(FREE_TOOLS),
            })
        
        elif parsed.path == "/tools":
            self.send_json({"tools": get_all_tools(), "count": len(get_all_tools())})
        
        elif parsed.path == "/tools/free":
            free_tools = [{"name": n, "endpoint": p} for n, p in FREE_TOOLS.items()]
            self.send_json({"tools": free_tools, "count": len(free_tools)})
        
        elif parsed.path.startswith("/call/"):
            tool_name = parsed.path[6:]  # strip /call/
            params = dict(urllib.parse.parse_qsl(parsed.query))
            wallet_seed = self.headers.get("x-wallet-seed")
            result = call_tool(tool_name, params, wallet_seed)
            self.send_json(result, 200 if result.get("success") else (402 if result.get("error") == "payment_required" else 400))
        
        else:
            self.send_json({"error": "not_found", "path": self.path}, 404)
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path.startswith("/call/"):
            tool_name = parsed.path[6:]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
            try:
                arguments = json.loads(body) if body else {}
            except:
                arguments = {}
            
            wallet_seed = self.headers.get("x-wallet-seed")
            result = call_tool(tool_name, arguments, wallet_seed)
            
            status = 200 if result.get("success") else (402 if result.get("error") == "payment_required" else 400)
            self.send_json(result, status)
        else:
            self.send_json({"error": "not_found"}, 404)


def main():
    parser = argparse.ArgumentParser(description="x402 Financial REST Wrapper")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()
    
    print(f"x402 Financial REST Wrapper")
    print(f"Listening on {args.host}:{args.port}")
    print(f"API: {API_BASE}")
    print(f"Tools: {len(PRICES) + len(FREE_TOOLS)} ({len(FREE_TOOLS)} free)")
    print()
    print("Examples:")
    print(f"  curl {args.host}:{args.port}/tools")
    print(f"  curl {args.host}:{args.port}/call/merchant_clean?description=NTUC%20FINANCE")
    print(f"  curl -X POST {args.host}:{args.port}/call/sgx_price -H 'Content-Type: application/json' -d '{{\"symbol\": \"DBS\"}}'")
    
    server = HTTPServer((args.host, args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()