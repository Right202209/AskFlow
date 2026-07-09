"""最小示例：用 FastAPI 把本目录下的 orders.csv 暴露成 AskFlow 的 search_order webhook。

运行方法：
    python docs/examples/order_webhook_demo.py
然后在 .env 配置：
    ORDER_LOOKUP_WEBHOOK_URL=http://localhost:9100/lookup
重启 AskFlow，前端聊天页问"查我的订单 AB12345678"即可看到真数据。
"""

from __future__ import annotations

import csv
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException

ORDERS_CSV = Path(__file__).with_name("orders.csv")
app = FastAPI()


def _load_orders() -> dict[str, dict]:
    with ORDERS_CSV.open(newline="", encoding="utf-8") as fh:
        return {row["order_id"]: row for row in csv.DictReader(fh)}


@app.get("/lookup")
def lookup(order_id: str) -> dict:
    record = _load_orders().get(order_id)
    if not record:
        raise HTTPException(status_code=404, detail="order not found")
    return record


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9100)
