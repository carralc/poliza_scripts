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
from enum import Enum 
import os
import io 

log = logging.getLogger(__name__)

VAUXOO_SKIP_FIRST = 1

CollapsedAccount = namedtuple("CollapsedAccount", ["account", "description"])

class OpMode(Enum):
    SINGLE_FILE_DIFF = 0
    DIR_DIFF = 1

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

def get_vg_poliza_lines(poliza_vg):
    with open(poliza_vg, "r", encoding="ISO-8859-1") as poliza_vg_file:
        for _ in range(SKIP_FIRST):
            next(poliza_vg_file)
        # list of PolizaLine
        lines_vg = map(process_line, poliza_vg_file)
        # Remove None's
        lines_vg = filter(lambda line: line, lines_vg)
        # Remove excluded concepts
        lines_vg : list[PolizaLine] = list(filter(lambda line: line.concept not in EXCLUDED_CONCEPTS, lines_vg))
        return remove_unsupported_vg_lines(lines_vg)

def get_vx_poliza_lines(poliza_vx):
    with open(poliza_vx, "r") as poliza_vauxoo:
        poliza_reader = csv.reader(poliza_vauxoo, delimiter=",", quotechar='"')
        for _ in range(VAUXOO_SKIP_FIRST):
            next(poliza_reader)
        lines_vauxoo : list[PolizaLine] = map(process_vauxoo_line, poliza_reader)
        lines_vauxoo : list[PolizaLine] = list(filter(lambda line: line.concept not in EXCLUDED_CONCEPTS, lines_vauxoo))
        return lines_vauxoo

def get_matches(lines_src, lines_target, args, src_lbl="SOURCE", target_lbl="TARGET"):

    extracted_lines_source = {}
    extracted_lines_target = {}

    if args.collapse_accounts:
        collapsed_accounts = get_collapsed_accounts(".collapse")
        for account, descr in collapsed_accounts:
            lines_src, extracted_src  = collapse_account(lines_src, account, descr)
            extracted_lines_source[account] = extracted_src
            lines_target, extracted_target = collapse_account(lines_target, account, descr)
            extracted_lines_target[account] = extracted_target


    matched_lines = []
    unmatched_lines = []

    odd_amounts_buffer = []

    for line_target in lines_target:
        if matched_line := line_has_match(line_target, lines_src, strict=args.strict, show_close_matches=args.show_close_matches):
            matched_lines.append((line_target, matched_line))
        else:
            # If line was unmatched and is accumulated line, check if by extracting one or some amounts, we could
            # actually match it to its intended target. In practice, this is used by extracting untagged spa amounts
            if acc_lines_src := extracted_lines_source.get(line_target.account):
                acc_lines_tgt = extracted_lines_target.get(line_target.account)
                target_amount = sum(float(l.amount) for l in acc_lines_tgt)
                odd_lines = get_odd_amounts_out(acc_lines_src, target_amount)
                if odd_lines:
                    add_to_odd_amounts(odd_lines, odd_amounts_buffer, src_lbl, target_lbl)
                    matched_lines.append((line_target, get_dummy_line()))
                    continue

            possible_target = get_possible_target(line_target, lines_src) or None
            unmatched_lines.append((line_target, possible_target))

    return matched_lines, unmatched_lines, odd_amounts_buffer

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

    opmode = None

    if os.path.isdir(poliza_vg) and os.path.isdir(poliza_vauxoo):
        opmode = OpMode.DIR_DIFF
    elif os.path.isfile(poliza_vg) and os.path.isfile(poliza_vauxoo):
        opmode = OpMode.SINGLE_FILE_DIFF


    if opmode == OpMode.SINGLE_FILE_DIFF:
        lines_vx = get_vx_poliza_lines(poliza_vauxoo) 
        lines_vg = get_vg_poliza_lines(poliza_vg) 
        #  matched_lines, unmatched_lines, odd_amounts_buffer = get_matches(lines_vg, lines_vx, args, src_lbl="POLIZA VG", target_lbl="POLIZA VX") 
        matched_lines, unmatched_lines, odd_amounts_buffer = get_matches(lines_vx, lines_vg, args, src_lbl="POLIZA VX", target_lbl="POLIZA VG") 

        CSV_RESULT_FILE = "POLIZA_DIFF_%s.csv"

        if args.csv_match_results:
            poliza_date = extract_poliza_date_from_fname(poliza_vg)
            with open(CSV_RESULT_FILE % poliza_date, "w") as outfile:
                writer = csv.writer(outfile, csv.QUOTE_MINIMAL)
                writer.writerow(["account", "concept", "VG-VX match"])
                for vx, vg in matched_lines:
                    writer.writerow([vx.account, vx.concept, True])
                for vx, possibly_vg in unmatched_lines:
                    writer.writerow([vx.account, vx.concept, False])

        headers = ["STATUS", "VG acc", "VG concept", "VG amount", "VX amount","VX acc", "VX concept"]
        print(tabulate_results(matched_lines, unmatched_lines,odd_amounts_buffer, headers))


    elif opmode == OpMode.DIR_DIFF:
        # Iter through files in vg dir
        for vg_poliza_fname in os.listdir(poliza_vg):
            # Extract poliza date stamp
            poliza_date_stamp = extract_poliza_date_from_fname(vg_poliza_fname)

            target_vx_fname = f"POLIZAINGRESOS_VX{poliza_date_stamp}.csv"
            target_vx_fname = os.path.join(poliza_vx, target_vx_fname)
            # Look for matching vx poliza
            if not os.path.exists(target_vx_fname):
                print(f"SKIP: {target_vx_fname} not found")
                continue
            

    else:
        print("ERROR: Unimplemented")

def tabulate_results(matched_lines, unmatched_lines, odd_amounts_buffer, headers) -> str:
    out_str = io.StringIO("")
    matched_table = ([
            ["MATCH", tgt.account, tgt.concept, format_amount((tgt.sign, tgt.amount, tgt.type)), format_amount((src.sign, src.amount, src.type)), src.account, src.concept] 
            for tgt, src in matched_lines])
    unmatched_table = ([
            ["NO MATCH", tgt.account, tgt.concept, tgt.amount, possible_tgt.amount if possible_tgt else "", possible_tgt.concept if possible_tgt else "", possible_tgt.account if possible_tgt else ""] 
            for tgt, possible_tgt in unmatched_lines])
    assert len(headers) == len(matched_table[0])
    print(tabulate.tabulate(matched_table, headers=headers), file=out_str)
    print(tabulate.tabulate(unmatched_table), file=out_str)
    for msg in odd_amounts_buffer:
        print(msg, file=out_str)
    len_target = len(matched_lines) + len(unmatched_lines)
    matches = len(matched_lines)
    non_matches = len(unmatched_lines)
    match_pctg = matches / len_target
    print("Summary:\nMatching concepts: {}\nNon matching: {}\nMatching pctg: {:.2f}%".format(matches, non_matches, match_pctg * 100), file=out_str)
    return out_str.getvalue()

    

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

def remove_unsupported_vg_lines(lines: list[PolizaLine]) ->list[PolizaLine]:
    lines = filter(lambda l: "spa" not in l.concept.lower(), lines)
    lines = filter(lambda l: "masaje" not in l.concept.lower(), lines)
    lines = filter(lambda l: "facial" not in l.concept.lower(), lines)
    lines = filter(lambda l: "boutique" not in l.concept.lower(), lines)
    return list(lines)
    

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
