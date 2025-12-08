"""Parse BeerXML files to Python dict."""
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Union
from defusedxml import ElementTree as DefusedET


class BeerXMLParser:
    """Parse BeerXML 1.0 format (with Brewfather extensions)."""

    def parse(self, xml_content: str) -> Dict[str, Any]:
        """Parse BeerXML string to nested dict.

        Args:
            xml_content: BeerXML file content as string

        Returns:
            Nested dict matching BeerXML structure

        Raises:
            ValueError: Invalid XML format
        """
        try:
            root = DefusedET.fromstring(xml_content.encode('utf-8'))
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}")

        # Return the root element as a dict with its tag as the key
        return {root.tag: self._element_to_dict(root)}

    def _element_to_dict(self, element: ET.Element) -> Union[Dict[str, Any], str]:
        """Convert XML element to dict or string.

        Returns dict of child elements, or string for leaf nodes.
        """
        # Process child elements
        children = list(element)

        if not children:
            # Leaf node - return text content
            text = element.text
            return text.strip() if text else ""

        # Build dict of children
        result = {}
        for child in children:
            child_value = self._element_to_dict(child)

            if child.tag in result:
                # Multiple elements with same tag - convert to list
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_value)
            else:
                result[child.tag] = child_value

        return result
