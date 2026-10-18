"""Declarative routing: each route names its method, path and required permission."""
import re
from dataclasses import dataclass
from typing import Callable

PUBLIC = 'public'            # no login needed
AUTHENTICATED = 'authenticated'  # any logged-in user


@dataclass
class Route:
    method: str
    pattern: re.Pattern
    handler: Callable
    permission: object


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, path, handler, permission):
        """Register a route. `{name}` in the path matches a positive integer passed as `name`."""
        regex = '^' + re.sub(r'\{(\w+)\}', r'(?P<\1>[0-9]+)', path) + '$'
        self.routes.append(Route(method, re.compile(regex), handler, permission))

    def get(self, path, permission):
        return lambda handler: self.add('GET', path, handler, permission) or handler

    def post(self, path, permission):
        return lambda handler: self.add('POST', path, handler, permission) or handler

    def match(self, method, path):
        """(route, params), or (None, allowed_methods) when nothing matches."""
        allowed = set()
        for route in self.routes:
            found = route.pattern.match(path)
            if not found:
                continue
            if route.method == method:
                return route, {key: int(value) for key, value in found.groupdict().items()}
            allowed.add(route.method)
        return None, allowed
