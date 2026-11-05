"""Bounded file cache, invalidated by file revision; callers get independent copies."""
import copy,json
from functools import lru_cache
@lru_cache(maxsize=8)
def _read(path,mtime_ns,size):
    with open(path,encoding='utf-8') as source:return json.load(source)
def read_profile(path):
    stat=path.stat();return copy.deepcopy(_read(str(path),stat.st_mtime_ns,stat.st_size))
