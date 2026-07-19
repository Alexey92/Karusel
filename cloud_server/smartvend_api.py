"""
Модуль для работы с API SmartVend.
"""
import httpx
import os
from datetime import datetime

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


async def get_sales(controller_id: str, from_ts: int, to_ts: int, per_page: int = 1000):
    """Получить все продажи за период (с пагинацией)."""
    all_sales = []
    page = 1
    
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.post(
                f"{SMARTVEND_BASE}/get-list-of-sales",
                headers={"x-organization-key": SMARTVEND_KEY},
                json={
                    "dateRange": {"from": from_ts, "to": to_ts},
                    "filters": {"controllerIds": [controller_id]},
                    "pagination": {"currentPage": page, "perPage": per_page}
                }
            )
            data = resp.json()
            if data.get("result", {}).get("$case") == "success":
                items = data["result"]["success"]["items"]
                all_sales.extend(items)
                total_pages = data["result"]["success"].get("pagination", {}).get("totalPages", 1)
                if page >= total_pages or not items:
                    break
                page += 1
            else:
                break
    
    return all_sales


async def get_encashments(controller_id: str, from_ts: int, to_ts: int):
    """Получить список инкассаций за период."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-encashments-list",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={
                "dateRange": {"from": from_ts, "to": to_ts},
                "filters": {"controllerIds": [controller_id]}
            }
        )
        data = resp.json()
        if data.get("result", {}).get("$case") == "success":
            return data["result"]["success"]["items"]
        return []


async def create_encashment(controller_id: str):
    """Создать инкассацию (сбрасывает счётчики)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/create-encashment",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={"controllerId": controller_id}
        )
        return resp.json()


async def get_money_from_sales(controller_id: str, from_ts: int, to_ts: int) -> dict:
    """Получить сумму денег из продаж за период."""
    sales = await get_sales(controller_id, from_ts, to_ts)
    
    total_money = 0
    total_sales = len(sales)
    
    for sale in sales:
        # insertedMoney в копейках
        money = int(sale.get("insertedMoney", 0))
        total_money += money
    
    return {
        "total_money": total_money,  # в копейках
        "total_sales": total_sales,
        "sales": sales
    }