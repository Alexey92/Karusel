"""
Модуль для работы с API SmartVend.
"""
import httpx
import os

SMARTVEND_BASE = "https://api.smartvend.ru/v1"
SMARTVEND_KEY = os.getenv("SMARTVEND_API_KEY", "302a300506032b6570032100d41f51080cb63a02b7df51ee717205d5ba881fc945cf69ae7eb07fd96cc11589")


async def get_controllers():
    """Получить список всех контроллеров."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-list-of-controllers",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={"filters": {}}
        )
        data = resp.json()
        if data.get("result", {}).get("$case") == "success":
            return data["result"]["success"]["items"]
        return []


async def get_sales(controller_id: str, from_ts: int, to_ts: int):
    """Получить продажи за период (UNIX timestamp)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-list-of-sales",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={
                "dateRange": {"from": from_ts, "to": to_ts},
                "filters": {"controllerIds": [controller_id]},
                "pagination": {"currentPage": 1, "perPage": 1000}
            }
        )
        data = resp.json()
        if data.get("result", {}).get("$case") == "success":
            return data["result"]["success"]["items"]
        return []