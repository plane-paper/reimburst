from arq.connections import RedisSettings


class WorkerSettings:
    functions: list = []
    redis_settings = RedisSettings()
