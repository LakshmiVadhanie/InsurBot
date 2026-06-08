"""
Synthetic seed data generator for InsurBot BigQuery tables.

Generates and uploads:
  - 10 coverage plans
  - 1000 policies
  - 3000 claims

Usage:
    python -m data.seed.seed_data \
        --project your-gcp-project \
        --dataset insurbot \
        --location US

Requirements: google-cloud-bigquery must be installed and GOOGLE_APPLICATION_CREDENTIALS set.
"""

import argparse
import datetime
import random
import uuid
from dataclasses import dataclass, field

from google.cloud import bigquery


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

PLAN_TYPES = ["HMO", "PPO", "EPO", "HDHP"]
TIERS = ["BRONZE", "SILVER", "GOLD", "PLATINUM"]
NETWORK_SIZES = ["NARROW", "BROAD", "NATIONAL"]
POLICY_STATUSES = ["ACTIVE", "LAPSED", "CANCELLED", "PENDING"]
CLAIM_TYPES = ["MEDICAL", "DENTAL", "VISION", "PHARMACY", "MENTAL_HEALTH"]
CLAIM_STATUSES = ["OPEN", "IN_REVIEW", "APPROVED", "DENIED", "CLOSED"]
DENIAL_REASONS = [
    "NOT_COVERED",
    "DEDUCTIBLE_NOT_MET",
    "OUT_OF_NETWORK",
    "MISSING_DOCUMENTATION",
    "DUPLICATE_CLAIM",
]
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "William", "Barbara", "David", "Elizabeth", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def _rand_date(start: datetime.date, end: datetime.date) -> datetime.date:
    delta = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, delta))


def generate_coverage_plans() -> list[dict]:
    plans = []
    tier_premium_base = {"BRONZE": 250, "SILVER": 380, "GOLD": 520, "PLATINUM": 700}
    tier_deductible = {"BRONZE": 6500, "SILVER": 4000, "GOLD": 2000, "PLATINUM": 500}

    for tier in TIERS:
        for plan_type in PLAN_TYPES[:2]:  # HMO + PPO per tier for variety
            plan_id = f"PLAN-{tier[:2]}-{plan_type[:2]}-{random.randint(100, 999)}"
            premium = tier_premium_base[tier] + random.randint(-30, 30)
            deductible = tier_deductible[tier] + random.randint(-200, 200)
            plans.append(
                {
                    "plan_id": plan_id,
                    "plan_name": f"{tier.title()} {plan_type} {datetime.date.today().year}",
                    "tier": tier,
                    "plan_type": plan_type,
                    "monthly_premium": round(premium, 2),
                    "deductible": round(deductible, 2),
                    "out_of_pocket_max": round(deductible * 1.5, 2),
                    "copay_primary": 20 if tier in ("GOLD", "PLATINUM") else 40,
                    "copay_specialist": 50 if tier in ("GOLD", "PLATINUM") else 80,
                    "covers_dental": tier in ("GOLD", "PLATINUM"),
                    "covers_vision": tier == "PLATINUM",
                    "covers_mental_health": tier in ("SILVER", "GOLD", "PLATINUM"),
                    "covers_pharmacy": True,
                    "network_size": random.choice(NETWORK_SIZES),
                    "effective_year": datetime.date.today().year,
                    "created_at": datetime.datetime.utcnow().isoformat(),
                }
            )
    return plans


def generate_policies(plans: list[dict], count: int = 1000) -> list[dict]:
    today = datetime.date.today()
    policies = []
    for _ in range(count):
        plan = random.choice(plans)
        effective = _rand_date(today - datetime.timedelta(days=1460), today)
        expiry = effective + datetime.timedelta(days=365)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        policies.append(
            {
                "policy_id": f"POL-{uuid.uuid4().hex[:10].upper()}",
                "holder_name": f"{first} {last}",
                "holder_email": f"{first.lower()}.{last.lower()}@example.com",
                "plan_id": plan["plan_id"],
                "plan_type": plan["plan_type"],
                "effective_date": effective.isoformat(),
                "expiry_date": expiry.isoformat(),
                "premium_amount": plan["monthly_premium"],
                "status": random.choices(
                    POLICY_STATUSES, weights=[70, 10, 10, 10], k=1
                )[0],
                "state": random.choice(US_STATES),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
        )
    return policies


def generate_claims(policies: list[dict], count: int = 3000) -> list[dict]:
    today = datetime.date.today()
    claims = []
    for _ in range(count):
        policy = random.choice(policies)
        effective = datetime.date.fromisoformat(policy["effective_date"])
        claim_date = _rand_date(effective, min(today, datetime.date.fromisoformat(policy["expiry_date"])))
        requested = round(random.uniform(50, 15000), 2)
        status = random.choices(
            CLAIM_STATUSES, weights=[15, 20, 40, 15, 10], k=1
        )[0]
        approved = round(requested * random.uniform(0.5, 1.0), 2) if status == "APPROVED" else None
        denial = random.choice(DENIAL_REASONS) if status == "DENIED" else None
        resolved = (
            (claim_date + datetime.timedelta(days=random.randint(5, 90))).isoformat()
            if status in ("APPROVED", "DENIED", "CLOSED")
            else None
        )
        claims.append(
            {
                "claim_id": f"CLM-{uuid.uuid4().hex[:10].upper()}",
                "policy_id": policy["policy_id"],
                "claim_date": claim_date.isoformat(),
                "claim_type": random.choice(CLAIM_TYPES),
                "status": status,
                "amount_requested": requested,
                "amount_approved": approved,
                "denial_reason": denial,
                "adjuster_id": f"ADJ-{random.randint(100, 999)}",
                "resolved_date": resolved,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
        )
    return claims


# ---------------------------------------------------------------------------
# BigQuery upload
# ---------------------------------------------------------------------------

@dataclass
class TableSpec:
    table_id: str
    rows: list[dict] = field(default_factory=list)


def _upload(
    client: bigquery.Client,
    project: str,
    dataset: str,
    spec: TableSpec,
) -> None:
    table_ref = f"{project}.{dataset}.{spec.table_id}"
    errors = client.insert_rows_json(table_ref, spec.rows)
    if errors:
        raise RuntimeError(f"BigQuery insert errors for {spec.table_id}: {errors}")
    print(f"Inserted {len(spec.rows)} rows into {table_ref}")


def seed(project: str, dataset: str, location: str) -> None:
    client = bigquery.Client(project=project)

    print("Generating coverage plans...")
    plans = generate_coverage_plans()

    print("Generating policies...")
    policies = generate_policies(plans, count=1000)

    print("Generating claims...")
    claims = generate_claims(policies, count=3000)

    for spec in [
        TableSpec("coverage_plans", plans),
        TableSpec("policies", policies),
        TableSpec("claims", claims),
    ]:
        _upload(client, project, dataset, spec)

    print("Seed complete.")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed InsurBot BigQuery tables with synthetic data")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--dataset", default="insurbot", help="BigQuery dataset name")
    parser.add_argument("--location", default="US", help="BigQuery location")
    args = parser.parse_args()

    seed(project=args.project, dataset=args.dataset, location=args.location)
