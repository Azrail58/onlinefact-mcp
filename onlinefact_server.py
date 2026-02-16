"""
OnlineFact MCP Server - Yilmaz Voeding XL
==========================================
MCP server die OnlineFact REST API ontsluit voor Claude.
Gebruik vanuit Claude Code, Claude Desktop, of Claude.ai (via remote MCP).

Transport:
  - stdio  : lokaal (Claude Code / Claude Desktop)
  - sse    : remote (Claude.ai web & mobiel via Render/Railway)

Env vars (voor cloud deployment):
  ONLINEFACT_API_URL, ONLINEFACT_API_KEY, ONLINEFACT_API_SECRET
  MCP_TRANSPORT=sse (default: stdio)
  MCP_BEARER_TOKEN=<geheim> (optioneel, beveiligt remote toegang)
  PORT=10000 (Render default)

Tools: producten, categorieën, merken, klanten, facturen, rapporten.
"""

import json
import os
import sys
import logging
import base64
from pathlib import Path

import requests

# Logging naar stderr (stdout is gereserveerd voor JSON-RPC)
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("onlinefact-mcp")

from mcp.server.fastmcp import FastMCP

# Transport/port/token detectie (nodig vóór FastMCP creatie voor SSE settings)
_transport = os.environ.get("MCP_TRANSPORT", "stdio")
_port = int(os.environ.get("PORT", "10000"))
_bearer_token = os.environ.get("MCP_BEARER_TOKEN", "")


# ── OnlineFact API Client (standalone, geen YilmazTool import nodig) ──

class OnlineFactAPI:
    """REST API client voor OnlineFact. Basic Auth met api_key:api_secret."""

    def __init__(self, api_url, api_key, api_secret):
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _url(self, endpoint):
        return f"{self.api_url}/{endpoint.lstrip('/')}"

    def _get(self, endpoint, params=None):
        resp = self.session.get(self._url(endpoint), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint, data):
        resp = self.session.post(self._url(endpoint), json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _put(self, endpoint, data):
        resp = self.session.put(self._url(endpoint), json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # Products
    def list_products(self, page=1, limit=100, **filters):
        params = {"page": page, "limit": limit}
        params.update(filters)
        return self._get("products/", params)

    def get_product(self, product_id):
        return self._get(f"products/{product_id}/")

    def search_product(self, reference=None, description=None):
        params = {"limit": 10}
        if reference:
            params["reference"] = reference
        if description:
            params["description"] = description
        return self._get("products/", params)

    def create_product(self, reference, description, price_incl=0, tax=6,
                       categorie_id=None, unit=None, purchaseprice_excl=None,
                       barcode=None):
        data = {"reference": reference, "description": description,
                "price_incl": price_incl, "tax": tax}
        if categorie_id:
            data["categorie_id"] = categorie_id
        if unit:
            data["unit"] = unit
        if purchaseprice_excl is not None:
            data["purchaseprice_excl"] = purchaseprice_excl
        if barcode:
            data["barcode"] = barcode
        return self._post("products/", data)

    def update_product(self, product_id, **fields):
        return self._put(f"products/{product_id}/", fields)

    # Categories & Brands
    def list_categories(self, page=1, limit=100):
        return self._get("categories/", {"page": page, "limit": limit})

    def list_brands(self, page=1, limit=100):
        return self._get("brands/", {"page": page, "limit": limit})

    # Customers
    def list_customers(self, page=1, limit=100):
        return self._get("customers/", {"page": page, "limit": limit})

    def get_customer(self, customer_id):
        return self._get(f"customers/{customer_id}/")

    def create_customer(self, name, discount=0, **kwargs):
        data = {"name": name, "discount": discount}
        data.update(kwargs)
        return self._post("customers/", data)

    # Documents
    def list_documents(self, document_type=None, page=1, limit=50,
                       min_date=None, max_date=None, **filters):
        params = {"page": page, "limit": limit}
        if document_type is not None:
            params["document_type"] = document_type
        if min_date:
            params["min_date"] = min_date
        if max_date:
            params["max_date"] = max_date
        params.update(filters)
        return self._get("documents/", params)

    def get_document(self, document_id):
        return self._get(f"documents/{document_id}/")

    def create_document(self, document_type, lines, customer_id=None,
                        document_date=None, reference=None, payment_method=1):
        data = {"document_type": document_type, "payment_method": payment_method,
                "lines": lines}
        if customer_id:
            data["customer_id"] = customer_id
        if document_date:
            data["document_date"] = document_date
        if reference:
            data["reference"] = reference
        return self._post("documents/", data)

    # Reports
    def get_sale_totals(self, min_date, max_date):
        return self._get("reports/saletotals/", {"min_date": min_date, "max_date": max_date})

    def get_sales_per_product(self, min_date, max_date, limit=50):
        return self._get("reports/salesperproduct/",
                         {"min_date": min_date, "max_date": max_date, "limit": limit})

    def get_sales_per_relation(self, min_date, max_date):
        return self._get("reports/salesperrelation/",
                         {"min_date": min_date, "max_date": max_date})

    def test_connection(self):
        try:
            result = self._get("products/", {"limit": 1})
            return True, f"Verbonden ({len(result)} producten)"
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                return False, "Ongeldige API credentials"
            return False, f"HTTP fout: {e.response.status_code}"
        except requests.ConnectionError:
            return False, "Kan niet verbinden met OnlineFact API"
        except Exception as e:
            return False, str(e)


# ── Config laden ──────────────────────────────────────────────

def load_api():
    """Laad OnlineFact API client vanuit env vars of lokale config."""
    # Cloud: gebruik environment variables
    api_url = os.environ.get("ONLINEFACT_API_URL")
    api_key = os.environ.get("ONLINEFACT_API_KEY")
    api_secret = os.environ.get("ONLINEFACT_API_SECRET")

    if api_url and api_key and api_secret:
        logger.info("Config geladen vanuit environment variables")
        return OnlineFactAPI(api_url, api_key, api_secret)

    # Lokaal: gebruik yilmaz_config.json
    config_path = Path(__file__).parent.parent / "YilmazTool" / "yilmaz_config.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        of = cfg["onlinefact"]
        logger.info(f"Config geladen vanuit {config_path}")
        return OnlineFactAPI(of["api_url"], of["api_key"], of["api_secret"])

    raise RuntimeError("Geen OnlineFact config gevonden (env vars of yilmaz_config.json)")

api = load_api()
logger.info("OnlineFact API client geladen")

# ── MCP Server ────────────────────────────────────────────────

_mcp_kwargs = dict(
    instructions=(
        "OnlineFact kassasysteem van Yilmaz Voeding XL. "
        "Bevat producten, klanten, facturen en verkooprapporten. "
        "Alle prijzen zijn in EUR. Documenten types: "
        "1=offerte, 2=bestelling, 3=factuur, 4=creditnota, 5=leveringsbon, 8=ticket."
    ),
)
if _transport == "sse":
    _mcp_kwargs["host"] = "0.0.0.0"
    _mcp_kwargs["port"] = _port

mcp = FastMCP("onlinefact", **_mcp_kwargs)

# ── PRODUCTEN ─────────────────────────────────────────────────

@mcp.tool()
def zoek_producten(zoekterm: str) -> str:
    """Zoek producten op naam of referentiecode in OnlineFact.

    Args:
        zoekterm: Productnaam (bijv. 'Kizilay') of referentie (bijv. 'P001')
    """
    try:
        # Probeer eerst op referentie, dan op beschrijving
        results = api.search_product(description=zoekterm)
        if not results:
            results = api.search_product(reference=zoekterm)
        if not results:
            return f"Geen producten gevonden voor '{zoekterm}'"
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij zoeken: {e}"


@mcp.tool()
def product_details(product_id: int) -> str:
    """Haal volledige details op van een product.

    Args:
        product_id: Het OnlineFact product ID
    """
    try:
        result = api.get_product(product_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen product {product_id}: {e}"


@mcp.tool()
def lijst_producten(pagina: int = 1, aantal: int = 50) -> str:
    """Toon een lijst van producten met paginering.

    Args:
        pagina: Paginanummer (standaard 1)
        aantal: Aantal per pagina (standaard 50, max 100)
    """
    try:
        results = api.list_products(page=pagina, limit=min(aantal, 100))
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen producten: {e}"


@mcp.tool()
def maak_product(
    referentie: str,
    beschrijving: str,
    prijs_incl: float,
    btw: int = 6,
    eenheid: str = "ST",
    categorie_id: int = 0,
    inkoopprijs: float = 0,
    barcode: str = "",
) -> str:
    """Maak een nieuw product aan in OnlineFact.

    Args:
        referentie: Unieke productcode (bijv. 'P_NIEUW_001')
        beschrijving: Productnaam
        prijs_incl: Verkoopprijs inclusief BTW
        btw: BTW percentage (standaard 6)
        eenheid: Eenheid - ST (stuk), KG, L, etc.
        categorie_id: Categorie ID (0 = geen)
        inkoopprijs: Inkoopprijs exclusief BTW
        barcode: EAN/barcode (optioneel)
    """
    try:
        result = api.create_product(
            reference=referentie,
            description=beschrijving,
            price_incl=prijs_incl,
            tax=btw,
            unit=eenheid,
            categorie_id=categorie_id if categorie_id else None,
            purchaseprice_excl=inkoopprijs if inkoopprijs else None,
            barcode=barcode if barcode else None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij aanmaken product: {e}"


@mcp.tool()
def update_product(product_id: int, velden: str) -> str:
    """Wijzig een bestaand product in OnlineFact.

    Args:
        product_id: Het product ID
        velden: JSON string met te wijzigen velden, bijv. '{"price_incl": 2.99, "stock": 50}'
            Mogelijke velden: description, price_incl, tax, unit, stock,
            purchaseprice_excl, costprice_excl, barcode, categorie_id, managestock
    """
    try:
        fields = json.loads(velden)
        result = api.update_product(product_id, **fields)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {velden}"
    except Exception as e:
        return f"Fout bij updaten product {product_id}: {e}"


# ── CATEGORIEËN & MERKEN ──────────────────────────────────────

@mcp.tool()
def lijst_categorieen() -> str:
    """Toon alle productcategorieën in OnlineFact."""
    try:
        results = api.list_categories(limit=200)
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen categorieën: {e}"


@mcp.tool()
def lijst_merken() -> str:
    """Toon alle merken in OnlineFact."""
    try:
        results = api.list_brands(limit=200)
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen merken: {e}"


# ── KLANTEN ───────────────────────────────────────────────────

@mcp.tool()
def lijst_klanten(pagina: int = 1, aantal: int = 50) -> str:
    """Toon alle klanten in OnlineFact.

    Args:
        pagina: Paginanummer
        aantal: Aantal per pagina
    """
    try:
        results = api.list_customers(page=pagina, limit=min(aantal, 100))
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen klanten: {e}"


@mcp.tool()
def klant_details(klant_id: int) -> str:
    """Haal details op van een klant.

    Args:
        klant_id: Het klant ID
    """
    try:
        result = api.get_customer(klant_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen klant {klant_id}: {e}"


@mcp.tool()
def maak_klant(naam: str, korting: int = 0) -> str:
    """Maak een nieuwe klant aan.

    Args:
        naam: Klantnaam
        korting: Kortingspercentage (standaard 0)
    """
    try:
        result = api.create_customer(name=naam, discount=korting)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij aanmaken klant: {e}"


# ── DOCUMENTEN (FACTUREN) ────────────────────────────────────

@mcp.tool()
def lijst_facturen(
    type: int = 3,
    van_datum: str = "",
    tot_datum: str = "",
    pagina: int = 1,
    aantal: int = 50,
) -> str:
    """Toon facturen/documenten uit OnlineFact.

    Args:
        type: Document type - 1=offerte, 2=bestelling, 3=factuur, 4=creditnota, 5=leveringsbon, 8=ticket
        van_datum: Startdatum (YYYY-MM-DD), leeg = geen filter
        tot_datum: Einddatum (YYYY-MM-DD), leeg = geen filter
        pagina: Paginanummer
        aantal: Aantal per pagina
    """
    try:
        results = api.list_documents(
            document_type=type,
            page=pagina,
            limit=min(aantal, 100),
            min_date=van_datum if van_datum else None,
            max_date=tot_datum if tot_datum else None,
        )
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen documenten: {e}"


@mcp.tool()
def factuur_details(document_id: int) -> str:
    """Haal een volledige factuur op met alle regels.

    Args:
        document_id: Het document/factuur ID
    """
    try:
        result = api.get_document(document_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen factuur {document_id}: {e}"


@mcp.tool()
def maak_factuur(
    type: int,
    regels: str,
    klant_id: int = 0,
    datum: str = "",
    referentie: str = "",
    betaalmethode: int = 1,
) -> str:
    """Maak een nieuwe factuur/document aan in OnlineFact.

    Args:
        type: Document type - 1=offerte, 2=bestelling, 3=factuur, 4=creditnota, 5=leveringsbon, 8=ticket
        regels: JSON array met factuurregels, bijv. '[{"reference":"P001","quantity":2,"description":"Appel","price_vatexcl":1.50,"tax":6}]'
        klant_id: Klant ID (0 = geen klant)
        datum: Factuurdatum YYYY-MM-DD (leeg = vandaag)
        referentie: Eigen referentie/opmerking
        betaalmethode: 1=onbetaald, 2=cash, 3=overschrijving, 4=creditcard, 6=bancontact
    """
    try:
        lines = json.loads(regels)
        result = api.create_document(
            document_type=type,
            lines=lines,
            customer_id=klant_id if klant_id else None,
            document_date=datum if datum else None,
            reference=referentie if referentie else None,
            payment_method=betaalmethode,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON voor regels: {regels}"
    except Exception as e:
        return f"Fout bij aanmaken factuur: {e}"


# ── RAPPORTEN ─────────────────────────────────────────────────

@mcp.tool()
def verkoop_totaal(van_datum: str, tot_datum: str) -> str:
    """Haal verkooptotalen op voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        result = api.get_sale_totals(min_date=van_datum, max_date=tot_datum)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen verkooptotalen: {e}"


@mcp.tool()
def verkoop_per_product(van_datum: str, tot_datum: str, aantal: int = 50) -> str:
    """Toon verkoop per product (top producten) voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
        aantal: Maximum aantal producten (standaard 50)
    """
    try:
        result = api.get_sales_per_product(
            min_date=van_datum, max_date=tot_datum, limit=min(aantal, 100)
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen verkoop per product: {e}"


@mcp.tool()
def verkoop_per_klant(van_datum: str, tot_datum: str) -> str:
    """Toon omzet per klant voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        result = api.get_sales_per_relation(min_date=van_datum, max_date=tot_datum)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen verkoop per klant: {e}"


# ── SYSTEEM ───────────────────────────────────────────────────

@mcp.tool()
def test_verbinding() -> str:
    """Test de verbinding met de OnlineFact API."""
    try:
        ok, msg = api.test_connection()
        status = "OK" if ok else "FOUT"
        return f"Verbinding: {status} - {msg}"
    except Exception as e:
        return f"Verbindingsfout: {e}"


# ── Start ─────────────────────────────────────────────────────

if __name__ == "__main__":
    if _transport == "sse":
        if _bearer_token:
            # Beveiligde SSE met bearer token middleware
            import uvicorn
            from starlette.middleware import Middleware
            from starlette.middleware.base import BaseHTTPMiddleware
            from starlette.responses import JSONResponse

            class BearerAuthMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    auth = request.headers.get("Authorization", "")
                    if auth != f"Bearer {_bearer_token}":
                        return JSONResponse(
                            {"error": "Unauthorized"}, status_code=401
                        )
                    return await call_next(request)

            app = mcp.sse_app()
            app.add_middleware(BearerAuthMiddleware)

            logger.info(f"OnlineFact MCP Server gestart (SSE+Auth, poort {_port})")
            config = uvicorn.Config(app, host="0.0.0.0", port=_port, log_level="info")
            server = uvicorn.Server(config)
            import asyncio
            asyncio.run(server.serve())
        else:
            logger.info(f"OnlineFact MCP Server gestart (SSE, poort {_port})")
            mcp.run(transport="sse")
    else:
        logger.info("OnlineFact MCP Server gestart (stdio)")
        mcp.run(transport="stdio")
