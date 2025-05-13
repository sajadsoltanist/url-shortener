"""Exceptions for the URL shortener service layer.

This module contains the exception hierarchy for the service layer,
providing domain-specific exceptions that abstract underlying implementation details.
"""


class ServiceError(Exception):
    """Base exception for all service-level errors."""
    pass


class URLError(ServiceError):
    """Base exception for URL-related errors."""
    pass


class URLValidationError(URLError):
    """URL failed validation checks."""
    pass


class InvalidURLError(URLValidationError):
    """The URL format is invalid."""
    pass


class URLCreationError(URLError):
    """Error occurred during URL creation."""
    pass


class ShortCodeGenerationError(URLCreationError):
    """Failed to generate a unique short code."""
    pass


class CustomCodeAlreadyExistsError(URLCreationError):
    """The requested custom code is already in use."""
    pass


class CustomCodeValidationError(URLCreationError):
    """The requested custom code doesn't meet requirements."""
    pass


class URLNotFoundError(URLError):
    """URL with the specified short code was not found."""
    pass


class URLExpiredError(URLError):
    """URL has expired and is no longer valid."""
    pass


class URLUpdateError(URLError):
    """Error occurred while updating a URL."""
    pass


class StatsError(ServiceError):
    """Base exception for statistics-related errors."""
    pass


class StatsTrackingError(StatsError):
    """Error occurred while tracking click statistics."""
    pass


class StatsRetrievalError(StatsError):
    """Error occurred while retrieving statistics."""
    pass


class CleanupError(ServiceError):
    """Base exception for cleanup-related errors."""
    pass


class ExpiredURLCleanupError(CleanupError):
    """Error occurred while cleaning up expired URLs."""
    pass 