#!/bin/python3
import sys
from collections import namedtuple
import re

PolizaLine = namedtuple("PolizaLine", ["account", "concept", "sign", "amount", "type"])

SKIP_FIRST = 2
EXCLUDED_CONCEPTS = [
'PAQ MLP MENOR NET CENTER 54 US',
'PAQ MLP PREARRIVAL 97.20 USD A',
'VISA DOLARES',
'PAQ MLP PREARRIVAL 108 USD BEB',
'Viajes El Arco-SPA',
'Complementaria MASTER CARD DOL',
'PAQ MLP UVC 108 USD',
'Graba-Desc. s/venta Tratamient',
'Ninguna-Todo el día-SPA',
'Salon de Belleza-Todo el día-S',
'PAQ MLP PREARRIVAL 97.20 USD B',
'REST LOBBY BAR DINNER',
'PAQ MLP PREARRIVAL 99 USD BEBI',
'AJ SPA GIFT CERT',
'ACUMUL/FILIALES DEUDORAS',
'ACUMUL/CLIENTES Y/O AGENCIAS B',
'CXC MEAL PLAN UVC',
'Complementaria DEPOSITO WEB US',
'PAQ MLP UVC 108 USD BEBIDA',
'Graba-Desc. s/venta Faciales',
'ACUMUL/CTM',
'CXC MEAL PLAN PA UVC',
'ACUMUL/CUENTA COMPLEMENTARIA',
'MASTER CARD DOLARES',
'ACUMUL/VALUACION DE BANCOS',
'ACUMUL/IMPUESTO AL HOSPEDAJE',
'Graba-Desc. s/venta Salon de B',
'ACUMUL/INGRESO HABITACIONES',
'Faciales-Todo el día-SPA',
'ACUMUL/RENTA DE PELICULAS',
'Graba-Desc. s/venta Suministro',
'ACUMUL/POR OTROS',
'ACUMUL/OTROS',
'ACUMUL/INGRESOS HABITACIONES A',
'PAQ MLP PREARRIVAL 99 USD ALIM',
'Graba-Desc. s/venta Masajes',
'PAQ MLP PREARRIVAL MENOR 49.50',
'ACUMUL/CENTROS DE CONSUMO',
'ACUMUL/OTROS',
'DEPOSITO POR RESERVACIONES DLS',
'PAQ MLP DIRECTO 120 USD',
'CREDITO AUDITORIA REPROCESO RO',
'ACUMUL/BANAMEX',
'REEMBOLSO AGENCIA',
'AJ RESORT CREDIT AYB',
'Complemtaria DEPOSITO POR RESE',
'Gift Certificate Use-SPA',
'PAQ MLP PREARRIVAL MENOR 48.60',
'ACUMUL/PAID OUT',
'ENVIRONMENTAL SANITATION SERV',
'Complementaria DEPOSITO POR RE',
'Tratamientos-Todo el día-SPA',
'ACUMUL/CLIENTES NACIONALES DLL',
'PAQ MLP PREARRIVAL 108 USD ALI',
'Complementaria VISA DOLARES',
'AJ REST PATRON',
'PAQ MLP DIRECTO 120 USD ALIMEN',
'ACUMUL/SPA MASAJES',
'CXC NET CENTER',
'PAQ MLP UVC 108 USD ALIMENTO',
'ACUMUL/ALIMENTOS AIP',
'AJ REST CORALLE',
'PAQ MLP DIRECTO 120 USD BEBIDA',
'DEPOSITO WEB USD',
'ACUMUL/SOBRANTES Y FALTANTES'
]


def valid_args(argv) -> bool:
    return len(argv) == 2


def process_line(line: str) -> PolizaLine:
    ACCOUNT_LEN = 11
    CONCEPT_LEN = 30
    if len(line) < ACCOUNT_LEN + CONCEPT_LEN:
        return None
    account = line[0:ACCOUNT_LEN].strip()
    concept = line[ACCOUNT_LEN:ACCOUNT_LEN+CONCEPT_LEN].strip()
    amount_str = line[ACCOUNT_LEN+CONCEPT_LEN:].strip()
    sign, amount, amount_type = process_amount(amount_str)
    return PolizaLine(account, concept, sign, amount, amount_type)

def process_amount(amount: str) -> tuple:
    amount_matcher = re.compile(r"((?P<sign>-)*(?P<amount>\d+\.\d+))(?P<type>a|c)")
    amount_match = amount_matcher.search(amount)
    sign = amount_match["sign"] or "+"
    return (sign, amount_match["amount"], amount_match["type"])



def main(argv):
    if not valid_args(argv):
        print("Invalid args")
    fname = argv[1]
    with open(fname, "r", encoding="ISO-8859-1") as input_file:
        print("'Cuenta','Concepto','Monto'")
        for _ in range(SKIP_FIRST):
            next(input_file)
        for line in input_file:
            line_vals = process_line(line)
            if line_vals:
                account, concept, sign, amount, amount_type = line_vals
                if not any(concept in excluded_concept for excluded_concept in EXCLUDED_CONCEPTS):
                    print(f"'{account}','{concept}','{(sign if sign == '-' else '') + amount + amount_type}'")


if __name__ == "__main__":
    main(sys.argv)
