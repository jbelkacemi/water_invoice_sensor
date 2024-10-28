"""Platform for water invoice sensor integration."""
from __future__ import annotations
import requests
import logging
import time
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

def get_token() -> str | None:
    """Obtain the access token for the API."""
    url_token = "https://api-ae.acciona.com/ova-agua-login/token"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "grant_type": "client_credentials"
    }

    response = requests.post(url_token, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        _LOGGER.error("Error al obtener el token: %s", response.text)
        return None

def get_control_info(token: str, username: str, password: str, device_token: str) -> dict | None:
    """Login and obtain user information."""
    url_login = "https://api-ae.acciona.com/ova-agua-login/login"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8"
    }
    payload = {
        "username": username,
        "password": password,
        "deviceToken": device_token
    }

    response = requests.post(url_login, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get('userInfo')
    else:
        _LOGGER.error("Error al obtener la información del usuario: %s", response.text)
        return None

def get_invoice_data(username: str, password: str, device_token: str, client_code: str, contract_reference: str) -> dict | None:
    """Retrieve the last invoice information."""
    token = get_token()
    if not token:
        return None

    control_info = get_control_info(token, username, password, device_token)
    if not control_info:
        return None

    invoices_url = f"https://api-ae.acciona.com/ova-agua-invoice/api/v1/concession/LU/supply/{contract_reference}/invoice/last-invoice?subjectCode={client_code}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {token}",
        "Control-Info": str(control_info),
    }

    response = requests.get(invoices_url, headers=headers)
    if response.status_code == 200:
        invoice_code = response.json().get('invoiceCode')
        detail_url = f"https://api-ae.acciona.com/ova-agua-invoice/api/v1/concession/LU/supply/{contract_reference}/invoice/detail?invoiceCode={invoice_code}&subjectCode={client_code}"
        response_detail = requests.get(detail_url, headers=headers)
        if response_detail.status_code == 200:
            return response_detail.json()
        else:
            _LOGGER.error("Error al obtener el detalle de la factura: %s", response_detail.text)
    else:
        _LOGGER.error("Error al obtener la factura: %s", response.text)
    return None

def get_telemetry_data(username: str, password: str, device_token: str, contract_reference: str) -> dict | None:
    """Retrieve telemetry information."""
    token = get_token()
    if not token:
        return None

    control_info = get_control_info(token, username, password, device_token)
    if not control_info:
        return None

    telemetry_url = f"https://api-ae.acciona.com/ova-agua-invoice/api/v1/concession/LU/supply/{contract_reference}/consumption/telemeter-info"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {token}",
        "Control-Info": str(control_info),
    }

    response = requests.get(telemetry_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        _LOGGER.error("Error al obtener la telemetría: %s", response.text)
        return None

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the water invoice sensor platform."""
    username = config.get('username')
    password = config.get('password')
    device_token = config.get('deviceToken')
    client_code = config.get('client_code')
    contract_reference = config.get('contract_reference')
    update_interval_hours = config.get('update_interval_hours', 24)  # Valor por defecto de 24 horas

    add_entities([
        WaterInvoiceSensor(username, password, device_token, client_code, contract_reference, update_interval_hours),
        TelemetrySensor(username, password, device_token, contract_reference, update_interval_hours)
    ])

class WaterInvoiceSensor(SensorEntity):
    """Representation of a Water Invoice Sensor."""

    _attr_name = "Última Factura de Agua"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "€"

    def __init__(self, username: str, password: str, device_token: str, client_code: str, contract_reference: str, update_interval_hours: int = 24):
        """Initialize the sensor."""
        self._username = username
        self._password = password
        self._device_token = device_token
        self._contract_reference = contract_reference
        self._client_code = client_code
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._update_interval_seconds = update_interval_hours * 3600  # Convertir horas a segundos
        self._last_update = 0

    def update(self) -> None:
        """Fetch new state data for the sensor, only if the update interval has passed."""
        current_time = time.time()
        if current_time - self._last_update >= self._update_interval_seconds:
            invoice_data = get_invoice_data(self._username, self._password, self._device_token, self._client_code, self._contract_reference)
            if invoice_data:
                self._attr_native_value = invoice_data.get('amount')
                self._attr_extra_state_attributes = {
                    "invoiceType": invoice_data.get('invoiceType'),
                    "invoiceCode": invoice_data.get('invoiceCode'),
                    "lapseKey": str(invoice_data.get('lapseKey')) + " - " + str(invoice_data.get('lapseYear')),
                    "consumption": invoice_data.get('consumption'),
                    "paymentState": invoice_data.get('paymentState'),
                    "actualReading": invoice_data.get('actualReading'),
                    "previousReading": invoice_data.get('previousReading'),
                }
            else:
                self._attr_native_value = None
            self._last_update = current_time

class TelemetrySensor(SensorEntity):
    """Representation of a Telemetry Sensor."""

    _attr_name = "Sensor de Telemetría"
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "m³"

    def __init__(self, username: str, password: str, device_token: str, contract_reference: str, update_interval_hours: int = 24):
        """Initialize the sensor."""
        self._username = username
        self._password = password
        self._device_token = device_token
        self._contract_reference = contract_reference
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._update_interval_seconds = update_interval_hours * 3600
        self._last_update = 0

    def update(self) -> None:
        """Fetch new state data for the sensor, only if the update interval has passed."""
        current_time = time.time()
        if current_time - self._last_update >= self._update_interval_seconds:
            telemetry_data = get_telemetry_data(self._username, self._password, self._device_token, self._contract_reference)
            if telemetry_data:
                self._attr_native_value = telemetry_data.get('reading')
                self._attr_extra_state_attributes = {
                    "telemeterNumber": telemetry_data.get('telemeterNumber'),
                    "readingDate": telemetry_data.get('readingDate'),
                }
            else:
                self._attr_native_value = None
            self._last_update = current_time
