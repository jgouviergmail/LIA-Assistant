"""Disposable Redis primitive characterization; NOT application/world code."""

import asyncio
import json
import os
from urllib.parse import unquote, urlparse
from uuid import uuid4

from redis.asyncio import Redis

ADMIT = """
local account,cap,now,ttl=ARGV[1],tonumber(ARGV[2]),tonumber(ARGV[3]),tonumber(ARGV[4])
local expired=redis.call('ZRANGEBYSCORE',KEYS[1],'-inf',now)
for _,id in ipairs(expired) do redis.call('ZREM',KEYS[1],id);redis.call('HDEL',KEYS[2],id) end
if redis.call('ZSCORE',KEYS[1],account) then return {'existing',redis.call('HGET',KEYS[2],account)} end
if not redis.call('ZSCORE',KEYS[3],account) then redis.call('ZADD',KEYS[3],redis.call('INCR',KEYS[4]),account) end
local head=redis.call('ZRANGE',KEYS[3],0,0)[1]
if redis.call('ZCARD',KEYS[1])<cap and head==account then
  redis.call('ZREM',KEYS[3],account)
  local fence=redis.call('INCR',KEYS[4])
  redis.call('ZADD',KEYS[1],now+ttl,account);redis.call('HSET',KEYS[2],account,fence)
  for _,key in ipairs(KEYS) do redis.call('EXPIRE',key,300) end
  return {'admitted',tostring(fence)}
end
for _,key in ipairs(KEYS) do redis.call('EXPIRE',key,300) end
return {'queued',tostring(redis.call('ZRANK',KEYS[3],account)+1)}
"""

RELEASE = """
if redis.call('HGET',KEYS[2],ARGV[1])~=ARGV[2] then return 0 end
redis.call('ZREM',KEYS[1],ARGV[1]);redis.call('HDEL',KEYS[2],ARGV[1]);return 1
"""


async def main():
    parsed = urlparse(os.environ['REDIS_URL'])
    kwargs = dict(host=parsed.hostname, port=parsed.port or 6379,
                  username=unquote(parsed.username) if parsed.username else None,
                  password=unquote(parsed.password) if parsed.password else None,
                  db=15, decode_responses=True, socket_timeout=5)
    clients = [Redis(**kwargs) for _ in range(4)]
    prefix = 'world-qualification:' + str(uuid4())
    keys = [prefix + suffix for suffix in (':active', ':fences', ':queue', ':sequence')]
    checks = []
    try:
        await clients[0].ping()
        for cap in (5, 10):
            await clients[0].delete(*keys)
            replies = await asyncio.gather(*[
                clients[i % 4].eval(ADMIT, 4, *keys, f'account-{i}', cap, 1000, 45)
                for i in range(100)
            ])
            assert sum(r[0] == 'admitted' for r in replies) == cap
            assert await clients[0].zcard(keys[0]) == cap
            assert await clients[0].zcard(keys[2]) == 100 - cap
            checks.append(f'{cap}: atomic cap holds under 100 concurrent requests / 4 clients')
        await clients[0].delete(*keys)
        replies = await asyncio.gather(*[
            clients[i % 4].eval(ADMIT, 4, *keys, 'one-account', 5, 1000, 45)
            for i in range(100)
        ])
        assert sum(r[0] == 'admitted' for r in replies) == 1
        assert await clients[0].zcard(keys[0]) == 1
        assert await clients[0].zcard(keys[2]) == 0
        checks.append('100 tabs/retries consume one account slot')
        await clients[0].delete(*keys)
        first = await clients[0].eval(ADMIT, 4, *keys, 'first', 1, 1000, 45)
        for account in ('second', 'third'):
            await clients[0].eval(ADMIT, 4, *keys, account, 1, 1000, 45)
        await clients[0].eval(ADMIT, 4, *keys, 'second', 1, 1000, 45)
        assert await clients[0].zrange(keys[2], 0, -1) == ['second', 'third']
        assert await clients[0].eval(RELEASE, 4, *keys, 'first', first[1]) == 1
        late = await clients[1].eval(ADMIT, 4, *keys, 'late', 1, 1001, 45)
        assert late[0] == 'queued'
        second = await clients[2].eval(ADMIT, 4, *keys, 'second', 1, 1001, 45)
        assert second[0] == 'admitted'
        checks.append('FIFO stays stable on retries; a new arrival cannot jump the queue')
        newer_fence = str(await clients[0].incr(keys[3]))
        await clients[0].hset(keys[1], 'second', newer_fence)
        assert await clients[3].eval(RELEASE, 4, *keys, 'second', second[1]) == 0
        assert await clients[0].zcard(keys[0]) == 1
        checks.append('stale controller cannot release a newer generation slot')
        third = await clients[0].eval(ADMIT, 4, *keys, 'third', 1, 1047, 45)
        assert third[0] == 'admitted'
        assert await clients[0].zcard(keys[0]) == 1
        checks.append('expired leases pruned atomically without key-expiry notification')
        reduced = await clients[0].eval(ADMIT, 4, *keys, 'late', 0, 1048, 45)
        assert reduced[0] == 'queued'
        assert await clients[0].zcard(keys[0]) == 1
        checks.append('lowering cap stops new admission without arbitrary eviction')
        print(json.dumps({'status': 'passed', 'redis_db': 15,
                          'independent_clients': 4, 'checks': checks,
                          'limits': 'Primitive spike only; no world protocol, reservations, auth or game load tested.'}, indent=2))
    finally:
        await clients[0].delete(*keys)
        for client in clients:
            await client.aclose()


asyncio.run(main())
