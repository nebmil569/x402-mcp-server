"""
x402 Financial Data API — MCP Server
======================================
Exposes x402 Financial API as MCP tools. AI agents can call financial tools
directly via the MCP protocol without needing x402 SDK integration.

Builds on the x402 Financial Data API (x402-financial-api.life.conway.tech) which has
47+ paid endpoints and 4 free endpoints.

Usage:
    python mcp_server.py
    # Then connect via MCP client (Claude Desktop, OpenClaw agents, etc.)

For OpenClaw: configure in openclaw.yaml as a spawning service.
"""

import os
import json
import base64
from typing import Optional, List, Dict, Any
import struct
import hashlib
import hmac

# HTTP
import requests

# MCP
from mcp.server import Server
from mcp.types import Tool, CallToolResult

# ============================================================
# x402 Payment Constants
# ============================================================
NETWORK = "eip155:8453"
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
WALLET = "0x50F9D979b825670A9936D992F5db8AEd9497208A"
API_BASE = "https://x402-financial-api.life.conway.tech"

# Price map (USDC)
PRICES = {
    "parse_pdf": 0.02,
    "extract_transactions": 0.01,
    "summary": 0.01,
    "spending_report": 0.01,
    "cash_flow_report": 0.01,
    "subscriptions_report": 0.01,
    "billing_calendar": 0.01,
    "tax_report": 0.02,
    "cpf_calculator": 0.02,
    "srs_calculator": 0.01,
    "hdb_resale": 0.01,
    "invoice": 0.02,
    "financial_insights": 0.01,
    "portfolio_summary": 0.05,
    "batch_clean_21_100": 0.005,
    "sgx_stock": 0.02,
    "sgx_portfolio": 0.03,
    "sgx_price": 0.005,
    "coe_prices": 0.01,
    "singapore_holidays": 0.005,
    "singapore_benefits": 0.01,
    "property_tax": 0.01,
    "condo_maintenance": 0.01,
    "absd_calculator": 0.01,
    "bto_affordability": 0.02,
    "car_loan_parf": 0.01,
    "financial_health_score": 0.01,
    "forex_convert": 0.005,
    "ssb_rates": 0.01,
    "ssb_calculator": 0.01,
    "utilities_estimate": 0.005,
    "electricity_compare": 0.01,
    "fire_calculator": 0.01,
    "school_nearby": 0.01,
    "school_nearby_secondary": 0.01,
    "hawker_nearby": 0.01,
    "goal_plan": 0.01,
    "retirement_community": 0.01,
    "mortgage_compare": 0.01,
    "business_lookup": 0.02,
    "salary_benchmark": 0.01,
    "rental_yield": 0.01,
    "tax_income": 0.02,
    "refinance": 0.015,
    "sgx_fundamentals": 0.02,
    "savings_optimize": 0.02,
    "financial_audit": 0.10,
}

# Free endpoints (no payment required)
FREE_TOOLS = {
    "merchant_clean": "/merchant/clean",
    "merchant_batch_clean": "/merchant/batch-clean",
    "holidays_singapore": "/holidays/singapore",
    "singapore_compound": "/singapore/compound",
}

SUPPORTED_BANKS = ["dbs", "posb", "ocbc", "uob", "citi", "maybank", "standchart", "trust", "boc"]


def price_to_wei(price_usd: float) -> int:
    return int(price_usd * 10**18)


def build_payment_headers(tool_name: str) -> Dict[str, str]:
    """Build x402 payment headers"""
    price = PRICES.get(tool_name, 0)
    price_wei = price_to_wei(price)
    headers = {
        "Content-Type": "application/json",
        "x402-version": "2",
        "x402-network": NETWORK,
        "x402-asset": ASSET,
        "x402-price": str(price_wei),
        "x402-recipient": WALLET,
    }
    return headers


def call_x402_endpoint(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Make an x402-compatible call to the API"""
    
    # Determine endpoint URL
    if tool_name in FREE_TOOLS:
        endpoint = FREE_TOOLS[tool_name]
        url = f"{API_BASE}{endpoint}"
        if arguments:
            import urllib.parse
            url += "?" + urllib.parse.urlencode(arguments)
        headers = {"Accept": "application/json"}
    else:
        # Map tool name to endpoint
        endpoint_map = {
            "parse_pdf": "/parse/{bank}",
            "sgx_stock": "/sgx/stock",
            "sgx_portfolio": "/sgx/portfolio",
            "sgx_price": "/sgx/price",
            "sgx_fundamentals": "/sgx/fundamentals",
            "cpf_calculator": "/cpf/calculator",
            "tax_income": "/tax/income",
            "fire_calculator": "/fire/calculator",
            "bto_affordability": "/bto/topup-suggestions",
            "refinance": "/refinance",
            "school_nearby": "/school/nearby",
            "school_nearby_secondary": "/school/nearby-secondary",
            "business_lookup": "/business/lookup",
            "forex_convert": "/forex/convert",
            "utilities_estimate": "/utilities/estimate",
            "electricity_compare": "/electricity/compare",
            "property_tax": "/property/tax",
            "absd_calculator": "/absd/calculator",
            "financial_health_score": "/financial/health-score",
            "salary_benchmark": "/salary/benchmark",
            "rental_yield": "/rental/yield",
            "cpf_topup": "/cpf/topup",
            "goal_plan": "/goal/plan",
            "retirement_community": "/retirement/community",
            "mortgage_compare": "/mortgage/compare",
            "savings_optimize": "/savings/optimize",
            "summary": "/summary",
            "spending_report": "/report/spending",
            "cash_flow_report": "/report/cash-flow",
            "subscriptions_report": "/report/subscriptions",
            "billing_calendar": "/billing/calendar",
            "tax_report": "/report/tax",
            "hdb_resale": "/hdb/resale",
            "condo_maintenance": "/condo/maintenance",
            "car_loan_parf": "/car/loan-parf",
            "ssb_rates": "/ssb/rates",
            "ssb_calculator": "/ssb/calculator",
            "coe_prices": "/coe/prices",
            "singapore_benefits": "/singapore/benefits",
            "portfolio_summary": "/report/portfolio",
            "invoice": "/invoice/generate",
            "srs_calculator": "/srs/calculator",
            "financial_insights": "/financial/insights",
        }
        
        endpoint = endpoint_map.get(tool_name, f"/{tool_name.replace('_', '/')}")
        url = f"{API_BASE}{endpoint}"
        headers = build_payment_headers(tool_name)
        
        # Special handling for parse_pdf
        if tool_name == "parse_pdf":
            bank = arguments.get("bank", "dbs")
            url = f"{API_BASE}/parse/{bank}"
            arguments = {k: v for k, v in arguments.items() if k != "bank"}
    
    try:
        # Free tools use GET, paid tools use POST
        if tool_name in FREE_TOOLS:
            response = requests.get(url, headers=headers, timeout=30)
        else:
            response = requests.post(url, json=arguments, headers=headers, timeout=30)
        
        if response.status_code == 402:
            result = response.json()
            msg = result.get("error", result.get("message", "Payment required"))
            required = result.get("required_amount", str(PRICES.get(tool_name, 0)))
            return f"💳 Payment required ({PRICES.get(tool_name, 0)} USDC): {msg}"
        
        if response.status_code == 200:
            return json.dumps(response.json(), indent=2)
        
        return f"Error {response.status_code}: {response.text[:500]}"
    
    except Exception as e:
        return f"Request failed: {str(e)}"


# ============================================================
# MCP Server
# ============================================================

server = Server("x402-financial-api")


def get_tool_definitions() -> List[Tool]:
    """Build the tool definitions"""
    tools = []
    
    # Paid tools
    for name, price in PRICES.items():
        tools.append(Tool(
            name=name,
            description=_desc(name),
            inputSchema={
                "type": "object",
                "properties": _params(name),
                "required": _required(name),
            }
        ))
    
    # Free tools
    free_descs = {
        "merchant_clean": "Clean and standardize merchant names using AI",
        "merchant_batch_clean": "Batch clean merchant names",
        "holidays_singapore": "Get Singapore public holidays for a year",
        "singapore_compound": "Calculate compound savings growth in Singapore",
    }
    for name in FREE_TOOLS:
        tools.append(Tool(
            name=name,
            description=free_descs[name],
            inputSchema={"type": "object", "properties": {}, "required": []}
        ))
    
    return tools


def _desc(name: str) -> str:
    d = {
        "parse_pdf": "Parse a bank statement PDF (9 Singapore banks: DBS, POSB, OCBC, UOB, Citi, Maybank, Standard Chartered, Trust, BOC)",
        "sgx_stock": "Get SGX stock data, fundamentals, price, and analyst recommendations",
        "sgx_portfolio": "Analyze a portfolio of SGX stocks with totals and metrics",
        "cpf_calculator": "Calculate CPF contributions and projections",
        "tax_income": "Calculate Singapore income tax for a given income and year",
        "fire_calculator": "Calculate FIRE (Financial Independence, Retire Early) numbers",
        "bto_affordability": "Calculate BTO (Build-To-Order) flat affordability",
        "refinance": "Analyze mortgage refinance opportunities",
        "school_nearby": "Find primary schools near a Singapore postal district",
        "business_lookup": "Look up Singapore business entity by UEN",
        "forex_convert": "Convert currencies at live forex rates",
        "utilities_estimate": "Estimate Singapore utilities (electricity, water, gas) costs",
        "electricity_compare": "Compare Singapore electricity retailer plans",
        "property_tax": "Calculate Singapore property tax",
        "absd_calculator": "Calculate ABSD (Additional Buyer's Stamp Duty)",
        "financial_health_score": "Calculate personal financial health score",
        "salary_benchmark": "Benchmark salary against Singapore market",
        "rental_yield": "Calculate rental yield for Singapore property",
        "cpf_topup": "Calculate optimal CPF top-up strategy",
        "goal_plan": "Generate a financial goal plan",
        "retirement_community": "Find retirement community options in Singapore",
        "mortgage_compare": "Compare mortgage rates across Singapore banks",
        "savings_optimize": "Optimize savings strategy",
        "summary": "Generate AI-powered financial summary from transactions",
        "spending_report": "Generate detailed spending analysis report",
        "cash_flow_report": "Generate cash flow analysis",
        "subscriptions_report": "Detect recurring subscriptions from transactions",
        "billing_calendar": "Generate billing calendar from transactions",
        "tax_report": "Generate Singapore income tax estimate report",
        "hdb_resale": "Estimate HDB resale value",
        "invoice": "Parse and extract data from invoices",
        "portfolio_summary": "Generate portfolio summary report",
        "coe_prices": "Get latest COE prices",
        "singapore_benefits": "Check eligible Singapore government benefits",
        "financial_insights": "Generate AI-powered financial insights",
        "srs_calculator": "Calculate SRS (Supplementary Retirement Scheme) projections",
        "ssb_calculator": "Calculate Singapore Savings Bonds returns",
        "ssb_rates": "Get latest SSB interest rates",
        "car_loan_parf": "Calculate car loan and PARF",
        "condo_maintenance": "Estimate condo maintenance fees",
        "extract_transactions": "Extract and categorize transactions from bank data",
        "batch_clean_21_100": "Batch clean merchant names (21-100 names)",
    }
    return d.get(name, f"Call x402 {name} endpoint")


def _params(name: str) -> Dict[str, Any]:
    p = {
        "parse_pdf": {"bank": {"type": "string", "description": "Bank code: dbs, posb, ocbc, uob, citi, maybank, standchart, trust, boc"}, "data": {"type": "string", "description": "Base64-encoded PDF data"}},
        "sgx_stock": {"symbol": {"type": "string", "description": "SGX stock symbol (e.g., DBS, O39, U11)"}},
        "sgx_portfolio": {"stocks": {"type": "array", "items": {"type": "string"}, "description": "List of SGX stock symbols"}, "shares": {"type": "array", "items": {"type": "number"}, "description": "Number of shares per stock"}},
        "sgx_price": {"symbol": {"type": "string", "description": "SGX stock symbol"}},
        "sgx_fundamentals": {"symbol": {"type": "string", "description": "SGX stock symbol"}},
        "cpf_calculator": {"age": {"type": "number", "description": "Current age"}, "salary": {"type": "number", "description": "Monthly salary (SGD)"}},
        "tax_income": {"income": {"type": "number", "description": "Annual income (SGD)"}, "year": {"type": "number", "description": "Tax year (e.g., 2025)"}},
        "fire_calculator": {"age": {"type": "number", "description": "Current age"}, "annual_income": {"type": "number", "description": "Annual income (SGD)"}, "annual_expenses": {"type": "number", "description": "Annual expenses (SGD)"}, "current_savings": {"type": "number", "description": "Current savings (SGD)"}},
        "bto_affordability": {"income": {"type": "number", "description": "Monthly household income (SGD)"}, "age": {"type": "number", "description": "Your age"}},
        "refinance": {"loan_amount": {"type": "number", "description": "Current loan amount (SGD)"}, "current_rate": {"type": "number", "description": "Current interest rate (%)"}, "property_value": {"type": "number", "description": "Property value (SGD)"}},
        "school_nearby": {"postal_district": {"type": "string", "description": "Postal district (e.g., '18' or '18,19')"}},
        "school_nearby_secondary": {"postal_district": {"type": "string", "description": "Postal district"}, "psle_score": {"type": "number", "description": "PSLE score"}},
        "business_lookup": {"uen": {"type": "string", "description": "UEN (e.g., '202012345A')"}},
        "forex_convert": {"from_currency": {"type": "string", "description": "From currency (e.g., USD, EUR)"}, "to_currency": {"type": "string", "description": "To currency (e.g., SGD)"}, "amount": {"type": "number", "description": "Amount to convert"}},
        "utilities_estimate": {"house_type": {"type": "string", "description": "HDB type: 1-room, 2-room, 3-room, 4-room, 5-room, executive"}},
        "electricity_compare": {"consumption_kwh": {"type": "number", "description": "Monthly consumption (kWh)"}},
        "property_tax": {"annual_value": {"type": "number", "description": "Annual rental value (SGD)"}, "owner_type": {"type": "string", "description": "owner-occupied or investor"}},
        "absd_calculator": {"price": {"type": "number", "description": "Property price (SGD)"}, "buyer_type": {"type": "string", "description": "citizen, pr, foreigner"}},
        "financial_health_score": {"monthly_income": {"type": "number", "description": "Monthly income (SGD)"}, "monthly_expenses": {"type": "number", "description": "Monthly expenses (SGD)"}, "total_savings": {"type": "number", "description": "Total savings (SGD)"}},
        "salary_benchmark": {"job_title": {"type": "string", "description": "Job title"}, "years_experience": {"type": "number", "description": "Years of experience"}},
        "rental_yield": {"property_price": {"type": "number", "description": "Property price (SGD)"}, "monthly_rent": {"type": "number", "description": "Monthly rent (SGD)"}},
        "cpf_topup": {"current_cpf": {"type": "number", "description": "Current CPF OA amount (SGD)"}, "monthly_salary": {"type": "number", "description": "Monthly salary (SGD)"}},
        "goal_plan": {"goal": {"type": "string", "description": "Financial goal (e.g., 'retire at 55')"}, "current_savings": {"type": "number", "description": "Current savings (SGD)"}, "monthly_income": {"type": "number", "description": "Monthly income (SGD)"}, "monthly_expenses": {"type": "number", "description": "Monthly expenses (SGD)"}},
        "retirement_community": {"budget": {"type": "number", "description": "Budget (SGD)"}, "location": {"type": "string", "description": "Preferred area"}},
        "mortgage_compare": {"loan_amount": {"type": "number", "description": "Loan amount (SGD)"}, "tenure_years": {"type": "number", "description": "Loan tenure (years)"}},
        "savings_optimize": {"monthly_income": {"type": "number", "description": "Monthly income (SGD)"}, "monthly_expenses": {"type": "number", "description": "Monthly expenses (SGD)"}, "goal": {"type": "string", "description": "Financial goal"}},
        "summary": {"transactions": {"type": "array", "description": "Transaction data"}},
        "spending_report": {"transactions": {"type": "array", "description": "Transaction data"}, "period": {"type": "string", "description": "Period (e.g., '2024-01')"}},
        "cash_flow_report": {"transactions": {"type": "array", "description": "Transaction data"}},
        "subscriptions_report": {"transactions": {"type": "array", "description": "Transaction data"}},
        "billing_calendar": {"transactions": {"type": "array", "description": "Transaction data"}},
        "tax_report": {"income": {"type": "number", "description": "Annual income (SGD)"}, "year": {"type": "number", "description": "Tax year"}},
        "hdb_resale": {"flat_type": {"type": "string", "description": "Flat type: 2-room, 3-room, 4-room, 5-room, executive"}, "storey": {"type": "string", "description": "Storey range (e.g., 4-6)"}, "town": {"type": "string", "description": "Town (e.g., Tampines, Bedok)"}, "floor_area": {"type": "number", "description": "Floor area (sqm)"}, "remaining_lease": {"type": "number", "description": "Remaining lease (years)"}},
        "coe_prices": {"category": {"type": "string", "description": "Category: A, B, C (optional)"}},
        "singapore_benefits": {"income": {"type": "number", "description": "Annual household income (SGD)"}, "age": {"type": "number", "description": "Age"}, "housing_type": {"type": "string", "description": "HDB or private"}},
        "portfolio_summary": {"stocks": {"type": "array", "description": "Stock holdings"}, "total_value": {"type": "number", "description": "Total portfolio value (SGD)"}},
        "invoice": {"data": {"type": "string", "description": "Base64-encoded invoice PDF"}, "text": {"type": "string", "description": "Or plain text invoice data"}},
        "srs_calculator": {"contribution": {"type": "number", "description": "Annual SRS contribution (SGD)"}, "years": {"type": "number", "description": "Years until retirement"}},
        "ssb_calculator": {"amount": {"type": "number", "description": "Investment amount (SGD)"}, "tenure": {"type": "number", "description": "Tenure in years"}},
        "car_loan_parf": {"purchase_price": {"type": "number", "description": "Car price (SGD)"}, "open_market_value": {"type": "number", "description": "OMV (SGD)"}, "coe_premium": {"type": "number", "description": "COE premium (SGD)"}, "age": {"type": "number", "description": "Car age (years)"}},
        "condo_maintenance": {"condo_type": {"type": "string", "description": "Condo type: 1-bedroom, 2-bedroom, 3-bedroom"}, "location": {"type": "string", "description": "District/area"}},
        "extract_transactions": {"data": {"type": "string", "description": "Base64-encoded bank statement PDF"}, "bank": {"type": "string", "description": "Bank code"}},
    }
    return p.get(name, {})


def _required(name: str) -> List[str]:
    req = {
        "parse_pdf": ["bank"],
        "sgx_stock": ["symbol"],
        "sgx_portfolio": ["stocks", "shares"],
        "sgx_price": ["symbol"],
        "sgx_fundamentals": ["symbol"],
        "school_nearby": ["postal_district"],
        "school_nearby_secondary": ["postal_district"],
        "business_lookup": ["uen"],
        "forex_convert": ["from_currency", "to_currency", "amount"],
        "property_tax": ["annual_value", "owner_type"],
        "absd_calculator": ["price", "buyer_type"],
        "financial_health_score": ["monthly_income", "monthly_expenses", "total_savings"],
        "salary_benchmark": ["job_title", "years_experience"],
        "rental_yield": ["property_price", "monthly_rent"],
        "cpf_topup": ["current_cpf", "monthly_salary"],
        "goal_plan": ["goal", "current_savings", "monthly_income", "monthly_expenses"],
        "rental_yield": ["property_price", "monthly_rent"],
    }
    return req.get(name, [])


@server.list_tools()
async def list_tools() -> List[Tool]:
    return get_tool_definitions()


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Call a financial tool"""
    result = call_x402_endpoint(name, arguments)
    return [{"type": "text", "text": result}]


async def main():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())