"""Parse configuration.xml and device.xml from .pcfg archives."""

from dataclasses import dataclass
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as ET


@dataclass
class DeviceInfo:
    """Device identity extracted from device.xml."""

    serial_number: str
    device_type: str
    firmware_version: str


@dataclass
class ConfigParam:
    """Single configuration parameter with section, ID, and value."""

    section: str  # "OBL" or "OPT"
    param_id: int
    value: str


def _find_element_value(
    root: Element,
    tag_names: tuple[str, ...],
    attr_names: tuple[str, ...],
    name_attr_value: str,
) -> str:
    """Search elements by tag name, 'name' attribute, or fallback attribute names."""
    # First pass: match by tag or name= attribute
    for elem in root.iter():
        tag = elem.tag.lower()
        if tag in tag_names or elem.get("name") == name_attr_value:
            return elem.text or elem.get("val", "")

    # Fallback: search for specific attributes on any element
    for elem in root.iter():
        for attr in attr_names:
            if attr in elem.attrib:
                return elem.attrib[attr]

    return ""


def parse_device_xml(content: bytes) -> DeviceInfo:
    """Extract device identity from device.xml."""
    root = ET.fromstring(content)

    serial = _find_element_value(
        root,
        tag_names=("serialnumber",),
        attr_names=("SN", "sn", "SerialNumber"),
        name_attr_value="SerialNumber",
    )
    device_type = _find_element_value(
        root,
        tag_names=("devicetype",),
        attr_names=("DeviceType", "devicetype", "Type"),
        name_attr_value="DeviceType",
    )
    firmware = _find_element_value(
        root,
        tag_names=("swversion",),
        attr_names=(),
        name_attr_value="SWVersion",
    )

    return DeviceInfo(
        serial_number=serial or "unknown",
        device_type=device_type,
        firmware_version=firmware,
    )


def parse_configuration_xml(content: bytes) -> list[ConfigParam]:
    """Extract therapy parameters from configuration.xml."""
    root = ET.fromstring(content)
    params: list[ConfigParam] = []

    for section_tag in ("OBL", "OPT"):
        section_elem = root.find(f".//{section_tag}")
        if section_elem is None:
            continue
        for p_elem in section_elem.findall("P"):
            param_id = p_elem.get("id")
            value = p_elem.get("val")
            if param_id is not None and value is not None:
                params.append(
                    ConfigParam(
                        section=section_tag,
                        param_id=int(param_id),
                        value=value,
                    ),
                )

    return params
