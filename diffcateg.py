from .data import VG_POS_FAMILIES, MARKET_CONSUMPTION_CENTER_ID
from collections import namedtuple
import json
import sys
from unidecode import unidecode
import csv
import datetime as dt

DIFF_CATEG_OUT_FILE_NAME = "pos_categ_diff_%d%m%Y%H%M.csv"
PRODUCT_CATALOG_OUT_FILE_NAME = "product_catalog_%d%m%Y%H%M.csv"

PosVillaProduct = namedtuple("PosVillaProduct", ["pos_villa_identifier", "name", "family"])
OdooProduct = namedtuple("OdooProduct", ["product_template_id","name", "pos_categ_id", "parent_category", "active"])
VillaOdooRelation = namedtuple("VillaOdooRelation", ["pos_villa_product", "odoo_product"])
OdooVillaRelation = namedtuple("OdooVillaRelation", ["odoo_product", "pos_villa_product"])

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
        odoo_product = OdooProduct(odoo_product.id, odoo_product.name, odoo_product.pos_categ_id.name, odoo_product.pos_categ_id.parent_id.name, odoo_product.active)
        relations.append(VillaOdooRelation(pos_villa_product, odoo_product))
    return relations

def get_all_odoo_products_relation(env) -> list:
    product = env["product.product"]
    odoo_pos_villa_relations = []
    for product in product.search([]):
        odoo_product = OdooProduct(product.id, product.name, product.pos_categ_id.name, product.pos_categ_id.parent_id.name, product.active)
        if product.pos_villa_product_ids:
            for legacy_product in product.pos_villa_product_ids:
                odoo_pos_villa_relations.append(OdooVillaRelation(odoo_product, record_to_pos_villa_product(legacy_product)))
        else:
            odoo_pos_villa_relations.append(OdooVillaRelation(odoo_product, None))
    return odoo_pos_villa_relations

def product_categories_match(pos_villa_product: PosVillaProduct, odoo_product: OdooProduct) -> bool:
    villa_categ = pos_villa_product.family and unidecode(pos_villa_product.family.lower())
    odoo_categ = odoo_product.pos_categ_id and unidecode(odoo_product.pos_categ_id.lower())
    return (villa_categ and odoo_categ and (villa_categ in odoo_categ or odoo_categ in villa_categ))

def main(env):
    now = dt.datetime.now()
    diff_filename = now.strftime(DIFF_CATEG_OUT_FILE_NAME)
    with open(diff_filename, "w") as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
        HEADERS = ["product_template_id", "Odoo Name", "pos_villa_identifier", "POS Villa Name", "Parent Category", "Categ Odoo (pos_categ_id)", "active", "Familia POS Villa", "Status"]
        writer.writerow(HEADERS)
        products_rel = get_market_products_rel(env)
        for pos_villa_product, odoo_product in products_rel:
            if not product_categories_match(pos_villa_product, odoo_product):
                product_template_id = odoo_product.product_template_id or "SIN EQUIVALENTE EN ODOO"
                odoo_name = odoo_product.name or "SIN EQUIVALENTE EN ODOO"
                pos_villa_id = pos_villa_product.pos_villa_identifier or "SIN EQUIVALENTE EN POS VILLA"
                pos_villa_name = pos_villa_product.name or "SIN EQUIVALENTE EN POS VILLA"
                parent_category = odoo_product.parent_category or "SIN CATEGORIA"
                categ_odoo = odoo_product.pos_categ_id or "SIN CATEGORIA EN ODOO"
                active = odoo_product.active
                familia_pos_villa = pos_villa_product.family or "SIN CATEGORIA"
                status = "TODO"
                if odoo_product.name:
                    writer.writerow([product_template_id, odoo_name, pos_villa_id, pos_villa_name, parent_category, categ_odoo, active, familia_pos_villa, status])

    catalog_filename = now.strftime(PRODUCT_CATALOG_OUT_FILE_NAME)
    with open(catalog_filename, "w") as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
        HEADERS = ["id", "pos_villa_id" ,"Name", "Parent Category", "Category", "Active"]
        writer.writerow(HEADERS)
        all_odoo_product_relations = get_all_odoo_products_relation(env)
        for odoo_product, pos_villa_product in all_odoo_product_relations:
            id, name, categ, parent_categ, active = odoo_product
            pos_villa_id = pos_villa_product.pos_villa_identifier if pos_villa_product else "N/A"
            writer.writerow([id, pos_villa_id, name, parent_categ or "SIN CATEGORIA" , categ or "SIN CATEGORIA", active])
