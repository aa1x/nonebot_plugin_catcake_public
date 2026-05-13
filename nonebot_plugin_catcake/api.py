from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class CatcakeApi:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def weekly_count(self) -> int:
        data = await self._get_json("/api/weekly-count")
        return int(data.get("count", 0))

    async def search(self, server: str) -> List[Dict[str, Any]]:
        data = await self._get_json("/api/search", params={"server": server})
        if isinstance(data, list):
            return data
        return []

    async def daily_aji(self, server: str) -> Optional[str]:
        data = await self._get_json("/api/daily-aji", params={"server": server})
        uid = data.get("uid") if isinstance(data, dict) else None
        return str(uid) if uid else None

    async def upload(
        self,
        server: str,
        uid: str,
        cat_cakes: List[str],
        cat_locations: List[str] | None = None,
    ) -> bool:
        payload = {
            "uid": uid,
            "server": server,
            "cat_cakes": cat_cakes,
            "cat_locations": cat_locations or [],
        }
        data = await self._post_json("/api/cat-cakes", json=payload)
        return bool(data.get("success")) if isinstance(data, dict) else False

    async def upload_aji(self, server: str, uid: str) -> bool:
        payload = {"uid": uid, "server": server}
        data = await self._post_json("/api/daily-aji", json=payload)
        return bool(data.get("success")) if isinstance(data, dict) else False

    async def _get_json(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def _post_json(self, path: str, json: Dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}{path}", json=json)
            response.raise_for_status()
            return response.json()
