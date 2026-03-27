"""
OnlineFact MCP Server v3.0 - Yilmaz Voeding XL
================================================
MCP server die OnlineFact REST API ontsluit voor Claude.
Gebruik vanuit Claude Code, Claude Desktop, of Claude.ai (via remote MCP).

Transport:
  - stdio           : lokaal (Claude Code / Claude Desktop)
  - streamable-http : remote (Claude.ai web & mobiel via Render)

Env vars (voor cloud deployment):
  ONLINEFACT_API_URL, ONLINEFACT_API_KEY, ONLINEFACT_API_SECRET
  MCP_TRANSPORT=sse|streamable-http (default: stdio)
  PORT=10000 (Render default)

Tools (55+): producten, categorieën, merken, klanten, leveranciers, facturen,
  creditnota's, bestellingen, voorraad, rapporten, analyse.
Prompts (3): maandrapport, inventaris_check, prijslijst.
Resources (2): catalogus, categorieen.
"""

import json
import os
import sys
import logging
import base64
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Logging naar stderr (stdout is gereserveerd voor JSON-RPC)
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("onlinefact-mcp")

from mcp.server.fastmcp import FastMCP

# Transport/port detectie (nodig vóór FastMCP creatie)
# Remote transport is altijd streamable-http (Claude.ai vereist dit)
_raw_transport = os.environ.get("MCP_TRANSPORT", "stdio")
_transport = "streamable-http" if _raw_transport in ("sse", "streamable-http") else _raw_transport
_port = int(os.environ.get("PORT", "10000"))
# Geheim pad voor URL-beveiliging (alleen wie de URL kent heeft toegang)
_secret_path = os.environ.get("MCP_SECRET_PATH", "5156490603d507d7")


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

    def _delete(self, endpoint):
        resp = self.session.delete(self._url(endpoint), timeout=30)
        resp.raise_for_status()
        return resp.status_code == 204 or resp.ok

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

    def delete_product(self, product_id):
        return self._delete(f"products/{product_id}/")

    # Categories
    def list_categories(self, page=1, limit=100):
        return self._get("categories/", {"page": page, "limit": limit})

    def get_category(self, category_id):
        return self._get(f"categories/{category_id}/")

    def create_category(self, name, parent_id=0, sort_order=0):
        data = {"name": name, "parent_id": parent_id, "sort_order": sort_order}
        return self._post("categories/", data)

    def update_category(self, category_id, **fields):
        return self._put(f"categories/{category_id}/", fields)

    def delete_category(self, category_id):
        return self._delete(f"categories/{category_id}/")

    # Brands
    def list_brands(self, page=1, limit=100):
        return self._get("brands/", {"page": page, "limit": limit})

    def get_brand(self, brand_id):
        return self._get(f"brands/{brand_id}/")

    def create_brand(self, name):
        return self._post("brands/", {"name": name})

    def update_brand(self, brand_id, **fields):
        return self._put(f"brands/{brand_id}/", fields)

    def delete_brand(self, brand_id):
        return self._delete(f"brands/{brand_id}/")

    # Customers
    def list_customers(self, page=1, limit=100, **filters):
        params = {"page": page, "limit": limit}
        params.update(filters)
        return self._get("customers/", params)

    def get_customer(self, customer_id):
        return self._get(f"customers/{customer_id}/")

    def create_customer(self, name, discount=0, **kwargs):
        data = {"name": name, "discount": discount}
        data.update(kwargs)
        return self._post("customers/", data)

    def update_customer(self, customer_id, **fields):
        return self._put(f"customers/{customer_id}/", fields)

    def delete_customer(self, customer_id):
        return self._delete(f"customers/{customer_id}/")

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

    def update_document(self, document_id, **fields):
        return self._put(f"documents/{document_id}/", fields)

    def delete_document(self, document_id):
        return self._delete(f"documents/{document_id}/")

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

_instructions = (
    "OnlineFact kassasysteem van Yilmaz Voeding XL. "
    "Bevat producten, categorieën, merken, klanten, leveranciers, facturen, "
    "creditnota's, bestellingen, offertes, leveringsbonnen, voorraad en verkooprapporten. "
    "Alle prijzen zijn in EUR. Documenten types: "
    "1=offerte, 2=bestelling, 3=factuur, 4=creditnota, 5=leveringsbon, 8=ticket."
)

_mcp_kwargs = dict(instructions=_instructions)
if _transport in ("sse", "streamable-http"):
    _mcp_kwargs["host"] = "0.0.0.0"
    _mcp_kwargs["port"] = _port
    # Geheim pad als URL prefix zodat alleen wie de URL kent toegang heeft
    _mcp_kwargs["streamable_http_path"] = f"/{_secret_path}/mcp"
    _mcp_kwargs["sse_path"] = f"/{_secret_path}/sse"
    _mcp_kwargs["message_path"] = f"/{_secret_path}/messages/"

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


@mcp.tool()
def maak_categorie(naam: str, parent_id: int = 0, sortering: int = 0) -> str:
    """Maak een nieuwe productcategorie aan in OnlineFact.

    Args:
        naam: Categorienaam (bijv. 'Bakkerij')
        parent_id: Bovenliggende categorie ID (0 = hoofdcategorie)
        sortering: Sorteervolgorde (0 = standaard)
    """
    try:
        result = api.create_category(name=naam, parent_id=parent_id, sort_order=sortering)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij aanmaken categorie: {e}"


@mcp.tool()
def update_categorie(categorie_id: int, velden: str) -> str:
    """Wijzig een bestaande categorie in OnlineFact.

    Args:
        categorie_id: Het categorie ID
        velden: JSON string met te wijzigen velden, bijv. '{"name": "Nieuwe Naam", "sort_order": 5}'
            Mogelijke velden: name, parent_id, sort_order
    """
    try:
        fields = json.loads(velden)
        result = api.update_category(categorie_id, **fields)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {velden}"
    except Exception as e:
        return f"Fout bij updaten categorie {categorie_id}: {e}"


@mcp.tool()
def verwijder_categorie(categorie_id: int) -> str:
    """Verwijder een categorie uit OnlineFact. LET OP: dit is permanent!

    Args:
        categorie_id: Het categorie ID om te verwijderen
    """
    try:
        api.delete_category(categorie_id)
        return f"Categorie {categorie_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen categorie {categorie_id}: {e}"


@mcp.tool()
def maak_merk(naam: str) -> str:
    """Maak een nieuw merk aan in OnlineFact.

    Args:
        naam: Merknaam (bijv. 'HARIBO')
    """
    try:
        result = api.create_brand(name=naam)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij aanmaken merk: {e}"


@mcp.tool()
def update_merk(merk_id: int, naam: str) -> str:
    """Wijzig een bestaand merk in OnlineFact.

    Args:
        merk_id: Het merk ID
        naam: Nieuwe merknaam
    """
    try:
        result = api.update_brand(merk_id, name=naam)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij updaten merk {merk_id}: {e}"


@mcp.tool()
def verwijder_merk(merk_id: int) -> str:
    """Verwijder een merk uit OnlineFact. LET OP: dit is permanent!

    Args:
        merk_id: Het merk ID om te verwijderen
    """
    try:
        api.delete_brand(merk_id)
        return f"Merk {merk_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen merk {merk_id}: {e}"


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


# ── EXTRA TOOLS: ZOEKEN & BEHEER ─────────────────────────────

@mcp.tool()
def zoek_klant(zoekterm: str) -> str:
    """Zoek klanten op naam in OnlineFact.

    Args:
        zoekterm: Klantnaam of deel van de naam (bijv. 'Ahmed')
    """
    try:
        results = api.list_customers(limit=100, name=zoekterm)
        if not results:
            return f"Geen klanten gevonden voor '{zoekterm}'"
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij zoeken klant: {e}"


@mcp.tool()
def verwijder_product(product_id: int) -> str:
    """Verwijder een product uit OnlineFact. LET OP: dit is permanent!

    Args:
        product_id: Het product ID om te verwijderen
    """
    try:
        api.delete_product(product_id)
        return f"Product {product_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen product {product_id}: {e}"


@mcp.tool()
def zoek_factuur(zoekterm: str = "", min_bedrag: float = 0, max_bedrag: float = 0,
                 van_datum: str = "", tot_datum: str = "") -> str:
    """Zoek facturen op klantnaam, bedrag of datum.

    Args:
        zoekterm: Zoek op referentie of klantnaam (optioneel)
        min_bedrag: Minimum bedrag filter (0 = geen filter)
        max_bedrag: Maximum bedrag filter (0 = geen filter)
        van_datum: Startdatum YYYY-MM-DD (optioneel)
        tot_datum: Einddatum YYYY-MM-DD (optioneel)
    """
    try:
        params = {}
        if zoekterm:
            params["reference"] = zoekterm
        results = api.list_documents(
            document_type=3, page=1, limit=50,
            min_date=van_datum if van_datum else None,
            max_date=tot_datum if tot_datum else None,
            **params,
        )
        # Filter op bedrag client-side als nodig
        if (min_bedrag or max_bedrag) and isinstance(results, list):
            filtered = []
            for doc in results:
                total = float(doc.get("total_incl", 0) or 0)
                if min_bedrag and total < min_bedrag:
                    continue
                if max_bedrag and total > max_bedrag:
                    continue
                filtered.append(doc)
            results = filtered
        if not results:
            return "Geen facturen gevonden met deze criteria."
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij zoeken facturen: {e}"


@mcp.tool()
def bulk_prijs_update(product_ids: str, nieuwe_prijs: float = 0,
                      percentage: float = 0) -> str:
    """Wijzig de prijs van meerdere producten tegelijk.

    Args:
        product_ids: Komma-gescheiden product IDs, bijv. '101,102,103'
        nieuwe_prijs: Vaste nieuwe prijs incl BTW (0 = gebruik percentage)
        percentage: Prijsverhoging/verlaging in %, bijv. 10 voor +10%, -5 voor -5%
    """
    try:
        ids = [int(x.strip()) for x in product_ids.split(",")]
        resultaten = []
        for pid in ids:
            try:
                if nieuwe_prijs > 0:
                    api.update_product(pid, price_incl=nieuwe_prijs)
                    resultaten.append(f"Product {pid}: prijs → €{nieuwe_prijs:.2f}")
                elif percentage != 0:
                    product = api.get_product(pid)
                    huidige = float(product.get("price_incl", 0))
                    nieuw = round(huidige * (1 + percentage / 100), 2)
                    api.update_product(pid, price_incl=nieuw)
                    resultaten.append(f"Product {pid}: €{huidige:.2f} → €{nieuw:.2f} ({percentage:+.1f}%)")
                else:
                    resultaten.append(f"Product {pid}: geen wijziging (geef prijs of percentage op)")
            except Exception as e:
                resultaten.append(f"Product {pid}: FOUT - {e}")
        return "\n".join(resultaten)
    except Exception as e:
        return f"Fout bij bulk update: {e}"


# ── EXTRA TOOLS: ANALYSE & RAPPORTEN ─────────────────────────

@mcp.tool()
def dagomzet(datum: str = "") -> str:
    """Snelle samenvatting van de omzet voor een dag (standaard vandaag).

    Args:
        datum: Datum YYYY-MM-DD (leeg = vandaag)
    """
    try:
        if not datum:
            datum = datetime.now().strftime("%Y-%m-%d")
        totals = api.get_sale_totals(min_date=datum, max_date=datum)
        tickets = api.list_documents(document_type=8, min_date=datum, max_date=datum, limit=1)
        facturen = api.list_documents(document_type=3, min_date=datum, max_date=datum, limit=1)
        n_tickets = len(tickets) if isinstance(tickets, list) else 0
        n_facturen = len(facturen) if isinstance(facturen, list) else 0
        lines = [
            f"📊 Dagomzet {datum}",
            f"{'='*30}",
            json.dumps(totals, indent=2, ensure_ascii=False),
            f"Tickets: {n_tickets}",
            f"Facturen: {n_facturen}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Fout bij ophalen dagomzet: {e}"


@mcp.tool()
def voorraad_overzicht(alleen_laag: bool = True, drempel: int = 5) -> str:
    """Toon voorraadoverzicht, optioneel alleen producten met lage voorraad.

    Args:
        alleen_laag: True = alleen producten met voorraad <= drempel
        drempel: Voorraaddrempel (standaard 5)
    """
    try:
        alle_producten = []
        page = 1
        while True:
            batch = api.list_products(page=page, limit=100)
            if not batch:
                break
            if isinstance(batch, list):
                alle_producten.extend(batch)
                if len(batch) < 100:
                    break
            else:
                break
            page += 1
            if page > 20:  # Veiligheidsgrens
                break
        if alleen_laag:
            gefilterd = [p for p in alle_producten
                         if int(p.get("stock", 0) or 0) <= drempel
                         and p.get("managestock", False)]
            if not gefilterd:
                return f"Alle producten hebben meer dan {drempel} op voorraad."
            result = [{"id": p.get("id"), "reference": p.get("reference"),
                       "description": p.get("description"), "stock": p.get("stock")}
                      for p in gefilterd]
        else:
            result = [{"id": p.get("id"), "reference": p.get("reference"),
                       "description": p.get("description"), "stock": p.get("stock"),
                       "managestock": p.get("managestock")}
                      for p in alle_producten]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen voorraad: {e}"


@mcp.tool()
def winstmarge(product_id: int = 0, categorie_id: int = 0) -> str:
    """Bereken winstmarge voor een product of hele categorie.

    Args:
        product_id: Specifiek product ID (0 = alle/categorie)
        categorie_id: Filter op categorie (0 = alle)
    """
    try:
        if product_id:
            p = api.get_product(product_id)
            verkoop = float(p.get("price_incl", 0) or 0)
            btw = float(p.get("tax", 6) or 6)
            verkoop_excl = verkoop / (1 + btw / 100)
            inkoop = float(p.get("purchaseprice_excl", 0) or 0)
            marge = verkoop_excl - inkoop
            pct = (marge / inkoop * 100) if inkoop > 0 else 0
            return (f"Product: {p.get('description')}\n"
                    f"Verkoop incl: €{verkoop:.2f} (excl: €{verkoop_excl:.2f})\n"
                    f"Inkoop excl: €{inkoop:.2f}\n"
                    f"Marge: €{marge:.2f} ({pct:.1f}%)")
        # Meerdere producten
        producten = api.list_products(page=1, limit=100)
        if not isinstance(producten, list):
            return "Kan producten niet ophalen."
        if categorie_id:
            producten = [p for p in producten if p.get("categorie_id") == categorie_id]
        result = []
        for p in producten:
            verkoop = float(p.get("price_incl", 0) or 0)
            btw = float(p.get("tax", 6) or 6)
            verkoop_excl = verkoop / (1 + btw / 100)
            inkoop = float(p.get("purchaseprice_excl", 0) or 0)
            marge = verkoop_excl - inkoop
            pct = (marge / inkoop * 100) if inkoop > 0 else 0
            result.append({
                "id": p.get("id"), "description": p.get("description"),
                "verkoop_incl": verkoop, "inkoop_excl": inkoop,
                "marge": round(marge, 2), "marge_pct": round(pct, 1),
            })
        result.sort(key=lambda x: x["marge_pct"], reverse=True)
        return json.dumps(result[:50], indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij marge berekening: {e}"


@mcp.tool()
def top_producten(periode: str = "maand", aantal: int = 10) -> str:
    """Toon best verkochte producten voor een periode.

    Args:
        periode: 'vandaag', 'week', 'maand', 'jaar' of custom 'YYYY-MM-DD,YYYY-MM-DD'
        aantal: Aantal top producten (standaard 10)
    """
    try:
        van, tot = _parse_periode(periode)
        result = api.get_sales_per_product(min_date=van, max_date=tot, limit=aantal)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen top producten: {e}"


@mcp.tool()
def flop_producten(periode: str = "maand", aantal: int = 10) -> str:
    """Toon minst verkochte producten (producten met laagste omzet).

    Args:
        periode: 'vandaag', 'week', 'maand', 'jaar' of custom 'YYYY-MM-DD,YYYY-MM-DD'
        aantal: Aantal flop producten (standaard 10)
    """
    try:
        van, tot = _parse_periode(periode)
        # Haal veel producten op en sorteer omgekeerd
        result = api.get_sales_per_product(min_date=van, max_date=tot, limit=100)
        if isinstance(result, list):
            result.sort(key=lambda x: float(x.get("total_incl", 0) or 0))
            result = result[:aantal]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen flop producten: {e}"


@mcp.tool()
def btw_rapport(van_datum: str, tot_datum: str) -> str:
    """BTW overzicht per tarief (6% en 21%) voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        totals = api.get_sale_totals(min_date=van_datum, max_date=tot_datum)
        # Haal ook verkoop per product voor BTW-splits
        per_product = api.get_sales_per_product(
            min_date=van_datum, max_date=tot_datum, limit=100
        )
        btw_6 = {"omzet_incl": 0, "btw": 0, "producten": 0}
        btw_21 = {"omzet_incl": 0, "btw": 0, "producten": 0}
        btw_overig = {"omzet_incl": 0, "btw": 0, "producten": 0}
        if isinstance(per_product, list):
            for p in per_product:
                omzet = float(p.get("total_incl", 0) or 0)
                tax = float(p.get("tax", 6) or 6)
                btw_bedrag = omzet - (omzet / (1 + tax / 100))
                if tax == 6:
                    btw_6["omzet_incl"] += omzet
                    btw_6["btw"] += btw_bedrag
                    btw_6["producten"] += 1
                elif tax == 21:
                    btw_21["omzet_incl"] += omzet
                    btw_21["btw"] += btw_bedrag
                    btw_21["producten"] += 1
                else:
                    btw_overig["omzet_incl"] += omzet
                    btw_overig["btw"] += btw_bedrag
                    btw_overig["producten"] += 1
        for d in (btw_6, btw_21, btw_overig):
            d["omzet_incl"] = round(d["omzet_incl"], 2)
            d["btw"] = round(d["btw"], 2)
        rapport = {
            "periode": f"{van_datum} tot {tot_datum}",
            "totalen": totals,
            "btw_6_pct": btw_6,
            "btw_21_pct": btw_21,
            "btw_overig": btw_overig,
            "totaal_btw": round(btw_6["btw"] + btw_21["btw"] + btw_overig["btw"], 2),
        }
        return json.dumps(rapport, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij BTW rapport: {e}"


# ── KLANTBEHEER (uitgebreid) ──────────────────────────────────

@mcp.tool()
def update_klant(klant_id: int, velden: str) -> str:
    """Wijzig een bestaande klant in OnlineFact.

    Args:
        klant_id: Het klant ID
        velden: JSON string met te wijzigen velden, bijv. '{"name": "Nieuwe Naam", "discount": 10, "email": "info@test.be"}'
            Mogelijke velden: name, address, address2, zip, city, country_id, phone, mobile,
            email, taxnr, discount, priceniveau, type (1=klant, 2=leverancier)
    """
    try:
        fields = json.loads(velden)
        result = api.update_customer(klant_id, **fields)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {velden}"
    except Exception as e:
        return f"Fout bij updaten klant {klant_id}: {e}"


@mcp.tool()
def verwijder_klant(klant_id: int) -> str:
    """Verwijder een klant uit OnlineFact. LET OP: dit is permanent!

    Args:
        klant_id: Het klant ID om te verwijderen
    """
    try:
        api.delete_customer(klant_id)
        return f"Klant {klant_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen klant {klant_id}: {e}"


# ── FACTUURBEHEER (uitgebreid) ───────────────────────────────

@mcp.tool()
def update_factuur(document_id: int, velden: str) -> str:
    """Wijzig een bestaand document/factuur in OnlineFact.

    Args:
        document_id: Het document ID
        velden: JSON string met te wijzigen velden, bijv. '{"payment_method": 2}'
            Mogelijke velden: payment_method (1=onbetaald, 2=cash, 3=overschrijving, 4=creditcard, 6=bancontact),
            reference, customer_id
    """
    try:
        fields = json.loads(velden)
        result = api.update_document(document_id, **fields)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {velden}"
    except Exception as e:
        return f"Fout bij updaten document {document_id}: {e}"


@mcp.tool()
def verwijder_factuur(document_id: int) -> str:
    """Verwijder een document/factuur uit OnlineFact. LET OP: dit is permanent!

    Args:
        document_id: Het document ID om te verwijderen
    """
    try:
        api.delete_document(document_id)
        return f"Document {document_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen document {document_id}: {e}"


@mcp.tool()
def openstaande_facturen(klant_id: int = 0) -> str:
    """Toon alle onbetaalde facturen, optioneel gefilterd op klant.

    Args:
        klant_id: Filter op klant ID (0 = alle klanten)
    """
    try:
        alle_facturen = []
        page = 1
        while page <= 10:
            batch = api.list_documents(document_type=3, page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_facturen.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        # Filter op onbetaald (payment_method == 1)
        openstaand = [f for f in alle_facturen
                      if str(f.get("payment_method", "1")) == "1"]
        if klant_id:
            openstaand = [f for f in openstaand
                          if str(f.get("customer_id", "0")) == str(klant_id)]
        if not openstaand:
            return "Geen openstaande facturen gevonden."
        totaal = sum(float(f.get("total_incl", 0) or 0) for f in openstaand)
        result = {
            "aantal": len(openstaand),
            "totaal_openstaand": round(totaal, 2),
            "facturen": [{
                "id": f.get("id"),
                "datum": f.get("document_date"),
                "klant": f.get("customer_name", f.get("customer_id")),
                "bedrag_incl": f.get("total_incl"),
                "referentie": f.get("reference"),
            } for f in openstaand]
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen openstaande facturen: {e}"


# ── LEVERANCIERS ─────────────────────────────────────────────

@mcp.tool()
def lijst_leveranciers() -> str:
    """Toon alle leveranciers (klanten met type=2) in OnlineFact."""
    try:
        alle_klanten = []
        page = 1
        while page <= 10:
            batch = api.list_customers(page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_klanten.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        leveranciers = [k for k in alle_klanten if str(k.get("type", "1")) == "2"]
        if not leveranciers:
            return "Geen leveranciers gevonden."
        result = [{
            "id": k.get("customer_id"),
            "naam": k.get("name"),
            "btw_nr": k.get("taxnr"),
            "adres": f"{k.get('address', '')} {k.get('zip', '')} {k.get('city', '')}".strip(),
            "email": k.get("email"),
            "telefoon": k.get("phone") or k.get("mobile"),
        } for k in leveranciers]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen leveranciers: {e}"


# ── LEVERANCIER CRUD ────────────────────────────────────────

@mcp.tool()
def maak_leverancier(
    naam: str,
    btw_nr: str = "",
    adres: str = "",
    postcode: str = "",
    stad: str = "",
    email: str = "",
    telefoon: str = "",
) -> str:
    """Maak een nieuwe leverancier aan in OnlineFact.

    Args:
        naam: Bedrijfsnaam leverancier
        btw_nr: BTW-nummer (bijv. 'BE0123456789')
        adres: Straat en huisnummer
        postcode: Postcode
        stad: Stad/gemeente
        email: E-mailadres
        telefoon: Telefoonnummer
    """
    try:
        kwargs = {"type": 2}  # type 2 = leverancier
        if btw_nr:
            kwargs["taxnr"] = btw_nr
        if adres:
            kwargs["address"] = adres
        if postcode:
            kwargs["zip"] = postcode
        if stad:
            kwargs["city"] = stad
        if email:
            kwargs["email"] = email
        if telefoon:
            kwargs["phone"] = telefoon
        result = api.create_customer(name=naam, **kwargs)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij aanmaken leverancier: {e}"


@mcp.tool()
def update_leverancier(leverancier_id: int, velden: str) -> str:
    """Wijzig een bestaande leverancier in OnlineFact.

    Args:
        leverancier_id: Het leverancier/klant ID
        velden: JSON string met te wijzigen velden, bijv. '{"name": "Nieuwe Naam", "email": "info@nieuw.be"}'
            Mogelijke velden: name, address, zip, city, phone, mobile, email, taxnr
    """
    try:
        fields = json.loads(velden)
        result = api.update_customer(leverancier_id, **fields)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {velden}"
    except Exception as e:
        return f"Fout bij updaten leverancier {leverancier_id}: {e}"


@mcp.tool()
def verwijder_leverancier(leverancier_id: int) -> str:
    """Verwijder een leverancier uit OnlineFact. LET OP: dit is permanent!

    Args:
        leverancier_id: Het leverancier/klant ID om te verwijderen
    """
    try:
        api.delete_customer(leverancier_id)
        return f"Leverancier {leverancier_id} is verwijderd."
    except Exception as e:
        return f"Fout bij verwijderen leverancier {leverancier_id}: {e}"


@mcp.tool()
def zoek_leverancier(zoekterm: str) -> str:
    """Zoek leveranciers op naam in OnlineFact.

    Args:
        zoekterm: Leveranciersnaam of deel ervan (bijv. 'EGE FOOD')
    """
    try:
        results = api.list_customers(limit=100, name=zoekterm)
        if isinstance(results, list):
            results = [k for k in results if str(k.get("type", "1")) == "2"]
        if not results:
            return f"Geen leveranciers gevonden voor '{zoekterm}'"
        formatted = [{
            "id": k.get("customer_id"),
            "naam": k.get("name"),
            "btw_nr": k.get("taxnr"),
            "adres": f"{k.get('address', '')} {k.get('zip', '')} {k.get('city', '')}".strip(),
            "email": k.get("email"),
            "telefoon": k.get("phone") or k.get("mobile"),
        } for k in results]
        return json.dumps(formatted, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij zoeken leverancier: {e}"


# ── VOORRAAD MUTATIES ──────────────────────────────────────

@mcp.tool()
def voorraad_correctie(product_id: int, nieuwe_voorraad: float) -> str:
    """Pas de voorraad van een product handmatig aan (correctie/telling).

    Args:
        product_id: Het product ID
        nieuwe_voorraad: De nieuwe voorraadstand (bijv. 50)
    """
    try:
        # Haal huidige voorraad op voor logging
        product = api.get_product(product_id)
        oude_voorraad = float(product.get("stock", 0) or 0)
        naam = product.get("description", "Onbekend")
        result = api.update_product(product_id, stock=nieuwe_voorraad)
        verschil = nieuwe_voorraad - oude_voorraad
        return (f"Voorraad aangepast: {naam}\n"
                f"  Oud: {oude_voorraad}\n"
                f"  Nieuw: {nieuwe_voorraad}\n"
                f"  Verschil: {verschil:+.0f}")
    except Exception as e:
        return f"Fout bij voorraadcorrectie product {product_id}: {e}"


@mcp.tool()
def voorraad_bulk_correctie(correcties: str) -> str:
    """Pas voorraad aan voor meerdere producten tegelijk (bijv. na telling).

    Args:
        correcties: JSON array met correcties, bijv. '[{"product_id": 5, "voorraad": 100}, {"product_id": 14, "voorraad": 50}]'
    """
    try:
        items = json.loads(correcties)
        resultaten = []
        for item in items:
            pid = item.get("product_id")
            nieuwe = item.get("voorraad", item.get("stock", 0))
            try:
                product = api.get_product(pid)
                oude = float(product.get("stock", 0) or 0)
                naam = product.get("description", "Onbekend")
                api.update_product(pid, stock=nieuwe)
                verschil = nieuwe - oude
                resultaten.append(f"OK: {naam} (#{pid}): {oude} → {nieuwe} ({verschil:+.0f})")
            except Exception as e:
                resultaten.append(f"FOUT: Product #{pid}: {e}")
        return "\n".join(resultaten)
    except json.JSONDecodeError:
        return f"Ongeldige JSON: {correcties}"
    except Exception as e:
        return f"Fout bij bulk correctie: {e}"


@mcp.tool()
def voorraad_bijvullen_advies(drempel: int = 10, min_verkoop: int = 1) -> str:
    """Genereer een besteladvies: welke producten moeten bijbesteld worden.

    Args:
        drempel: Voorraaddrempel - producten met minder worden geadviseerd (standaard 10)
        min_verkoop: Minimale verkoop in afgelopen maand om relevant te zijn (standaard 1)
    """
    try:
        # Haal alle producten op
        alle_producten = []
        page = 1
        while page <= 20:
            batch = api.list_products(page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_producten.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        # Haal verkoop afgelopen maand op
        vandaag = datetime.now()
        maand_geleden = (vandaag - timedelta(days=30)).strftime("%Y-%m-%d")
        vandaag_str = vandaag.strftime("%Y-%m-%d")
        verkoop = api.get_sales_per_product(min_date=maand_geleden, max_date=vandaag_str, limit=100)
        verkoop_map = {}
        if isinstance(verkoop, list):
            for v in verkoop:
                pid = str(v.get("product_id", ""))
                verkoop_map[pid] = float(v.get("quantity", 0) or 0)
        # Filter en bouw advies
        advies = []
        for p in alle_producten:
            stock = float(p.get("stock", 0) or 0)
            pid = str(p.get("product_id", p.get("id", "")))
            verkocht = verkoop_map.get(pid, 0)
            if stock <= drempel and p.get("managestock") and verkocht >= min_verkoop:
                advies.append({
                    "product_id": pid,
                    "naam": p.get("description"),
                    "referentie": p.get("reference"),
                    "huidige_voorraad": stock,
                    "verkocht_30d": verkocht,
                    "leverancier": p.get("supplier", ""),
                    "advies_bestellen": max(int(verkocht * 2 - stock), 10),
                })
        advies.sort(key=lambda x: x["huidige_voorraad"])
        if not advies:
            return f"Alle producten hebben voldoende voorraad (>{drempel})."
        return json.dumps(advies, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij besteladvies: {e}"


# ── CREDITNOTA & RETOUREN ──────────────────────────────────

@mcp.tool()
def maak_creditnota(
    regels: str,
    klant_id: int = 0,
    referentie: str = "",
    origineel_factuur_id: int = 0,
) -> str:
    """Maak een creditnota aan (voor retouren/correcties).

    Args:
        regels: JSON array met creditnota regels, bijv. '[{"reference":"P001","quantity":1,"description":"Retour Appel","price_vatexcl":1.50,"tax":6}]'
        klant_id: Klant ID (0 = geen klant)
        referentie: Eigen referentie/reden (bijv. 'Retour - beschadigd')
        origineel_factuur_id: Originele factuur ID ter referentie (optioneel)
    """
    try:
        lines = json.loads(regels)
        ref = referentie
        if origineel_factuur_id:
            ref = f"CN van factuur #{origineel_factuur_id}" + (f" - {referentie}" if referentie else "")
        result = api.create_document(
            document_type=4,  # 4 = creditnota
            lines=lines,
            customer_id=klant_id if klant_id else None,
            reference=ref if ref else None,
            payment_method=1,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON voor regels: {regels}"
    except Exception as e:
        return f"Fout bij aanmaken creditnota: {e}"


# ── BESTELLINGEN (INKOOP) ──────────────────────────────────

@mcp.tool()
def maak_bestelling(
    leverancier_id: int,
    regels: str,
    referentie: str = "",
    datum: str = "",
) -> str:
    """Maak een inkoopbestelling aan bij een leverancier.

    Args:
        leverancier_id: Leverancier/klant ID
        regels: JSON array met bestelregels, bijv. '[{"reference":"P001","quantity":24,"description":"Gummy Bears","price_vatexcl":0.63,"tax":6}]'
        referentie: Eigen referentie/bestelnummer (optioneel)
        datum: Besteldatum YYYY-MM-DD (leeg = vandaag)
    """
    try:
        lines = json.loads(regels)
        result = api.create_document(
            document_type=2,  # 2 = bestelling
            lines=lines,
            customer_id=leverancier_id,
            document_date=datum if datum else None,
            reference=referentie if referentie else None,
            payment_method=1,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON voor regels: {regels}"
    except Exception as e:
        return f"Fout bij aanmaken bestelling: {e}"


@mcp.tool()
def lijst_bestellingen(
    leverancier_id: int = 0,
    van_datum: str = "",
    tot_datum: str = "",
    pagina: int = 1,
    aantal: int = 50,
) -> str:
    """Toon bestellingen (inkooporders), optioneel gefilterd op leverancier.

    Args:
        leverancier_id: Filter op leverancier ID (0 = alle)
        van_datum: Startdatum YYYY-MM-DD (optioneel)
        tot_datum: Einddatum YYYY-MM-DD (optioneel)
        pagina: Paginanummer
        aantal: Aantal per pagina
    """
    try:
        results = api.list_documents(
            document_type=2,  # 2 = bestelling
            page=pagina,
            limit=min(aantal, 100),
            min_date=van_datum if van_datum else None,
            max_date=tot_datum if tot_datum else None,
        )
        if leverancier_id and isinstance(results, list):
            results = [d for d in results
                       if str(d.get("customer_id", "0")) == str(leverancier_id)]
        if not results:
            return "Geen bestellingen gevonden."
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen bestellingen: {e}"


@mcp.tool()
def maak_offerte(
    klant_id: int,
    regels: str,
    referentie: str = "",
    datum: str = "",
) -> str:
    """Maak een offerte aan voor een klant.

    Args:
        klant_id: Klant ID
        regels: JSON array met offerteregels, bijv. '[{"reference":"P001","quantity":10,"description":"Gummy Bears","price_vatexcl":0.84,"tax":6}]'
        referentie: Eigen referentie (optioneel)
        datum: Offertedatum YYYY-MM-DD (leeg = vandaag)
    """
    try:
        lines = json.loads(regels)
        result = api.create_document(
            document_type=1,  # 1 = offerte
            lines=lines,
            customer_id=klant_id,
            document_date=datum if datum else None,
            reference=referentie if referentie else None,
            payment_method=1,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON voor regels: {regels}"
    except Exception as e:
        return f"Fout bij aanmaken offerte: {e}"


@mcp.tool()
def maak_leveringsbon(
    klant_id: int,
    regels: str,
    referentie: str = "",
    datum: str = "",
) -> str:
    """Maak een leveringsbon aan.

    Args:
        klant_id: Klant ID
        regels: JSON array met leveringsregels
        referentie: Eigen referentie (optioneel)
        datum: Leveringsdatum YYYY-MM-DD (leeg = vandaag)
    """
    try:
        lines = json.loads(regels)
        result = api.create_document(
            document_type=5,  # 5 = leveringsbon
            lines=lines,
            customer_id=klant_id,
            document_date=datum if datum else None,
            reference=referentie if referentie else None,
            payment_method=1,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return f"Ongeldige JSON voor regels: {regels}"
    except Exception as e:
        return f"Fout bij aanmaken leveringsbon: {e}"


# ── FACTUUR PDF ────────────────────────────────────────────

@mcp.tool()
def factuur_pdf_url(document_id: int) -> str:
    """Genereer de PDF download URL voor een factuur/document.

    Args:
        document_id: Het document/factuur ID
    """
    try:
        doc = api.get_document(document_id)
        # OnlineFact biedt PDF via standaard URL patroon
        pdf_url = f"{api.api_url}/documents/{document_id}/pdf/"
        doc_type_map = {1: "Offerte", 2: "Bestelling", 3: "Factuur",
                        4: "Creditnota", 5: "Leveringsbon", 8: "Ticket"}
        doc_type = doc_type_map.get(int(doc.get("document_type", 3)), "Document")
        return (f"{doc_type} #{document_id}\n"
                f"PDF URL: {pdf_url}\n"
                f"Datum: {doc.get('document_date', '?')}\n"
                f"Bedrag: €{doc.get('total_incl', '?')}")
    except Exception as e:
        return f"Fout bij ophalen PDF URL: {e}"


# ── KLANT/PRODUCT HISTORIE ─────────────────────────────────

@mcp.tool()
def klant_historie(klant_id: int, aantal_maanden: int = 3) -> str:
    """Toon aankoopgeschiedenis van een klant.

    Args:
        klant_id: Het klant ID
        aantal_maanden: Hoeveel maanden terug kijken (standaard 3)
    """
    try:
        vandaag = datetime.now()
        start = (vandaag - timedelta(days=aantal_maanden * 30)).strftime("%Y-%m-%d")
        eind = vandaag.strftime("%Y-%m-%d")
        # Haal klantgegevens op
        klant = api.get_customer(klant_id)
        naam = klant.get("name", "Onbekend")
        # Haal facturen op
        alle_docs = []
        page = 1
        while page <= 10:
            batch = api.list_documents(document_type=3, page=page, limit=100,
                                       min_date=start, max_date=eind)
            if not batch or not isinstance(batch, list):
                break
            alle_docs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        # Filter op klant
        klant_docs = [d for d in alle_docs
                      if str(d.get("customer_id", "0")) == str(klant_id)]
        totaal = sum(float(d.get("total_incl", 0) or 0) for d in klant_docs)
        result = {
            "klant": naam,
            "klant_id": klant_id,
            "periode": f"{start} t/m {eind}",
            "aantal_facturen": len(klant_docs),
            "totaal_besteed": round(totaal, 2),
            "facturen": [{
                "id": d.get("id"),
                "datum": d.get("document_date"),
                "bedrag_incl": d.get("total_incl"),
                "referentie": d.get("reference"),
                "betaalmethode": d.get("payment_method"),
            } for d in klant_docs]
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen klanthistorie: {e}"


@mcp.tool()
def product_verkoop_historie(product_id: int, aantal_maanden: int = 3) -> str:
    """Toon verkoopgeschiedenis van een specifiek product.

    Args:
        product_id: Het product ID
        aantal_maanden: Hoeveel maanden terug kijken (standaard 3)
    """
    try:
        product = api.get_product(product_id)
        naam = product.get("description", "Onbekend")
        vandaag = datetime.now()
        # Per maand omzet ophalen
        maand_data = []
        for i in range(aantal_maanden):
            ref = vandaag - timedelta(days=i * 30)
            m_start = f"{ref.year}-{ref.month:02d}-01"
            if ref.month == 12:
                m_end = f"{ref.year}-12-31"
            else:
                m_end = (datetime(ref.year, ref.month + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
            verkoop = api.get_sales_per_product(min_date=m_start, max_date=m_end, limit=100)
            product_verkoop = None
            if isinstance(verkoop, list):
                for v in verkoop:
                    if str(v.get("product_id", "")) == str(product_id):
                        product_verkoop = v
                        break
            maand_data.append({
                "maand": f"{ref.year}-{ref.month:02d}",
                "aantal_verkocht": float(product_verkoop.get("quantity", 0)) if product_verkoop else 0,
                "omzet_incl": float(product_verkoop.get("total_incl", 0)) if product_verkoop else 0,
            })
        result = {
            "product": naam,
            "product_id": product_id,
            "huidige_voorraad": product.get("stock"),
            "prijs_incl": product.get("price_incl"),
            "verkoop_per_maand": maand_data,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen producthistorie: {e}"


# ── EXTRA RAPPORTEN ──────────────────────────────────────────

@mcp.tool()
def omzet_per_categorie(van_datum: str, tot_datum: str) -> str:
    """Toon omzet per productcategorie voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        per_product = api.get_sales_per_product(min_date=van_datum, max_date=tot_datum, limit=100)
        if not isinstance(per_product, list):
            return "Geen verkoopdata gevonden."
        # Haal categorieën op voor mapping
        categories = api.list_categories(limit=200)
        cat_map = {}
        if isinstance(categories, list):
            cat_map = {str(c["category_id"]): c["name"] for c in categories}
        # Groepeer per categorie
        cat_totals = {}
        for p in per_product:
            cat_id = str(p.get("categorie_id", "0") or "0")
            cat_name = cat_map.get(cat_id, "Geen categorie")
            if cat_name not in cat_totals:
                cat_totals[cat_name] = {"omzet_incl": 0, "aantal_producten": 0}
            cat_totals[cat_name]["omzet_incl"] += float(p.get("total_incl", 0) or 0)
            cat_totals[cat_name]["aantal_producten"] += 1
        # Sorteer op omzet
        result = [{"categorie": k, "omzet_incl": round(v["omzet_incl"], 2),
                    "aantal_producten": v["aantal_producten"]}
                   for k, v in sorted(cat_totals.items(),
                                      key=lambda x: x[1]["omzet_incl"], reverse=True)]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij omzet per categorie: {e}"


@mcp.tool()
def weekomzet(datum: str = "") -> str:
    """Snelle samenvatting van de omzet voor de huidige week.

    Args:
        datum: Datum binnen de gewenste week YYYY-MM-DD (leeg = deze week)
    """
    try:
        if datum:
            ref = datetime.strptime(datum, "%Y-%m-%d")
        else:
            ref = datetime.now()
        maandag = (ref - timedelta(days=ref.weekday())).strftime("%Y-%m-%d")
        zondag = (ref + timedelta(days=6 - ref.weekday())).strftime("%Y-%m-%d")
        totals = api.get_sale_totals(min_date=maandag, max_date=zondag)
        lines = [
            f"📊 Weekomzet {maandag} t/m {zondag}",
            f"{'='*35}",
            json.dumps(totals, indent=2, ensure_ascii=False),
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Fout bij ophalen weekomzet: {e}"


@mcp.tool()
def maandomzet(maand: int = 0, jaar: int = 0) -> str:
    """Snelle samenvatting van de omzet voor een maand.

    Args:
        maand: Maandnummer 1-12 (0 = huidige maand)
        jaar: Jaar YYYY (0 = huidig jaar)
    """
    try:
        nu = datetime.now()
        m = maand if maand else nu.month
        j = jaar if jaar else nu.year
        van = f"{j}-{m:02d}-01"
        if m == 12:
            tot = f"{j}-12-31"
        else:
            tot = (datetime(j, m + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
        totals = api.get_sale_totals(min_date=van, max_date=tot)
        lines = [
            f"📊 Maandomzet {m:02d}/{j}",
            f"{'='*30}",
            json.dumps(totals, indent=2, ensure_ascii=False),
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Fout bij ophalen maandomzet: {e}"


@mcp.tool()
def vergelijk_periodes(periode1_van: str, periode1_tot: str,
                       periode2_van: str, periode2_tot: str) -> str:
    """Vergelijk omzet tussen twee periodes (bijv. deze maand vs vorige maand).

    Args:
        periode1_van: Startdatum periode 1 (YYYY-MM-DD)
        periode1_tot: Einddatum periode 1 (YYYY-MM-DD)
        periode2_van: Startdatum periode 2 (YYYY-MM-DD)
        periode2_tot: Einddatum periode 2 (YYYY-MM-DD)
    """
    try:
        totals1 = api.get_sale_totals(min_date=periode1_van, max_date=periode1_tot)
        totals2 = api.get_sale_totals(min_date=periode2_van, max_date=periode2_tot)
        # Probeer numerieke vergelijking
        def _extract_total(t):
            if isinstance(t, dict):
                return float(t.get("total_incl", 0) or t.get("total", 0) or 0)
            if isinstance(t, list) and t:
                return float(t[0].get("total_incl", 0) or 0)
            return 0
        t1 = _extract_total(totals1)
        t2 = _extract_total(totals2)
        verschil = t1 - t2
        pct = ((t1 - t2) / t2 * 100) if t2 != 0 else 0
        result = {
            "periode_1": {"van": periode1_van, "tot": periode1_tot, "data": totals1},
            "periode_2": {"van": periode2_van, "tot": periode2_tot, "data": totals2},
            "verschil": round(verschil, 2),
            "verschil_pct": round(pct, 1),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij vergelijken periodes: {e}"


@mcp.tool()
def voorraad_waarde() -> str:
    """Bereken de totale voorraadwaarde (inkoop- en verkoopwaarde)."""
    try:
        alle_producten = []
        page = 1
        while page <= 20:
            batch = api.list_products(page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_producten.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        inkoop_waarde = 0
        verkoop_waarde = 0
        producten_met_voorraad = 0
        for p in alle_producten:
            stock = float(p.get("stock", 0) or 0)
            if stock > 0:
                producten_met_voorraad += 1
                inkoop = float(p.get("purchaseprice_excl", 0) or 0)
                verkoop = float(p.get("price_incl", 0) or 0)
                inkoop_waarde += stock * inkoop
                verkoop_waarde += stock * verkoop
        result = {
            "totaal_producten": len(alle_producten),
            "producten_met_voorraad": producten_met_voorraad,
            "inkoop_waarde_excl": round(inkoop_waarde, 2),
            "verkoop_waarde_incl": round(verkoop_waarde, 2),
            "potentiele_winst": round(verkoop_waarde - inkoop_waarde, 2),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij berekenen voorraadwaarde: {e}"


@mcp.tool()
def negatieve_voorraad() -> str:
    """Toon producten met negatieve voorraad (mogelijke fouten in het systeem)."""
    try:
        alle_producten = []
        page = 1
        while page <= 20:
            batch = api.list_products(page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_producten.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        negatief = [p for p in alle_producten if float(p.get("stock", 0) or 0) < 0]
        if not negatief:
            return "Geen producten met negatieve voorraad gevonden."
        result = [{"id": p.get("id"), "reference": p.get("reference"),
                    "description": p.get("description"), "stock": p.get("stock"),
                    "categorie_id": p.get("categorie_id")}
                   for p in negatief]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen negatieve voorraad: {e}"


# ── JAAROMZET & GEAVANCEERDE RAPPORTEN ───────────────────────

@mcp.tool()
def jaaromzet(jaar: int = 0) -> str:
    """Toon omzet per maand voor een heel jaar.

    Args:
        jaar: Jaar (0 = huidig jaar)
    """
    try:
        j = jaar if jaar else datetime.now().year
        maanden = []
        totaal_jaar = 0
        for m in range(1, 13):
            van = f"{j}-{m:02d}-01"
            if m == 12:
                tot = f"{j}-12-31"
            else:
                tot = (datetime(j, m + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
            # Sla toekomstige maanden over
            if datetime(j, m, 1) > datetime.now():
                break
            try:
                totals = api.get_sale_totals(min_date=van, max_date=tot)
                omzet = 0
                if isinstance(totals, dict):
                    omzet = float(totals.get("total_incl", 0) or 0)
                elif isinstance(totals, list) and totals:
                    omzet = float(totals[0].get("total_incl", 0) or 0)
                totaal_jaar += omzet
                maanden.append({"maand": f"{j}-{m:02d}", "omzet_incl": round(omzet, 2)})
            except Exception:
                maanden.append({"maand": f"{j}-{m:02d}", "omzet_incl": 0, "fout": True})
        result = {
            "jaar": j,
            "totaal_omzet_incl": round(totaal_jaar, 2),
            "gemiddeld_per_maand": round(totaal_jaar / max(len(maanden), 1), 2),
            "per_maand": maanden,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen jaaromzet: {e}"


@mcp.tool()
def omzet_per_merk(van_datum: str, tot_datum: str) -> str:
    """Toon omzet per merk voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        per_product = api.get_sales_per_product(min_date=van_datum, max_date=tot_datum, limit=100)
        if not isinstance(per_product, list):
            return "Geen verkoopdata gevonden."
        # Haal merken op voor mapping
        brands = api.list_brands(limit=200)
        brand_map = {}
        if isinstance(brands, list):
            brand_map = {str(b["brand_id"]): b["name"] for b in brands}
        # Groepeer per merk
        merk_totals = {}
        for p in per_product:
            brand_id = str(p.get("brand_id", "0") or "0")
            brand_name = brand_map.get(brand_id, "Geen merk")
            if brand_name not in merk_totals:
                merk_totals[brand_name] = {"omzet_incl": 0, "aantal_producten": 0, "aantal_verkocht": 0}
            merk_totals[brand_name]["omzet_incl"] += float(p.get("total_incl", 0) or 0)
            merk_totals[brand_name]["aantal_producten"] += 1
            merk_totals[brand_name]["aantal_verkocht"] += float(p.get("quantity", 0) or 0)
        result = [{"merk": k, "omzet_incl": round(v["omzet_incl"], 2),
                    "aantal_producten": v["aantal_producten"],
                    "stuks_verkocht": round(v["aantal_verkocht"], 1)}
                   for k, v in sorted(merk_totals.items(),
                                      key=lambda x: x[1]["omzet_incl"], reverse=True)]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij omzet per merk: {e}"


@mcp.tool()
def klant_ranking(van_datum: str, tot_datum: str, aantal: int = 20) -> str:
    """Ranglijst van klanten op basis van besteed bedrag.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
        aantal: Aantal klanten in de top (standaard 20)
    """
    try:
        result = api.get_sales_per_relation(min_date=van_datum, max_date=tot_datum)
        if isinstance(result, list):
            result.sort(key=lambda x: float(x.get("total_incl", 0) or 0), reverse=True)
            result = result[:aantal]
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen klant ranking: {e}"


@mcp.tool()
def omzet_per_betaalmethode(van_datum: str, tot_datum: str) -> str:
    """Toon omzetverdeling per betaalmethode voor een periode.

    Args:
        van_datum: Startdatum (YYYY-MM-DD)
        tot_datum: Einddatum (YYYY-MM-DD)
    """
    try:
        methode_map = {
            "1": "Onbetaald", "2": "Cash", "3": "Overschrijving",
            "4": "Creditcard", "6": "Bancontact"
        }
        alle_docs = []
        page = 1
        while page <= 10:
            batch = api.list_documents(document_type=3, page=page, limit=100,
                                       min_date=van_datum, max_date=tot_datum)
            if not batch or not isinstance(batch, list):
                break
            alle_docs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        # Tickets ook meepakken
        page = 1
        while page <= 10:
            batch = api.list_documents(document_type=8, page=page, limit=100,
                                       min_date=van_datum, max_date=tot_datum)
            if not batch or not isinstance(batch, list):
                break
            alle_docs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        totals = {}
        for doc in alle_docs:
            methode = str(doc.get("payment_method", "1"))
            naam = methode_map.get(methode, f"Onbekend ({methode})")
            if naam not in totals:
                totals[naam] = {"aantal": 0, "omzet_incl": 0}
            totals[naam]["aantal"] += 1
            totals[naam]["omzet_incl"] += float(doc.get("total_incl", 0) or 0)
        result = [{"methode": k, "aantal": v["aantal"],
                    "omzet_incl": round(v["omzet_incl"], 2)}
                   for k, v in sorted(totals.items(),
                                      key=lambda x: x[1]["omzet_incl"], reverse=True)]
        totaal = sum(r["omzet_incl"] for r in result)
        for r in result:
            r["percentage"] = round(r["omzet_incl"] / totaal * 100, 1) if totaal else 0
        return json.dumps({"periode": f"{van_datum} t/m {tot_datum}",
                           "totaal": round(totaal, 2),
                           "per_methode": result}, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen omzet per betaalmethode: {e}"


@mcp.tool()
def document_overzicht(van_datum: str = "", tot_datum: str = "") -> str:
    """Toon een overzicht van alle documenttypes (offertes, bestellingen, facturen, etc.).

    Args:
        van_datum: Startdatum YYYY-MM-DD (optioneel)
        tot_datum: Einddatum YYYY-MM-DD (optioneel)
    """
    try:
        type_map = {1: "Offertes", 2: "Bestellingen", 3: "Facturen",
                    4: "Creditnota's", 5: "Leveringsbonnen", 8: "Tickets"}
        overzicht = []
        for doc_type, naam in type_map.items():
            try:
                docs = api.list_documents(
                    document_type=doc_type, page=1, limit=1,
                    min_date=van_datum if van_datum else None,
                    max_date=tot_datum if tot_datum else None,
                )
                aantal = len(docs) if isinstance(docs, list) else 0
                overzicht.append({"type": doc_type, "naam": naam, "aantal": aantal})
            except Exception:
                overzicht.append({"type": doc_type, "naam": naam, "aantal": "?"})
        return json.dumps(overzicht, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij ophalen document overzicht: {e}"


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


# ── HELPER FUNCTIES ──────────────────────────────────────────

def _parse_periode(periode: str) -> tuple:
    """Parse periode string naar (van_datum, tot_datum)."""
    vandaag = datetime.now()
    if "," in periode:
        parts = periode.split(",")
        return parts[0].strip(), parts[1].strip()
    elif periode == "vandaag":
        d = vandaag.strftime("%Y-%m-%d")
        return d, d
    elif periode == "week":
        start = (vandaag - timedelta(days=vandaag.weekday())).strftime("%Y-%m-%d")
        return start, vandaag.strftime("%Y-%m-%d")
    elif periode == "jaar":
        return f"{vandaag.year}-01-01", vandaag.strftime("%Y-%m-%d")
    else:  # maand (default)
        return f"{vandaag.year}-{vandaag.month:02d}-01", vandaag.strftime("%Y-%m-%d")


# ── MCP PROMPTS ──────────────────────────────────────────────

@mcp.prompt()
def maandrapport(maand: str = "", jaar: str = "") -> str:
    """Genereer een volledig maandrapport met omzet, top producten en klanten.

    Args:
        maand: Maandnummer 1-12 (leeg = huidige maand)
        jaar: Jaar YYYY (leeg = huidig jaar)
    """
    nu = datetime.now()
    m = int(maand) if maand else nu.month
    j = int(jaar) if jaar else nu.year
    return (
        f"Maak een volledig maandrapport voor Yilmaz Voeding XL voor {m:02d}/{j}.\n\n"
        f"Gebruik deze tools:\n"
        f"1. verkoop_totaal(van_datum='{j}-{m:02d}-01', tot_datum='{j}-{m:02d}-28')\n"
        f"2. top_producten(periode='{j}-{m:02d}-01,{j}-{m:02d}-28', aantal=15)\n"
        f"3. verkoop_per_klant(van_datum='{j}-{m:02d}-01', tot_datum='{j}-{m:02d}-28')\n"
        f"4. btw_rapport(van_datum='{j}-{m:02d}-01', tot_datum='{j}-{m:02d}-28')\n\n"
        f"Presenteer het als een overzichtelijk rapport met:\n"
        f"- Totale omzet en aantal transacties\n"
        f"- Top 15 best verkochte producten\n"
        f"- Omzet per klant\n"
        f"- BTW overzicht (6% vs 21%)\n"
        f"- Vergelijking met vorige maand als mogelijk"
    )


@mcp.prompt()
def inventaris_check() -> str:
    """Controleer de voorraad en geef waarschuwingen voor lage voorraad."""
    return (
        "Doe een volledige inventariscontrole voor Yilmaz Voeding XL.\n\n"
        "Gebruik deze tools:\n"
        "1. voorraad_overzicht(alleen_laag=True, drempel=5)\n"
        "2. lijst_producten(pagina=1, aantal=100)\n\n"
        "Geef een overzicht van:\n"
        "- Producten met lage voorraad (≤5 stuks) - URGENT\n"
        "- Producten zonder voorraad (0 stuks) - KRITIEK\n"
        "- Totaal aantal producten in het systeem\n"
        "- Aanbevelingen voor bijbestellen"
    )


@mcp.prompt()
def prijslijst(categorie: str = "") -> str:
    """Genereer een prijslijst, optioneel gefilterd op categorie.

    Args:
        categorie: Categorienaam of ID (leeg = alle categorieën)
    """
    cat_filter = f" voor categorie '{categorie}'" if categorie else ""
    return (
        f"Genereer een overzichtelijke prijslijst{cat_filter} voor Yilmaz Voeding XL.\n\n"
        f"Gebruik deze tools:\n"
        f"1. lijst_categorieen() - om categorieën op te halen\n"
        f"2. lijst_producten(pagina=1, aantal=100) - producten ophalen\n"
        f"3. winstmarge() - marges berekenen\n\n"
        f"Presenteer als een nette tabel met:\n"
        f"- Categorie\n"
        f"- Productnaam\n"
        f"- Referentie\n"
        f"- Verkoopprijs incl BTW\n"
        f"- BTW tarief\n"
        f"- Eenheid"
    )


# ── MCP RESOURCES ────────────────────────────────────────────

@mcp.resource("onlinefact://catalogus")
def resource_catalogus() -> str:
    """Volledige productcatalogus van Yilmaz Voeding XL."""
    try:
        alle_producten = []
        page = 1
        while page <= 20:
            batch = api.list_products(page=page, limit=100)
            if not batch or not isinstance(batch, list):
                break
            alle_producten.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return json.dumps(alle_producten, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij laden catalogus: {e}"


@mcp.resource("onlinefact://categorieen")
def resource_categorieen() -> str:
    """Alle productcategorieën van Yilmaz Voeding XL."""
    try:
        result = api.list_categories(limit=200)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Fout bij laden categorieën: {e}"


# ── Start ─────────────────────────────────────────────────────

if __name__ == "__main__":
    if _transport == "streamable-http":
        logger.info(f"OnlineFact MCP Server gestart (streamable-http, poort {_port})")
        logger.info(f"Endpoint: /{_secret_path}/mcp")
        mcp.run(transport="streamable-http")
    elif _transport == "sse":
        logger.info(f"OnlineFact MCP Server gestart (SSE, poort {_port})")
        logger.info(f"Endpoint: /{_secret_path}/sse")
        mcp.run(transport="sse")
    else:
        logger.info("OnlineFact MCP Server gestart (stdio)")
        mcp.run(transport="stdio")
