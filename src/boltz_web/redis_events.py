from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis import Redis

from boltz_web.config import load_settings


settings = load_settings()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def publish_job_event(user_id: str, job_id: str, event: str, payload: dict[str, Any]) -> None:
    message = {
        "ts": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "job_id": job_id,
        "event": event,
        "payload": payload,
    }
    key = f"boltz:user:{user_id}:job:{job_id}:events"
    redis_client.rpush(key, json.dumps(message, ensure_ascii=False))
    redis_client.ltrim(key, -200, -1)
    redis_client.publish(f"boltz:user:{user_id}:jobs", json.dumps(message, ensure_ascii=False))


def list_job_events(user_id: str, job_id: str) -> list[dict[str, Any]]:
    key = f"boltz:user:{user_id}:job:{job_id}:events"
    return [json.loads(item) for item in redis_client.lrange(key, 0, -1)]

