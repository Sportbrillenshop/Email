#!/usr/bin/env python3
"""
Sportbrillenshop – Wekelijkse nieuwsbrief generator

Haalt automatisch de 6 nieuwste producten op uit Shopify, vult het
HTML-template in en zet het klaar als concept-template in Klaviyo.
Jij hoeft daarna alleen nog een campaign aan te maken en op Verzenden te klikken.

Installatie (eenmalig):
    pip install requests

Gebruik – nieuwste 6 producten automatisch:
    python generate_newsletter.py

Gebruik – zelf producten kiezen (handles staan in de Shopify product-URL):
    python generate_newsletter.py --products oakley-flak-2-0 oakley-sutro-lite ray-ban-meta ...
"""

import re
import sys
import argparse
import requests
from datetime import datetime
from pathlib import Path
from html import escape

# ══════════════════════════════════════════════════════════════════════════════
# INSTELLINGEN
# Vul SHOPIFY_STORE in met jouw .myshopify.com adres.
# Dat vind je zo: log in op Shopify → kijk in de browserbalk, bijv.:
#   https://sportbrillenshop.myshopify.com/admin  →  sportbrillenshop.myshopify.com
# ══════════════════════════════════════════════════════════════════════════════
SHOPIFY_STORE   = "sportbrillenshop-nl.myshopify.com"   # ← pas aan indien nodig
SHOPIFY_TOKEN   = "00c46eb67d84c39374abfa3a376aceb7"
KLAVIYO_API_KEY = "pk_RhiBQx_7f663cfac37833270c67bb3afe2d5fcbe5"

TEMPLATE_FILE   = Path(__file__).parent / "weekly-newsletter.html"
OUTPUT_DIR      = Path(__file__).parent / "output"
PRODUCTS_TOTAL  = 6   # 2 secties × 3 producten


# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY
# ══════════════════════════════════════════════════════════════════════════════

def shopify_get(endpoint, params=None):
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/{endpoint}"
    resp = requests.get(
        url,
        headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
        params=params or {},
        timeout=15,
    )
    if resp.status_code == 401:
        sys.exit("Fout: Shopify token is ongeldig. Controleer SHOPIFY_TOKEN en SHOPIFY_STORE.")
    resp.raise_for_status()
    return resp.json()


def fetch_latest_products(n=6):
    data = shopify_get("products.json", {"limit": n, "status": "active"})
    products = data["products"]
    if not products:
        sys.exit("Geen actieve producten gevonden in Shopify.")
    return products


def fetch_product_by_handle(handle):
    data = shopify_get("products.json", {"handle": handle, "limit": 1})
    products = data["products"]
    if not products:
        sys.exit(f"Product niet gevonden: '{handle}'. Controleer de handle (zie Shopify product-URL).")
    return products[0]


def product_image_url(product):
    """Geeft de eerste productafbeelding terug, geoptimaliseerd op 320px breedte."""
    if product.get("images"):
        src = product["images"][0]["src"]
        # Shopify CDN resize: voeg _320x toe voor 320px breed
        base, ext = src.rsplit(".", 1)
        return f"{base}_320x.{ext.split('?')[0]}"
    return "https://via.placeholder.com/160x130/f7f3f9/621979?text=Geen+foto"


def format_price(product):
    """Formatteert de prijs als € 169,95."""
    price_str = product["variants"][0]["price"]
    price = float(price_str)
    return f"&euro;&nbsp;{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ══════════════════════════════════════════════════════════════════════════════
# HTML OPBOUW
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_CELL = """\
                <td class="product-cell" width="33%" align="center" valign="top" style="padding: 0 8px;">
                  <a href="https://sportbrillenshop.nl/products/{handle}" target="_blank">
                    <img class="product-img"
                      src="{image_url}"
                      width="160" alt="{title_attr}"
                      style="width: 160px; max-width: 100%; border-radius: 6px; margin: 0 auto 12px;"
                    />
                  </a>
                  <p class="product-name" style="margin: 0 0 4px; color: #1a1a1a; font-size: 13px; font-family: Arial, Helvetica, sans-serif; font-weight: bold; line-height: 1.4;">
                    {title}
                  </p>
                  <p class="product-price" style="margin: 0 0 12px; color: #621979; font-size: 15px; font-family: Arial, Helvetica, sans-serif; font-weight: bold;">
                    {price}
                  </p>
                  <a class="product-btn" href="https://sportbrillenshop.nl/products/{handle}"
                     style="display: inline-block; background-color: #621979; color: #ffffff; font-size: 13px; font-family: Arial, Helvetica, sans-serif; font-weight: bold; text-decoration: none; padding: 9px 18px; border-radius: 4px;">
                    Nu shoppen
                  </a>
                </td>"""


def build_cell(product):
    title = product["title"]
    return PRODUCT_CELL.format(
        handle=product["handle"],
        image_url=product_image_url(product),
        title_attr=escape(title),
        title=escape(title),
        price=format_price(product),
    )


def fill_template(products):
    html = TEMPLATE_FILE.read_text(encoding="utf-8")
    for i, product in enumerate(products, start=1):
        new_cell = build_cell(product)
        # Vervang alles tussen <!-- SLOT-N-START --> en <!-- SLOT-N-END -->
        pattern = rf"<!-- SLOT-{i}-START -->.*?<!-- SLOT-{i}-END -->"
        replacement = f"<!-- SLOT-{i}-START -->\n{new_cell}\n                <!-- SLOT-{i}-END -->"
        html, count = re.subn(pattern, replacement, html, flags=re.DOTALL)
        if count == 0:
            print(f"  ⚠️  Slot {i} niet gevonden in template – sla over.")
    return html


# ══════════════════════════════════════════════════════════════════════════════
# KLAVIYO
# ══════════════════════════════════════════════════════════════════════════════

KLAVIYO_HEADERS = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
    "revision": "2024-02-15",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def create_klaviyo_template(html, name):
    """Maakt een nieuw HTML-template aan in Klaviyo en geeft het ID terug."""
    payload = {
        "data": {
            "type": "template",
            "attributes": {
                "name": name,
                "editor_type": "CODE",
                "html": html,
            },
        }
    }
    resp = requests.post(
        "https://a.klaviyo.com/api/templates/",
        headers=KLAVIYO_HEADERS,
        json=payload,
        timeout=20,
    )
    if resp.status_code == 401:
        return None, "Klaviyo API-sleutel ongeldig."
    if not resp.ok:
        return None, f"Klaviyo fout {resp.status_code}: {resp.text[:200]}"
    return resp.json()["data"]["id"], None


# ══════════════════════════════════════════════════════════════════════════════
# HOOFDPROGRAMMA
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Genereer de wekelijkse Sportbrillenshop nieuwsbrief"
    )
    parser.add_argument(
        "--products",
        nargs="+",
        metavar="HANDLE",
        help=(
            "Optioneel: geef zelf 6 product-handles op. "
            "De handle staat in de Shopify product-URL, bijv. oakley-flak-2-0-xl"
        ),
    )
    args = parser.parse_args()

    week_label = datetime.now().strftime("week %V – %Y")
    template_name = f"Nieuwsbrief {week_label}"
    print(f"\n{'─'*50}")
    print(f"  Sportbrillenshop – {template_name}")
    print(f"{'─'*50}\n")

    # 1. Producten ophalen uit Shopify
    if args.products:
        if len(args.products) != PRODUCTS_TOTAL:
            sys.exit(f"Geef precies {PRODUCTS_TOTAL} product-handles op (nu: {len(args.products)}).")
        print(f"Producten ophalen op handle...")
        products = [fetch_product_by_handle(h) for h in args.products]
    else:
        print(f"Laatste {PRODUCTS_TOTAL} producten ophalen uit Shopify...")
        products = fetch_latest_products(PRODUCTS_TOTAL)

    for i, p in enumerate(products, 1):
        print(f"  {i}. {p['title']}  –  {format_price(p)}")

    # 2. HTML-template invullen
    print("\nTemplate invullen met productgegevens...")
    filled_html = fill_template(products)

    # 3. Opslaan als lokaal bestand (altijd, als backup)
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_file = OUTPUT_DIR / f"nieuwsbrief-{datetime.now().strftime('%Y-week%V')}.html"
    output_file.write_text(filled_html, encoding="utf-8")
    print(f"  ✓ Opgeslagen als: {output_file}")

    # 4. Template uploaden naar Klaviyo
    print("\nTemplate uploaden naar Klaviyo...")
    template_id, error = create_klaviyo_template(filled_html, template_name)

    if error:
        print(f"  ⚠️  Klaviyo upload mislukt: {error}")
        print(f"  → Upload {output_file} handmatig via Klaviyo → Templates → Import HTML")
    else:
        print(f"  ✓ Template aangemaakt in Klaviyo (id: {template_id})")
        print(f"\n{'─'*50}")
        print("  Klaar! Volgende stappen in Klaviyo:")
        print("  1. Ga naar Campaigns → Create Campaign")
        print(f"  2. Kies template: \"{template_name}\"")
        print("  3. Kies je verzendlijst en plan de verzending in")
        print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
