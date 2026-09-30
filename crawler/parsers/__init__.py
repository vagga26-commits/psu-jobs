from .table import parse_table
from .official import parse_official

PARSERS = {"table": parse_table, "official": parse_official}
