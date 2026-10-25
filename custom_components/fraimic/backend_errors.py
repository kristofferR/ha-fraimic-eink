"""Delivery failures shared by the scheduler and companion transport."""

from homeassistant.exceptions import HomeAssistantError


class BackendUnavailable(HomeAssistantError):
    """The companion could not durably accept the delivery."""


class BackendBusy(BackendUnavailable):
    """A voice request or previously offered image owns the frame's buffer."""


class BackendExpired(BackendUnavailable):
    """A previously accepted delivery has definitively expired."""
