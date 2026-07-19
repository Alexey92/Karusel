"""
Тестовый скрипт для проверки API SmartVend.
Запуск: python3.12 smartvend_test.py
"""
import asyncio
import httpx

SMARTVEND_BASE = "https://api.smartvend.ru/v1"
SMARTVEND_KEY = "302a300506032b6570032100d41f51080cb63a02b7df51ee717205d5ba881fc945cf69ae7eb07fd96cc11589"  


async def get_controllers():
    """Получить список контроллеров."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-list-of-controllers",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={"filters": {}}
        )
        return resp.status_code, resp.json()


async def get_controller_state(controller_id: str):
    """Получить состояние контроллера (деньги, ошибки, статус)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-controller-state",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={"controllerId": controller_id}
        )
        return resp.status_code, resp.json()


async def get_sales(controller_id: str, from_ts: int, to_ts: int):
    """Получить продажи за период."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SMARTVEND_BASE}/get-list-of-sales",
            headers={"x-organization-key": SMARTVEND_KEY},
            json={
                "dateRange": {"from": from_ts, "to": to_ts},
                "filters": {"controllerIds": [controller_id]},
                "pagination": {"currentPage": 1, "perPage": 10}
            }
        )
        return resp.status_code, resp.json()


async def main():
    print("=== Тест API SmartVend ===\n")

    # 1. Получаем список контроллеров
    print("1. Список контроллеров:")
    status, data = await get_controllers()
    print(f"   Статус: {status}")
    if data.get("result", {}).get("$case") == "success":
        controllers = data["result"]["success"]["items"]
        for c in controllers:
            print(f"   - {c['humanName']} (ID: {c['id'][:8]}...)")
        print(f"   Всего: {len(controllers)} шт.\n")

        if controllers:
            test_id = controllers[0]["id"]
            
            # 2. Состояние первого контроллера
            print(f"2. Состояние контроллера {test_id[:8]}...:")
            status, data = await get_controller_state(test_id)
            print(f"   Статус: {status}")
            if data.get("result", {}).get("$case") == "success":
                state = data["result"]["success"]["data"]
                print(f"   Статус: {state.get('connectionStatus')}")
                print(f"   Денег всего (insertedMoney): {state.get('mc', '?')}")
                print(f"   Денег купюрами (bill): {state.get('bc', '?')}")
                print(f"   Денег монетами (coin): {state.get('cc', '?')}")
            print()

            # 3. Продажи за последние 7 дней
            import time
            now = int(time.time())
            week_ago = now - 7 * 24 * 3600
            print(f"3. Продажи за последние 7 дней:")
            status, data = await get_sales(test_id, week_ago, now)
            print(f"   Статус: {status}")
            if data.get("result", {}).get("$case") == "success":
                sales = data["result"]["success"]["items"]
                total_money = sum(int(s.get("insertedMoney", 0)) for s in sales)
                print(f"   Продаж: {len(sales)}")
                print(f"   Денег всего: {total_money} копеек ({total_money / 100:.2f} руб)")
    else:
        print(f"   Ошибка: {data}")

    print("\n=== Тест завершён ===")


if __name__ == "__main__":
    asyncio.run(main())