"""
x402 Financial API — Vercel Serverless Entry Point
==================================================
Vercel Python runtime entry point. Converts the HTTP server to a 
FastAPI app compatible with @vercel/python builder.
"""

import os
import json
import base64
from typing import Optional
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

app = FastAPI(title="x402 Financial REST Wrapper")

API_BASE = os.getenv("API_BASE", "https://x402-financial-data-api.vercel.app")
WALLET = "0x50F9D979b825670A9936D992F5db8AEd9497208A"
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

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
    "business_lookup": 0.02, "salary_benchmark": 0.01, "salary_net": 0.01,
    "tax_income": 0.02, "tax_calculator": 0.02,
}

ENDPOINT_MAP = {
    "parse_pdf": "/parse/{bank}", "sgx_stock": "/sgx/stock",
    "sgx_portfolio": "/sgx/portfolio", "sgx_price": "/sgx/price",
    "cpf_calculator": "/cpf/calculator", "tax_income": "/tax/income",
    "fire_calculator": "/fire/calculator", "property_tax": "/property/tax",
    "hdb_resale": "/hdb/resale", "bto_affordability": "/bto/affordability",
    "electricity_compare": "/electricity/compare", "school_nearby": "/school/nearby",
    "merchant_clean": "/merchant/clean", "holidays_singapore": "/holidays/singapore",
}

FREE_TOOLS = {"merchant_clean", "holidays_singapore", "singapore_compound"}


def _build_x402_header(addr: str, max_gas: int = 250000) -> dict:
    payload = json.dumps({
        "protocol": "2", "network": "base", "version": "1",
        "payload": {"address": addr, "maxGas": str(max_gas), "validAfter": 0, "validUntil": 0, "deadline": "0"}
    })
    return {"x402": payload, "Content-Type": "application/json", "Accept": "application/json"}


async def _call_api(endpoint: str, method: str = "GET", params: dict = None, wallet_seed: str = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    headers = {}
    if wallet_seed:
        headers = _build_x402_header(WALLET)
    else:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=60) as client:
        if method == "GET":
            r = await client.get(url, headers=headers, params=params)
        else:
            r = await client.post(url, headers=headers, json=params)
    
    if r.status_code == 402:
        return {"error": "payment_required", "payment": r.json()}
    return r.json()


@app.get("/tools")
async def list_tools():
    tools = [{"name": k, "price": v, "endpoint": ENDPOINT_MAP.get(k, "/")} for k, v in PRICES.items()]
    tools.extend([{"name": f, "price": 0, "endpoint": ENDPOINT_MAP.get(f, "/")} for f in FREE_TOOLS])
    return {"tools": tools, "count": len(tools)}


@app.get("/tools/free")
async def list_free_tools():
    return {"free_tools": list(FREE_TOOLS)}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "x402 Financial REST Wrapper", "api_base": API_BASE}


@app.get("/call/{tool_name}")
async def call_free_tool(tool_name: str, description: str = None, year: int = None):
    if tool_name not in FREE_TOOLS:
        raise HTTPException(status_code=400, detail=f"{tool_name} is not a free tool")
    
    if tool_name == "merchant_clean":
        return await _call_api("/merchant/clean", params={"description": description or ""})
    elif tool_name == "holidays_singapore":
        return await _call_api("/holidays/singapore", params={"year": year or 2026})
    
    raise HTTPException(status_code=404, detail="Tool not found")


@app.post("/call/{tool_name}")
async def call_paid_tool(tool_name: str, request: Request, x_wallet_seed: str = None):
    body = await request.json()
    
    if tool_name not in ENDPOINT_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    
    endpoint = ENDPOINT_MAP[tool_name]
    price = PRICES.get(tool_name, 0)
    
    if not x_wallet_seed and price > 0:
        return JSONResponse(
            status_code=402,
            content={"error": "payment_required", "tool": tool_name, "price_usdc": price, "wallet": WALLET}
        )
    
    return await _call_api(endpoint, method="POST", params=body, wallet_seed=x_wallet_seed)