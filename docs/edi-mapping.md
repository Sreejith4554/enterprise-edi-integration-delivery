# Implemented mapping contract, version 1

This deliberately narrow text format borrows EDIFACT segment names; it is not a full EDIFACT implementation or compliance claim. One UNH/UNT message per request, apostrophe terminators, plus-delimited elements, colon-delimited components. UTF-8 and surrounding segment whitespace are supported. UNA, UNB/UNZ, release characters (`?`), embedded delimiters, control envelopes, multiple messages and unknown segments are rejected. Use the fixtures exactly for interoperable demo behavior.

| Source | Source field/segment | Canonical target | Required | Transformation | Validation |
|---|---|---|---|---|---|
| JSON | external_order_id | external_order_id | Yes | Direct | 1–80 alphanumeric/underscore/hyphen; customer-scoped unique claim |
| JSON | customer_id | customer_id | Yes | Direct | NORDIC-001 |
| JSON | order_date / requested_delivery_date | Same | Yes | ISO date parsing | Real dates; delivery on/after order |
| JSON | currency / ship_to / items | Same | Yes | Pydantic nested model | Same domain rules as EDI |
| EDI | UNH+reference+ORDERS:D:96A:UN | Envelope only | Yes | Validate message type | First segment, unique |
| EDI | BGM+220+number+9 | external_order_id | Yes | Extract number | Original purchase order; canonical ID rules |
| EDI | DTM+137:YYYYMMDD:102 | order_date | Yes | Date to ISO | Real calendar date |
| EDI | DTM+2:YYYYMMDD:102 | requested_delivery_date | Yes | Date to ISO | On/after order date |
| EDI | NAD+BY+customer | customer_id | Yes | Extract party ID | NORDIC-001 |
| EDI | NAD+DP+name+street+city+postal+country | ship_to | Yes | Named address fields | Required nonempty fields; two uppercase country letters |
| EDI | CUX+2:currency:9 | currency | Yes | Extract code | EUR, USD, GBP |
| EDI | LIN+line++sku:SA | items[].line_number, sku | Yes | New line; integer number | Positive unique line; ATLAS-100 or ATLAS-200 |
| EDI | IMD+F+description | items[].description | Yes | Direct text | 1–200 characters; no embedded delimiters |
| EDI | QTY+21:quantity:EA | items[].quantity, unit | Yes | Decimal and unit | >0, max 12 digits/3 decimals; EA |
| EDI | PRI+AAA:price | items[].unit_price | Yes | Decimal | >=0, max 12 digits/2 decimals |
| EDI | UNT+count+reference | Envelope only | Yes | Parse integer | Total including UNH and UNT; matching reference; last segment |

Header qualifiers may appear once. Every item group must start with LIN; IMD, QTY and PRI are each allowed once per line. One to 100 complete lines. Unknown JSON fields are rejected. Prices remain decimal strings when serialized; there is no floating-point amount calculation.

## Example and response

`examples/valid_order.edi` has exactly twelve segments and one line. The JSON fixture has two lines to demonstrate multi-line canonical orders. Both call the same `map_order` validation and downstream service.

`mapping.acknowledgement` produces a JSON confirmation for all messages. EDI confirmations additionally contain four segments: UNH (ORDRSP), BGM (231 response / 29 accepted), RFF (original order number), UNT (4 with matching reference). This is a simplified acceptance response, not a standards-compliant line-level ORDRSP, CONTRL or commercial promise of availability. Rejected inbound messages expose persisted API errors rather than EDI negative acknowledgements.
