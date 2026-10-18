import re
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Invoice Structured Output Service")


class ExtractRequest(BaseModel):
    text: str = Field(..., description="Free-form invoice text")


class InvoiceExtraction(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


def extract_vendor(text: str) -> str:
    # Best pattern: "Invoice from <vendor>" or "Vendor: <vendor>"
    patterns = [
        r"(?:invoice\s+from|vendor\s*[:\-])\s*([A-Za-z0-9][A-Za-z0-9 &.,'\-]*?)(?=\s*(?:total|amount|invoice\s+(?:number|no|date)|due|payment|currency|$))",
        r"([A-Za-z0-9][A-Za-z0-9 &.,'\-]*(?:Industries|Ltd\.?|LLC|Inc\.?|Corporation|Corp\.?|Company|Co\.?))",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            vendor = match.group(1).strip(" .,:;-")
            if vendor:
                return vendor

    # Last-resort fallback: first capitalized-looking phrase
    fallback = re.search(r"([A-Z][A-Za-z0-9&.,'\-]*(?:\s+[A-Z][A-Za-z0-9&.,'\-]*)+)", text)
    return fallback.group(1).strip() if fallback else "Unknown Vendor"


def extract_amount(text: str) -> float:
    # Handles: 1234.56, 1,234.56, $1,234.56, EUR 1234.56, Total: 1234.56
    patterns = [
        r"(?:total|amount|due|payable|balance)\s*(?:due)?\s*[:\-]?\s*(?:[A-Z]{3}\s*)?[$€£]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"[$€£]\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue

    return 0.0


def extract_currency(text: str) -> str:
    # Prefer explicit 3-letter currency codes.
    match = re.search(r"\b(USD|EUR|GBP)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # Convert currency symbols as a fallback.
    symbol_map = {"$": "USD", "€": "EUR", "£": "GBP"}
    for symbol, code in symbol_map.items():
        if symbol in text:
            return code

    return "USD"


def extract_date(text: str) -> str:
    # Direct YYYY-MM-DD
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        return match.group(0)

    # DD/MM/YYYY or MM/DD/YYYY — assignment dates are 2026, so year is unambiguous.
    match = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", text)
    if match:
        first, second, year = match.groups()
        # Assume month/day order first; if impossible, swap.
        month, day = int(first), int(second)
        if month > 12:
            month, day = day, month
        return f"{year}-{month:02d}-{day:02d}"

    # Month name formats: 15 July 2026, July 15, 2026
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        day, month_name, year = match.groups()
        month = month_names.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    match = re.search(
        r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        month_name, day, year = match.groups()
        month = month_names.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    return "1970-01-01"


@app.post("/extract", response_model=InvoiceExtraction)
def extract_invoice(request: ExtractRequest):
    text = request.text.strip()

    # Empty text is still valid JSON, so return a best-effort valid object.
    if not text:
        return InvoiceExtraction(
            vendor="Unknown Vendor",
            amount=0.0,
            currency="USD",
            date="1970-01-01",
        )

    return InvoiceExtraction(
        vendor=extract_vendor(text),
        amount=extract_amount(text),
        currency=extract_currency(text),
        date=extract_date(text),
    )
