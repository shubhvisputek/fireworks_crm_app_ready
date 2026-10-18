"""Application errors. Each carries the HTTP status the web layer should return."""


class AppError(Exception):
    status = 400

    def __init__(self, message, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self):
        return {'error': self.message, **self.details}


class ValidationError(AppError):
    status = 400


class NotFoundError(AppError):
    status = 404


class AuthenticationError(AppError):
    status = 401


class PermissionDenied(AppError):
    status = 403


class RateLimited(AppError):
    status = 429
