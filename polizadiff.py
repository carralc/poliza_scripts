#!/bin/python3
"""
Produce a comparison between a villagroup poliza and our implementation of poliza
"""
from poliza2csv import process_line, EXCLUDED_CONCEPTS, SKIP_FIRST, PolizaLine, process_amount, format_amount
import sys
import csv
import re
from collections import namedtuple
import logging
import argparse
import tabulate
import datetime as dt
import itertools

log = logging.getLogger(__name__)

VAUXOO_SKIP_FIRST = 1

CollapsedAccount = namedtuple("CollapsedAccount", ["account", "description"])

def get_collapsed_accounts(fname: str) -> list:
    try:
        collapsed_accounts = []
        with open(fname, "r") as file:
            reader = csv.reader(file)
            for row in reader:
                collapsed_accounts.append(CollapsedAccount(*row))
        return collapsed_accounts
    except:
        return []

def extract_poliza_date_from_fname(fname:str) -> str:
    dt_matcher = re.compile(r"(?P<date>\d{8})")
    dt_match  = dt_matcher.search(fname)
    return dt_match["date"]

def main(argv):
    argparser = argparse.ArgumentParser()
    argparser.add_argument("POLIZA_VILLAGROUP", help="Villagroup poliza impl (.txt)")
    argparser.add_argument("POLIZA_VX", help="Vauxoo poliza impl (.csv)")
    argparser.add_argument("--strict", help="Doesn't permit a match if concepts don't align", action="store_true")
    argparser.add_argument("--show-close-matches", "-s", help="Show amounts that almost align by MARGIN", action="store_true")
    argparser.add_argument("--collapse-accounts", help="Collapse accounts specified in .collapse", action="store_true")
    argparser.add_argument("--show-inverted-sign-matches", help="Show amounts that match but have their sign inverted", action="store_true")
    argparser.add_argument("--csv-match-results", action="store_true")
    args = argparser.parse_args()

    poliza_vg = args.POLIZA_VILLAGROUP
    poliza_vauxoo = args.POLIZA_VX
    
    lines_vg = None
    lines_vauxoo = None
    with open(poliza_vg, "r", encoding="ISO-8859-1") as poliza_vg_file:
        for _ in range(SKIP_FIRST):
            next(poliza_vg_file)
        # list of PolizaLine
        lines_vg = map(process_line, poliza_vg_file)
        # Remove None's
        lines_vg = filter(lambda line: line, lines_vg)
        # Remove excluded concepts
        lines_vg : list[PolizaLine] = list(filter(lambda line: line.concept not in EXCLUDED_CONCEPTS, lines_vg))


    with open(poliza_vauxoo, "r") as poliza_vauxoo:
        poliza_reader = csv.reader(poliza_vauxoo, delimiter=",", quotechar='"')
        for _ in range(VAUXOO_SKIP_FIRST):
            next(poliza_reader)
        lines_vauxoo : list[PolizaLine] = map(process_vauxoo_line, poliza_reader)
        lines_vauxoo : list[PolizaLine] = list(filter(lambda line: line.concept not in EXCLUDED_CONCEPTS, lines_vauxoo))

    lines_vg = remove_spa_lines(lines_vg)

    extracted_lines_vx = {}
    extracted_lines_vg = {}

    if args.collapse_accounts:
        collapsed_accounts = get_collapsed_accounts(".collapse")
        for account, descr in collapsed_accounts:
            lines_vg, extracted_vg  = collapse_account(lines_vg, account, descr)
            extracted_lines_vg[account] = extracted_vg
            lines_vauxoo, extracted_vx = collapse_account(lines_vauxoo, account, descr)
            extracted_lines_vx[account] = extracted_vx


    matched_lines = []
    unmatched_lines = []

    odd_amounts_buffer = []

    for line_vx in lines_vauxoo:
        if matched_line := line_has_match(line_vx, lines_vg, strict=args.strict, show_close_matches=args.show_close_matches):
            matched_lines.append((line_vx, matched_line))
        else:
            # If line was unmatched and is accumulated line, check if by extracting one or some amounts, we could
            # actually match it to its intended target. In practice, this is used by extracting untagged spa amounts
            if acc_lines_vg := extracted_lines_vg.get(line_vx.account):
                acc_lines_vx = extracted_lines_vx.get(line_vx.account)
                target_amount = sum(float(l.amount) for l in acc_lines_vx)
                odd_lines = get_odd_amounts_out(acc_lines_vg, target_amount)
                if odd_lines:
                    add_to_odd_amounts(odd_lines, odd_amounts_buffer, "Poliza VG", "Poliza VX")
                    matched_lines.append((line_vx, get_dummy_line()))
                    continue

            possible_target = get_possible_target(line_vx, lines_vg) or None
            unmatched_lines.append((line_vx, possible_target))

    matched_table = [["MATCH", vx.account, vx.concept, format_amount((vx.sign, vx.amount, vx.type)), format_amount((vg.sign, vg.amount, vg.type)), vg.account, vg.concept] for vx, vg in matched_lines]
    unmatched_table = [["NO MATCH", vx.account, vx.concept, vx.amount, tg.amount if tg else "", tg.concept if tg else "", tg.account if tg else ""] for vx, tg in unmatched_lines]

    CSV_RESULT_FILE = "POLIZA_DIFF_%s.csv"

    if args.csv_match_results:
        poliza_date = extract_poliza_date_from_fname(poliza_vg)
        with open(CSV_RESULT_FILE % poliza_date, "w") as outfile:
            writer = csv.writer(outfile, csv.QUOTE_MINIMAL)
            writer.writerow(["account", "concept", "VX-VG match"])
            for vx, vg in matched_lines:
                writer.writerow([vx.account, vx.concept, True])
            for vx, possibly_vg in unmatched_lines:
                writer.writerow([vx.account, vx.concept, False])


    print(tabulate.tabulate(matched_table, headers=["STATUS", "VX acc", "VX concept", "VX amount", "VG amount","VG acc", "VG concept"]))
    print(tabulate.tabulate(unmatched_table))

    for msg in odd_amounts_buffer:
        print(msg)

    len_target = len(lines_vauxoo)
    matches = len(matched_lines)
    match_pctg = matches / len_target
    #  print("-"*40 + "\n")
    print("Summary:\nMatching concepts: {}\nNon matching: {}\nMatching pctg: {:.2f}%".format(matches, len(lines_vauxoo), match_pctg * 100))

def add_to_odd_amounts(odd_lines: list[PolizaLine], odd_amounts_acc_list: list[str], source: str, target: str):
    for line in odd_lines:
        msg = f"WARNING: {line.concept}  {format_amount((line.sign, line.amount, line.type))} exists in {source} but not in {target}. Removing it makes accounts {line.account} match."
        odd_amounts_acc_list.append(msg)

def line_has_match(line: PolizaLine, domain: list, tolerance=2.0, tolerance_upper_bound=5.0, strict=False, show_close_matches=False) -> PolizaLine:
    line_amount = float(line.amount)
    line_type = line.type
    line_sign = line.sign
    for target_line in domain:
        target_amount = float(target_line.amount)
        target_type = target_line.type
        target_sign = target_line.sign
        if  abs(line_amount - target_amount) < tolerance and line_type == target_type:
            #  if target_line.concept != line.concept and strict:
                #  return False
            if target_line.account.strip() != line.account.strip() and strict:
                return False
            return target_line 
        elif (diff:= abs(line_amount - target_amount)) < tolerance_upper_bound and line_type == target_type and show_close_matches:
            log.warning("Concepts %s, %s close to matching by $%s", target_line.concept, line.concept, diff)
    return False

def get_dummy_line() -> PolizaLine:
    return PolizaLine("","","","","")

def process_vauxoo_line(csv: list) -> PolizaLine:
    assert len(csv) == 3
    account = csv[0]
    concept = csv[1]
    sign, amount, _type = process_amount(csv[2])
    return PolizaLine(account, concept, sign, amount, _type)

def remove_spa_lines(lines: list[PolizaLine]) ->list[PolizaLine]:
    return list(filter(lambda l: "spa" not in l.concept.lower(), lines))
    

def collapse_account(lines: list[PolizaLine], account: str, descr: str) -> (list[PolizaLine], list[PolizaLine]):
    extracted_lines = list(filter(lambda l: l.account == account, lines))
    all_other_lines = list(filter(lambda l: l.account != account, lines))
    amount_debit = sum(float(l.sign + l.amount) for l in filter(lambda l: l.type == "c", extracted_lines))
    amount_credit = sum(float(l.sign + l.amount) for l in filter(lambda l: l.type == "a", extracted_lines))
    acc_amount_debit ="{:.2f}c".format(amount_debit)
    acc_amount_credit ="{:.2f}a".format(amount_credit)
    debit_sign, debit_amount, debit_type = process_amount(acc_amount_debit)
    credit_sign, credit_amount, credit_type = process_amount(acc_amount_credit)
    new_line_debit = PolizaLine(account, descr , debit_sign, debit_amount, debit_type)
    new_line_credit = PolizaLine(account, descr , credit_sign, credit_amount, credit_type)
    if amount_debit:
        all_other_lines.append(new_line_debit)
    if amount_credit:
        all_other_lines.append(new_line_credit)
    return all_other_lines, extracted_lines

def get_possible_target(line: PolizaLine, candidates: list[PolizaLine]) -> PolizaLine:
    # The heuristic we are using is:
    # 1. Search for account
    matches_by_account = list(filter(lambda l: l.account == line.account, candidates))
    # 2. Search if any two lines share a word in their title
    line_words = list(map(lambda w: w.lower(), re.split("[\W+|-]", line.concept.lower())))
    words_in_targets = map(lambda t: (t, re.split("[\W+|-]", t.concept.lower())), matches_by_account)
    count_of_word_matches = map(lambda tgt_words: (tgt_words[0], sum(w in line_words for w in tgt_words[1])), words_in_targets)
    sorted_by_matches = list(sorted(count_of_word_matches, key=lambda t: t[1], reverse=True))
    return sorted_by_matches[0][0] if sorted_by_matches else None

def get_odd_amounts_out(lines: list[PolizaLine], target_amount: float, tolerance=1.0) -> list[PolizaLine]:
    """If we have a list of lines whose sum doesn't match the target amount,
    it might be the case that if we extracted some of those amounts from the sum,
    the amounts might match with the target. This function performs combinatorial analysis
    so that we are able to find if extracting a combination of lines from the original lines
    yields the target amount"""
    max_combination_len = len(lines) if len(lines) < 6 else 5
    acc_lines_amount = sum(map(lambda l: float(l.sign + l.amount), lines)) 
    for i in range(1, max_combination_len):
        for combination in itertools.combinations(lines, i):
            possible_substracted_amount = sum(map(lambda l: float(l.sign + l.amount), combination))
            possible_actual_amount = acc_lines_amount - possible_substracted_amount
            if abs(possible_actual_amount - target_amount) < tolerance:
                return list(combination)
    return []

def miscategorized_sister_accounts(sister_account_lines: tuple, target_sister_account_lines: tuple) -> bool:
    """It has occured that two 'sister' accounts (i.e DELI BEBIDAS & DELI ALIMENTOS) have products that
    are badly categorized. so if each category has target amounts B1 and B2, its corresponding 
    actual amounts are A1 + X.XX and A2 - X.XX
    This function detects that special case"""
    a1_lines, a2_lines = sister_account_lines
    b3_lines, b4_lines = target_sister_account_lines
    my_amount = sum(float(a1.amount) for a1 in a1_lines) + sum(float(a2.amount) for a2 in a2_lines)
    target_amount = sum(float(b1.amount) for b1 in b1_lines) + sum(float(b2.amount) for b2 in b2_lines)
    return my_amount == target_amount

if __name__ == "__main__":
    main(sys.argv)
