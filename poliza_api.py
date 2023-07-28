#!/bin/python3
import json
from dataclasses import dataclass
from poliza2csv import EXCLUDED_CONCEPTS
from enum import Enum
from datetime import datetime
import requests
import asyncio

VG_POLIZA_URL_BASE = "https://restful.frontoffice.villagroup.com/PMSBusinessServer/BusinessServersISAPI.dll/datasnap/rest/todoo/"

active_requests = []


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


def _post_poliza_init(req: PolizaAPIRequest) -> PolizaAPIRequest:
    dt_format = "%m-%d-%Y"
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
        return data["Poliza"]
    else:
        print(response.text)


def total_by_account(lines: list[PolizaAPILine], account: str) -> float:
    account_lines = list(filter(lambda line: line.cuenta == account, lines))
    for line in account_lines:
        print(line)
    total_cargo = sum(line.cargo for line in account_lines)
    total_abono = sum(line.abono for line in account_lines)
    return PolizaAPILine(account, concepto=account_lines[0].concepto if account_lines else "", cargo=total_cargo, abono=total_abono)


def read_json_lines(fname: str):
    with open(fname, "rb") as f:
        data = json.load(f)
        lines = []
        for line in data["Poliza"]:
            api_line = PolizaAPILine(
                cuenta=line["Cuenta"], concepto=line["Concepto"], cargo=float(line["Cargo"]), abono=float(line["Abono"]))
            if api_line.concepto not in EXCLUDED_CONCEPTS:
                print(api_line)
                lines.append(api_line)
        return lines


async def push_pending_requests(active_requests_lock: asyncio.Lock, initial_requests: list, interval=350):
    while True:
        await asyncio.sleep(5)
        async with active_requests_lock:
            active_requests.append("AAAAAH")


async def get_requests_status(active_requests_lock: asyncio.Lock, interval=10):
    while True:
        await asyncio.sleep(10)
        async with active_requests_lock:
            for req in active_requests:
                print(req)


async def main():
    active_requests_lock = asyncio.Lock()
    await asyncio.gather(push_pending_requests(active_requests_lock, []), get_requests_status(active_requests_lock))


if __name__ == "__main__":
    asyncio.run(main())
