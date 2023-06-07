from .data import VG_POS_FAMILIES, MARKET_CONSUMPTION_CENTER_ID
from collections import namedtuple
import json
import sys
from unidecode import unidecode
import csv
import datetime as dt

OUT_FILE_NAME = "pos_categ_diff_%d%m%Y%H%M.csv"

PosVillaProduct = namedtuple("PosVillaProduct", ["pos_villa_identifier", "name", "family"])
OdooProduct = namedtuple("OdooProduct", ["product_template_id","name", "pos_categ_id"])
VillaOdooRelation = namedtuple("VillaOdooRelation", ["pos_villa_product", "odoo_product"])

def record_to_pos_villa_product(record) -> PosVillaProduct:
    pos_villa_values = json.loads(record.pos_villa_values)
    family_id = pos_villa_values["idFamilia"] or 0
    return PosVillaProduct(record.pos_villa_identifier, record.name, VG_POS_FAMILIES[int(family_id)])


def get_market_products_rel(env) -> list:
    """Return a list matching each legacy product with its target equivalent in odoo"""

    legacy_product = env["pos.villa.product"]
    legacy_market_products = legacy_product.search([("consumption_center_id", "=", MARKET_CONSUMPTION_CENTER_ID)])
    relations = []
    for legacy_product in legacy_market_products:
        pos_villa_product = record_to_pos_villa_product(legacy_product)
        odoo_product = legacy_product.product_tmpl_id
        odoo_product = OdooProduct(odoo_product.id, odoo_product.name, odoo_product.pos_categ_id.name)
        relations.append(VillaOdooRelation(pos_villa_product, odoo_product))
    return relations

def product_categories_match(pos_villa_product: PosVillaProduct, odoo_product: OdooProduct) -> bool:
    villa_categ = pos_villa_product.family and unidecode(pos_villa_product.family.lower())
    odoo_categ = odoo_product.pos_categ_id and unidecode(odoo_product.pos_categ_id.lower())
    return (villa_categ and odoo_categ and (villa_categ in odoo_categ or odoo_categ in villa_categ))

def main(env):
    now = dt.datetime.now()
    filename = now.strftime(OUT_FILE_NAME)
    with open(filename, "w") as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
        HEADERS = ["product_template_id", "Odoo Name", "pos_villa_identifier", "POS Villa Name", "Categ Odoo (pos_categ_id)", "Familia POS Villa", "Status"]
        writer.writerow(HEADERS)
        products_rel = get_market_products_rel(env)
        for pos_villa_product, odoo_product in products_rel:
            if not product_categories_match(pos_villa_product, odoo_product):
                product_template_id = odoo_product.product_template_id or "SIN EQUIVALENTE EN ODOO"
                odoo_name = odoo_product.name or "SIN EQUIVALENTE EN ODOO"
                pos_villa_id = pos_villa_product.pos_villa_identifier or "SIN EQUIVALENTE EN POS VILLA"
                pos_villa_name = pos_villa_product.name or  "SIN EQUIVALENTE EN POS VILLA"
                categ_odoo = odoo_product.pos_categ_id or "SIN CATEGORIA EN ODOO"
                familia_pos_villa = pos_villa_product.family or "SIN CATEGORIA"
                status = "TODO"
                writer.writerow([product_template_id, odoo_name, pos_villa_id, pos_villa_name, categ_odoo, familia_pos_villa, status])
