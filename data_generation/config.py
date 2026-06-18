from __future__ import annotations

from datetime import date

import numpy as np
from faker import Faker

SEED = 42
HORIZON_START = date(2020, 1, 1)
HORIZON_END = date(2025, 12, 31)
AS_OF = date(2025, 12, 31)
LAST_12M_START = date(2025, 1, 1)
LAST_3M_START = date(2025, 10, 1)

ORDERS_PER_YEAR = 2700
# The Phase 03 reset deletes *all* operational orders (including the 1996-1998
# Northwind seed), so synthetic ids cannot be derived from a surviving base row.
# We start from a fixed base (just past the original max ~11077) to keep the run
# deterministic; 11078 + ORDER_COUNT stays well under the smallint ceiling (32767).
FIRST_SYNTHETIC_ORDER_ID = 11078
ORDER_COUNT = ORDERS_PER_YEAR * 6

TOKYO_TRADERS = 4
EXOTIC_LIQUIDS = 1
GRANDMA_KELLYS = 3
PAVLOVA = 7

TOKYO_PRODUCTS = (9, 10, 74)
EXOTIC_PRODUCTS = (2, 3)
GRANDMA_PRODUCTS = (6, 7, 8)
PAVLOVA_PRODUCTS = (16, 17, 18, 63, 70)

TOP_CUSTOMER_IDS = (
    "SAVEA",
    "QUICK",
    "ERNSH",
    "HUNGO",
    "RATTC",
    "HANAR",
    "KOENE",
    "QUEEN",
    "SUPRD",
    "BERGS",
)
# Scenario B is anchored to a small fixed set of *non-top* customers, so the
# Exotic Liquids delays land clearly outside the top-10 (tests the top-customer
# filter). SCENARIO_B_CUSTOMER_ID is kept as the primary anchor for readability.
SCENARIO_B_CUSTOMER_IDS = ("ALFKI", "DUMON", "FAMIA")
SCENARIO_B_CUSTOMER_ID = SCENARIO_B_CUSTOMER_IDS[0]


def make_rng(seed: int = SEED) -> tuple[np.random.Generator, Faker]:
    fake = Faker()
    Faker.seed(seed)
    return np.random.default_rng(seed), fake
