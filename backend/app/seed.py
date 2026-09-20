"""Seed script - loads the 3 customers, their bookings (verbatim from the
data pack), and the ASSUMED rebooking inventory, then creates the schema.

Run:  python -m app.seed        (from backend/)
"""
from .database import Base, SessionLocal, engine
from .models import Booking, Customer, RebookingInventory

# ==== GROUND TRUTH FROM THE DATA PACK (do not alter) =========================
CUSTOMERS = [
    {
        "name": "Priya Nair",
        "loyalty_tier": "Gold",
        "email": "priya.nair@example.com",
        "phone": "+91-98xxxxxxx1",
        "flights_last_12m": 6,
        "prior_complaints": "1 prior complaint (delayed baggage, resolved with voucher)",
    },
    {
        "name": "Arvind Kulkarni",
        "loyalty_tier": "Silver",
        "email": "arvind.kulkarni@example.com",
        "phone": "+91-98xxxxxxx2",
        "flights_last_12m": 3,
        "prior_complaints": "No prior complaints",
    },
    {
        "name": "Meher Kaur",
        "loyalty_tier": "Platinum",
        "email": "meher.kaur@example.com",
        "phone": "+91-98xxxxxxx3",
        "flights_last_12m": 10,
        "prior_complaints": "1 prior complaint (overbooking, resolved with tier-status upgrade)",
    },
]

# "as of Wednesday, 23 September 2026"
BOOKINGS = [
    {
        "pnr": "SK4821X",
        "customer_name": "Priya Nair",
        "flight_label": "SK-204",
        "flight_number": "SK-204",
        "route": "Delhi → Goa",
        "origin": "Delhi",
        "destination": "Goa",
        "scheduled_departure": "Wed 23 Sep 2026 18:40",
        "status": "Cancelled (operational reasons)",
        "delay_hours": None,
        "new_departure": None,
        "payment_method": "Credit Card ending 4412",  # ASSUMPTION: method not in data pack
        "is_disrupted_leg": True,
        "fare": 8200.0,  # ASSUMPTION: fares not in data pack
    },
    {
        "pnr": "SK4821X",
        "customer_name": "Priya Nair",
        "flight_label": "Return",
        "flight_number": "SK-209",
        "route": "Goa → Delhi",
        "origin": "Goa",
        "destination": "Delhi",
        "scheduled_departure": "Fri 25 Sep 2026 16:20",
        "status": "Unaffected",
        "delay_hours": None,
        "new_departure": None,
        "payment_method": "Credit Card ending 4412",
        "is_disrupted_leg": False,
        "fare": 7900.0,
    },
    {
        "pnr": "TR1190B",
        "customer_name": "Arvind Kulkarni",
        "flight_label": "SK-118",
        "flight_number": "SK-118",
        "route": "Mumbai → Bengaluru",
        "origin": "Mumbai",
        "destination": "Bengaluru",
        "scheduled_departure": "Wed 23 Sep 2026 07:10",
        "status": "Delayed 4h (new departure 11:10)",
        "delay_hours": 4.0,
        "new_departure": "Wed 23 Sep 2026 11:10",
        "payment_method": "UPI",
        "is_disrupted_leg": True,
        "fare": 4300.0,
    },
    {
        "pnr": "WL7742",
        "customer_name": "Meher Kaur",
        "flight_label": "SK-305",
        "flight_number": "SK-305",
        "route": "Delhi → Hyderabad",
        "origin": "Delhi",
        "destination": "Hyderabad",
        "scheduled_departure": "Wed 23 Sep 2026 14:00",
        "status": "Delayed 6h (new departure 20:00)",
        "delay_hours": 6.0,
        "new_departure": "Wed 23 Sep 2026 20:00",
        "payment_method": "Credit Card ending 7723",  # ASSUMPTION: method not in data pack
        "is_disrupted_leg": True,
        "fare": 6800.0,
    },
]

# ==== ASSUMED INVENTORY (NOT in the data pack - flagged in README) ===========
# Needed so execute_rebooking is demoable. Plausible next-available flights.
REBOOKING_INVENTORY = [
    # Priya: Delhi -> Goa alternatives after cancelled 18:40 Wed departure
    {"flight_number": "SK-206", "origin": "Delhi", "destination": "Goa",
     "departure": "Wed 23 Sep 2026 21:15", "arrival": "Thu 24 Sep 2026 23:55",
     "fare": 8200.0, "is_higher_fare": False,
     "note": "Same evening; limited seats - Gold/Platinum priority (R5)"},
    {"flight_number": "SK-210", "origin": "Delhi", "destination": "Goa",
     "departure": "Thu 24 Sep 2026 07:30", "arrival": "Thu 24 Sep 2026 10:10",
     "fare": 8200.0, "is_higher_fare": False, "note": "Next morning"},
    {"flight_number": "SK-214", "origin": "Delhi", "destination": "Goa",
     "departure": "Thu 24 Sep 2026 18:40", "arrival": "Thu 24 Sep 2026 21:20",
     "fare": 8200.0, "is_higher_fare": False, "note": "Exactly 24h after original"},
    # Meher: the "different, higher-fare flight" she asks to be moved to
    {"flight_number": "SK-311", "origin": "Delhi", "destination": "Hyderabad",
     "departure": "Wed 23 Sep 2026 15:30", "arrival": "Wed 23 Sep 2026 18:00",
     "fare": 8800.0, "is_higher_fare": True,
     "note": "Higher-fare option; voluntary change -> R4 fare difference Rs.2,000"},
]

# Seeded opening message per scenario (what the customer says when the chat starts)
SCENARIO_OPENERS = {
    "SK4821X": "My flight got cancelled and no one told me anything!",
    "TR1190B": "My flight SK-118 is delayed 4 hours and I've been stuck at the airport all morning.",
    "WL7742": "My flight SK-305 is delayed 6 hours. This is unacceptable.",
}


def run_seed(verbose: bool = True) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Customer).count() > 0:
            if verbose:
                print("Seed: data already present - skipping (delete airline_agent.db to re-seed).")
            return

        name_to_id = {}
        for c in CUSTOMERS:
            cust = Customer(**c)
            db.add(cust)
            db.flush()
            name_to_id[c["name"]] = cust.id

        for b in BOOKINGS:
            b = dict(b)
            customer_name = b.pop("customer_name")
            b["customer_id"] = name_to_id[customer_name]
            db.add(Booking(**b))

        for inv in REBOOKING_INVENTORY:
            db.add(RebookingInventory(**inv))

        db.commit()
        if verbose:
            print("Seed complete: 3 customers, 4 bookings, rebooking inventory loaded.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
