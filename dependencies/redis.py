# dependencies/redis.py
from redis.asyncio import Redis
from redis.exceptions import RedisError
from fastapi import Depends, HTTPException

def get_redis() -> Redis:
    try:
        redis = Redis(host="localhost", port=6379, decode_responses=True)
        return redis
    except RedisError:
        raise HTTPException(status_code=500, detail="Redis connection error")

