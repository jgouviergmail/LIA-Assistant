"""Atomic Redis ownership transitions for the account's Live record and side lists."""

CLAIM = """
if redis.call('EXISTS', KEYS[1]) ~= 0 then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('DEL', KEYS[3], KEYS[4])
return 1
"""

EXTEND = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
local raw = redis.call('GET', KEYS[2])
if not raw then return 0 end
local ok, record = pcall(cjson.decode, raw)
if not ok or (record.record_revision or 0) ~= tonumber(ARGV[4]) then return 0 end
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
for index = 3, #KEYS do redis.call('EXPIRE', KEYS[index], ARGV[3]) end
return 1
"""

READ = """
local token = redis.call('GET', KEYS[1])
local raw = redis.call('GET', KEYS[2])
if not token or not raw then return false end
local ok, record = pcall(cjson.decode, raw)
if not ok or record.token ~= token then return false end
return raw
"""

RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('DEL', unpack(KEYS))
return 1
"""

APPEND = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return -1 end
local limit = tonumber(ARGV[3])
local room = limit >= 0 and limit - redis.call('LLEN', KEYS[2]) or #ARGV - 3
local kept = math.max(0, math.min(room, #ARGV - 3))
for index = 1, kept do redis.call('RPUSH', KEYS[2], ARGV[index + 3]) end
redis.call('EXPIRE', KEYS[2], ARGV[2])
return kept
"""

READ_LIST = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return false end
return redis.call('LRANGE', KEYS[2], 0, -1)
"""

DRAIN = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return false end
local rows = redis.call('LRANGE', KEYS[2], 0, tonumber(ARGV[2]) - 1)
redis.call('LTRIM', KEYS[2], #rows, -1)
return rows
"""
