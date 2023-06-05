#!/bin/python3
"""
Produce a comparison between a villagroup poliza and our implementation of poliza
"""
from poliza2csv import process_line, EXCLUDED_CONCEPTS, SKIP_FIRST, PolizaLine
import sys
import csv
import re
from collections import namedtuple
import logging

log = logging.getLogger(__name__)

VAUXOO_SKIP_FIRST = 1

def main(argv):
    if not validate_args(argv[1:]):
        usage()
        return
    poliza_vg = argv[1]
    poliza_vauxoo = argv[2]
    
    lines_vg = None
    lines_vauxoo = None
    with open(poliza_vg, "r", encoding="ISO-8859-1") as poliza_vg:
        for _ in range(SKIP_FIRST):
            next(poliza_vg)
        lines_vg = map(process_line, poliza_vg)
        # Remove None's
        lines_vg = filter(lambda line: line, lines_vg)
        lines_vg = list(filter(lambda line: line.concept not in EXCLUDED_CONCEPTS, lines_vg))

    with open(poliza_vauxoo, "r") as poliza_vauxoo:
        poliza_reader = csv.reader(poliza_vauxoo, delimiter=",", quotechar='"')
        for _ in range(VAUXOO_SKIP_FIRST):
            next(poliza_reader)
        lines_vauxoo = list(map(lambda values: PolizaLine(*values), poliza_reader))

    matches = sum(map(lambda line_vx: line_has_match(line_vx, lines_vg), lines_vauxoo))
    len_target = len(lines_vg)
    match_pctg = matches / len_target
    print("-"*40 + "\n")
    print("Summary:\nMatching concepts: {}\nMatching pctg: {:.2f}%".format(matches,match_pctg * 100))

def line_has_match(line: PolizaLine, domain: list, tolerance=0.5) -> bool:
    poliza_amount = re.compile(r"((?P<sign>-)*(?P<amount>\d+\.\d+))(?P<type>a|c)")
    line_amount_match = poliza_amount.search(line.amount)
    line_amount = float(line_amount_match["amount"])
    line_type = line_amount_match["type"] 
    line_sign = line_amount_match["sign"] or "+"
    for target_line in domain:
        target_amount_match = poliza_amount.search(target_line.amount)
        target_amount = float(target_amount_match["amount"])
        target_type = target_amount_match["amount"] 
        target_sign = target_amount_match["sign"] or "+"
        if  abs(line_amount - target_amount) < tolerance:
            if target_line.account.strip() == line.account.strip():
                if target_sign != line_sign:
                    log.warning("Matching amounts found for concepts %s, %s but with different sign", target_line.concept, line.concept)
                return True
            else:
                log.warning("Matching amounts found for concepts %s, %s but with different accounts", target_line.concept, line.concept)
    return False




def usage():
    print("USAGE:\n./polizadiff POLIZA_VG.txt POLIZA_VAUXOO.csv")

def validate_args(argv):
    if len(argv) < 2:
        return False
    return True

if __name__ == "__main__":
    main(sys.argv)
