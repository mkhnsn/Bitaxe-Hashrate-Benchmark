"""Async HTTP client for Bitaxe API."""

from typing import Optional

import httpx

from ..models import DeviceInfo


class BitaxeClient:
    """Async client for communicating with Bitaxe devices."""

    def __init__(self, ip: str, timeout: float = 10.0):
        """Initialize the Bitaxe client.

        Args:
            ip: IP address of the Bitaxe device (without http://).
            timeout: Request timeout in seconds.
        """
        self.base_url = f"http://{ip}"
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BitaxeClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, creating one if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def get_system_info(self) -> Optional[dict]:
        """Fetch system info from the Bitaxe.

        Returns:
            System info dict or None on failure.
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/system/info")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    async def get_asic_info(self) -> Optional[dict]:
        """Fetch ASIC info from the Bitaxe.

        Returns:
            ASIC info dict or None on failure.
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/system/asic")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    async def fetch_device_info(self) -> DeviceInfo:
        """Fetch complete device information.

        Returns:
            DeviceInfo with all device details.

        Raises:
            ConnectionError: If device info cannot be fetched.
        """
        # Get system info first (required for small_core_count)
        system_info = await self.get_system_info()
        if not system_info:
            raise ConnectionError("Failed to fetch system info from Bitaxe")

        if "smallCoreCount" not in system_info:
            raise ConnectionError("smallCoreCount field missing from /api/system/info")

        small_core_count = system_info["smallCoreCount"]

        # Check if system_info has all we need
        has_voltage = "coreVoltage" in system_info
        has_frequency = "frequency" in system_info
        has_asic_count = "asicCount" in system_info

        if has_voltage and has_frequency and has_asic_count:
            return DeviceInfo(
                hostname=system_info.get("hostname"),
                mac_address=system_info.get("macAddr"),
                small_core_count=small_core_count,
                asic_count=system_info.get("asicCount", 1),
                default_voltage=system_info.get("coreVoltage", 1150),
                default_frequency=system_info.get("frequency", 500),
                firmware_version=system_info.get("version"),
            )

        # Try ASIC endpoint for remaining info
        asic_info = await self.get_asic_info()
        if not asic_info:
            raise ConnectionError("Failed to fetch ASIC info from Bitaxe")

        return DeviceInfo(
            hostname=system_info.get("hostname"),
            mac_address=system_info.get("macAddr"),
            small_core_count=small_core_count,
            asic_count=asic_info.get("asicCount", 1),
            default_voltage=asic_info.get("defaultVoltage", 1150),
            default_frequency=asic_info.get("defaultFrequency", 500),
            firmware_version=system_info.get("version"),
        )

    async def set_settings(self, core_voltage: int, frequency: int) -> bool:
        """Apply voltage and frequency settings.

        Args:
            core_voltage: Core voltage in mV.
            frequency: Frequency in MHz.

        Returns:
            True if settings were applied successfully.
        """
        settings = {"coreVoltage": core_voltage, "frequency": frequency}
        try:
            response = await self.client.patch(
                f"{self.base_url}/api/system", json=settings
            )
            response.raise_for_status()
            return True
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    async def restart(self) -> bool:
        """Restart the Bitaxe system.

        Returns:
            True if restart command was sent successfully.
        """
        try:
            response = await self.client.post(f"{self.base_url}/api/system/restart")
            response.raise_for_status()
            return True
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
