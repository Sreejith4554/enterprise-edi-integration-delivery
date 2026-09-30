"""Explicit JSON/EDI adapters; supports only the documented strict ORDERS subset."""

import json
from datetime import datetime

from app.schemas import CanonicalPurchaseOrder, business_validate


def parse_edi(raw: str) -> dict:
    if not raw.strip().endswith("'") or any(c in raw for c in "?\x00"):
        raise ValueError("Segments must end with apostrophe; release characters are unsupported")
    segments = [s.strip().split("+") for s in raw.strip().split("'") if s.strip()]
    if not segments or segments[0][0] != "UNH" or segments[-1][0] != "UNT":
        raise ValueError("UNH and UNT must frame one message")
    data, items, seen = {}, [], set()
    for s in segments:
        tag = s[0]
        try:
            key = tag + (":" + s[1].split(":")[0] if tag in {"DTM", "NAD"} else "")
            if tag not in {"LIN", "IMD", "QTY", "PRI"}:
                if key in seen:
                    raise ValueError(f"Duplicate {key}")
                seen.add(key)
            if tag == "UNH":
                if len(s) != 3 or s[2] != "ORDERS:D:96A:UN":
                    raise ValueError("Expected ORDERS:D:96A:UN")
                reference = s[1]
            elif tag == "BGM":
                if len(s) != 4 or s[1] != "220" or s[3] != "9":
                    raise ValueError("Expected original purchase order BGM+220+id+9")
                data["external_order_id"] = s[2]
            elif tag == "DTM":
                qualifier, value, fmt = s[1].split(":")
                if qualifier not in {"137", "2"} or fmt != "102" or len(s) != 2:
                    raise ValueError("Unsupported DTM")
                data[{"137": "order_date", "2": "requested_delivery_date"}[qualifier]] = (
                    datetime.strptime(value, "%Y%m%d").date().isoformat()
                )
            elif tag == "NAD" and s[1] == "BY":
                if len(s) != 3:
                    raise ValueError("Expected NAD+BY+customer")
                data["customer_id"] = s[2]
            elif tag == "NAD" and s[1] == "DP":
                if len(s) != 7:
                    raise ValueError("Expected NAD+DP+name+street+city+postal+country")
                data["ship_to"] = dict(
                    zip(["name", "street", "city", "postal_code", "country"], s[2:], strict=True)
                )
            elif tag == "CUX":
                qualifier, currency, usage = s[1].split(":")
                if len(s) != 2 or qualifier != "2" or usage != "9":
                    raise ValueError("Expected CUX+2:currency:9")
                data["currency"] = currency
            elif tag == "LIN":
                if len(s) != 4 or s[2] or not s[3].endswith(":SA"):
                    raise ValueError("Expected LIN+number++sku:SA")
                items.append({"line_number": int(s[1]), "sku": s[3][:-3]})
            elif tag in {"IMD", "QTY", "PRI"}:
                if not items:
                    raise ValueError("Item segment before LIN")
                item = items[-1]
                field = {"IMD": "description", "QTY": "quantity", "PRI": "unit_price"}[tag]
                if field in item:
                    raise ValueError(f"Duplicate {tag} within line")
                if tag == "IMD":
                    if len(s) != 3 or s[1] != "F":
                        raise ValueError("Expected IMD+F+description")
                    item[field] = s[2]
                elif tag == "QTY":
                    q, value, unit = s[1].split(":")
                    if len(s) != 2 or q != "21":
                        raise ValueError("Expected QTY+21:quantity:unit")
                    item.update(quantity=value, unit=unit)
                else:
                    q, value = s[1].split(":")
                    if len(s) != 2 or q != "AAA":
                        raise ValueError("Expected PRI+AAA:price")
                    item[field] = value
            elif tag == "UNT":
                if len(s) != 3 or int(s[1]) != len(segments) or s[2] != reference:
                    raise ValueError("UNT count/reference mismatch")
            else:
                raise ValueError(f"Unsupported segment: {tag}")
        except (IndexError, UnboundLocalError) as exc:
            raise ValueError(f"Malformed {tag} segment") from exc
    required = {"UNH", "BGM", "DTM:137", "DTM:2", "NAD:BY", "NAD:DP", "CUX", "UNT"}
    if not required <= seen:
        raise ValueError("Missing mandatory segments: " + ", ".join(sorted(required - seen)))
    return dict(data, items=items)


def map_order(raw: str, source: str) -> CanonicalPurchaseOrder:
    data = json.loads(raw) if source == "JSON" else parse_edi(raw)
    order = CanonicalPurchaseOrder.model_validate(data)
    business_validate(order)
    return order


def acknowledgement(order: dict, erp_id: str, correlation_id: str, source: str) -> dict:
    result = {
        "correlation_id": correlation_id,
        "external_order_id": order["external_order_id"],
        "erp_order_id": erp_id,
        "status": "ACCEPTED",
    }
    if source == "EDI":
        result["edi"] = (
            f"UNH+{correlation_id}+ORDRSP:D:96A:UN'"
            f"BGM+231+{erp_id}+29'RFF+ON:{order['external_order_id']}'"
            f"UNT+4+{correlation_id}'"
        )
    return result
