#!/bin/python3
import json
from dataclasses import dataclass
from poliza2csv import EXCLUDED_CONCEPTS
from enum import Enum
from datetime import datetime, timedelta
import requests
import asyncio
import os

VG_POLIZA_URL_BASE = "https://restful.frontoffice.villagroup.com/PMSBusinessServer/BusinessServersISAPI.dll/datasnap/rest/todoo/"

MAX_ACTIVE_REQUESTS = 1

POLIZA_OUTPUT_DIR = "/home/carlos-vx/Vauxoo/poliza/polizas_api/"

active_requests = []
pending_downloads = set()
initial_requests = []
global_exit_flag = []


@dataclass
class PolizaAPILine:
    cuenta: str
    concepto: str
    cargo: float
    abono: float


class PolizaRequestStatus(Enum):
    UNSENT = 1
    ACTIVE = 2
    COMPLETED = 3
    ERROR = 4


class PolizaAPIRequest:
    id: int = 0
    status: PolizaRequestStatus = PolizaRequestStatus.UNSENT
    start_date: datetime
    end_date: datetime
    resort_id: int = 0
    response: str = ""

    def __init__(self, start_date, end_date, resort_id=16):
        self.status = PolizaRequestStatus.UNSENT
        self.start_date = start_date
        self.end_date = end_date
        self.resort_id = resort_id

    def __repr__(self):
        return f"APIRequest(id={self.id}, start_date={self.start_date.strftime('%d-%m-%Y')}, end_date={self.end_date.strftime('%d-%m-%Y')})"


def _post_poliza_init(req: PolizaAPIRequest) -> PolizaAPIRequest:
    dt_format = "%d-%m-%Y"
    params = {
        "idResort": req.resort_id,
        "FechaIni": req.start_date.strftime(dt_format),
        "FechaFin": req.end_date.strftime(dt_format)
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        VG_POLIZA_URL_BASE + "ProcesaPoliza", data=json.dumps(params), headers=headers)
    if response.status_code == 200:
        req.status = PolizaRequestStatus.ACTIVE
        resp_data = response.json()
        print(resp_data)
        req.id = int(resp_data["Valor"])
    else:
        req.status = PolizaRequestStatus.ERROR
    return req


def _get_request_status(req: PolizaAPIRequest) -> PolizaRequestStatus:
    response = requests.get(VG_POLIZA_URL_BASE +
                            f"EstadoProceso/{req.resort_id}/{req.id}")
    if response:
        data = response.json()
        status = data["Estatus"]
        if status == "Terminado":
            return PolizaRequestStatus.COMPLETED
        elif status == "Activo":
            return PolizaRequestStatus.ACTIVE


def _get_poliza(date, resort_id=16) -> dict:
    response = requests.get(VG_POLIZA_URL_BASE +
                            f"Poliza/{resort_id}/{date.strftime('%d-%m-%Y')}")
    if response:
        data = response.json()
        return data
    else:
        print(response.text)


def total_by_account(lines: list[PolizaAPILine], account: str) -> float:
    account_lines = list(filter(lambda line: line.cuenta == account, lines))
    for line in account_lines:
        print(line)
    total_cargo = sum(line.cargo for line in account_lines)
    total_abono = sum(line.abono for line in account_lines)
    return PolizaAPILine(account, concepto=account_lines[0].concepto if account_lines else "", cargo=total_cargo, abono=total_abono)


def daterange(start_date, end_date, step=1):
    "Works as python range() but inclusive on end_date"
    for n in range(0, int((end_date - start_date).days+1), step):
        yield start_date + timedelta(n)


def get_requests_in_range(start_date, end_date, dates_per_req=1):
    requests = []
    days = list(daterange(start_date, end_date))
    for i in range(0, len(days), dates_per_req):
        day_range = days[i:i+dates_per_req+1]
        req = PolizaAPIRequest(day_range[0], day_range[-1])
        requests.append(req)
    return requests


def read_json_lines(json):
    lines = []
    for line in json["Poliza"]:
        api_line = PolizaAPILine(
            cuenta=line["Cuenta"], concepto=line["Concepto"], cargo=float(line["Cargo"]), abono=float(line["Abono"]))
        if api_line.concepto not in EXCLUDED_CONCEPTS:
            lines.append(api_line)
    return lines


async def push_pending_requests(initial_requests_lock, active_requests_lock, interval=60):
    while True:
        async with active_requests_lock, initial_requests_lock:
            try:
                next_req = initial_requests.pop()
                if len(active_requests) >= MAX_ACTIVE_REQUESTS:
                    print("Active queue is full. Going to sleep")
                    initial_requests.append(next_req)
                else:
                    print(f"Posting request for {next_req}")
                    active_req = _post_poliza_init(next_req)
                    print(active_req)
                    if active_req.status != PolizaRequestStatus.ACTIVE:
                        # Something went wrong
                        print(
                            f"Something went wrong for request {active_req}")
                        initial_requests.append(active_req)
                    else:
                        active_requests.append(active_req)

            except IndexError:
                # Reached end of initial requests list
                print(f"No more initial requests to process. Exiting.")
                return
        await asyncio.sleep(interval)


async def update_requests_status(active_requests_lock, exit_flag_lock, interval=30):
    while True:
        await asyncio.sleep(interval)
        async with active_requests_lock:
            if len(active_requests) == 0:
                print("Active requests queue empty")
            else:
                print("Active requests:")
            for req in active_requests:
                print(f"Ping {req}")
                status = _get_request_status(req)
                if status != req.status:
                    print(
                        f"Status for request {req} changed from {req.status} to {status}")
                req.status = status
        async with exit_flag_lock:
            if global_exit_flag:
                return


async def transfer_requests_to_pending_download_queue(active_requests_lock, pending_downloads_lock, exit_flag_lock, interval=30):
    while True:
        await asyncio.sleep(interval)
        async with active_requests_lock, pending_downloads_lock:
            try:
                possibly_done = active_requests.pop()
                if possibly_done.status == PolizaRequestStatus.COMPLETED:
                    print(
                        f"Transfering {possibly_done} to pending downloads queue")
                    # If a request goes from 01/12 to 05/12, that means it is only processing until 04/12, so it only
                    # should account for those days when downloading, and the next request will process 05/12
                    for dt in daterange(possibly_done.start_date, possibly_done.end_date - timedelta(days=1)):
                        pending_downloads.add(dt)
                elif possibly_done.status == PolizaRequestStatus.ACTIVE:
                    active_requests.append(possibly_done)
                else:
                    print(
                        f"Something went wrong on transfer queue, req: {possibly_done}")
                    active_requests.append(possibly_done)
            except IndexError:
                # Active requests queue empty
                pass
        async with exit_flag_lock:
            if global_exit_flag:
                return


async def get_payloads(pending_downloads_lock, exit_flag_lock, interval=30):
    while True:
        await asyncio.sleep(interval)
        async with pending_downloads_lock:
            try:
                date_to_download = pending_downloads.pop()
                print(f"Getting payload for {date_to_download}")
                data = _get_poliza(date_to_download)
                if data:
                    fname = date_to_download.strftime(
                        "POLIZAINGRESOS_%Y%m%d.json")
                    with open(os.path.join(POLIZA_OUTPUT_DIR, fname), "w") as file:
                        json.dump(data, file)
            except KeyError:
                # Empty completed queue
                print("No pending payloads to process")
        async with exit_flag_lock:
            if global_exit_flag:
                return


async def supervisor(initial_requests_lock, active_requests_lock, pending_downloads_lock, exit_flag_lock, interval=30):
    while True:
        async with initial_requests_lock, active_requests_lock, pending_downloads_lock, exit_flag_lock:
            if (len(initial_requests) == 0
                and len(active_requests) == 0
                    and len(pending_downloads) == 0):
                global_exit_flag.append(True)
            if global_exit_flag:
                return
        await asyncio.sleep(interval)


async def main():
    d0 = datetime(2023, 1, 1)
    # The API is not inclusive on end date
    df = datetime(2023, 2, 12) + timedelta(days=1)

    print("Initial requests:")
    for req in get_requests_in_range(d0, df, 1):
        print(req)
        initial_requests.append(req)
    initial_requests.reverse()
    initial_requests_lock = asyncio.Lock()
    active_requests_lock = asyncio.Lock()
    pending_downloads_lock = asyncio.Lock()
    exit_flag_lock = asyncio.Lock()
    await asyncio.gather(
        push_pending_requests(initial_requests_lock,
                              active_requests_lock),
        update_requests_status(active_requests_lock,
                               exit_flag_lock, 15),
        transfer_requests_to_pending_download_queue(
            active_requests_lock,
            pending_downloads_lock,
            exit_flag_lock, 15),
        get_payloads(pending_downloads_lock, exit_flag_lock, 10),
        supervisor(initial_requests_lock,
                   active_requests_lock,
                   pending_downloads_lock,
                   exit_flag_lock, 5)
    )
    print("Finished!")


if __name__ == "__main__":
    asyncio.run(main())
