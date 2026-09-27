"""Generate the sample datasets and their planted-insight manifests.

Each dataset is synthetic but realistic (IDs, dates, missing values, noise
columns) and contains a few deliberately planted relationships. The manifest
next to each CSV lists them, and the findings-engine eval checks that the
analysis recovers every one and does not flag the noise columns.

Deterministic: re-running produces byte-identical files.
From apps/api:  .venv/bin/python scripts/generate_datasets.py
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "app" / "sample_data"
Manifest = dict[str, Any]


def _logistic(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def _dates(
    rng: np.random.Generator, n: int, start: str, end: str, month_weights: list[float]
) -> pd.Series:
    days = pd.date_range(start, end, freq="D")
    weights = np.array([month_weights[d.month - 1] for d in days], dtype=float)
    picked = rng.choice(days, size=n, p=weights / weights.sum())
    return pd.Series(np.sort(picked))


# ---------------------------------------------------------------- e-commerce


def ecommerce(rng: np.random.Generator) -> tuple[pd.DataFrame, Manifest]:
    n = 5000
    # Q4 seasonality: November and December carry roughly twice the order volume.
    month_w = [0.8, 0.75, 0.85, 0.9, 0.95, 0.9, 0.9, 0.95, 1.0, 1.1, 1.8, 2.1]
    order_date = _dates(rng, n, "2024-01-01", "2025-12-31", month_w)

    # A few heavy customers: order frequency follows a Pareto-like weight.
    n_customers = 1200
    cust_w = rng.pareto(1.3, n_customers) + 0.05
    customer_idx = rng.choice(n_customers, size=n, p=cust_w / cust_w.sum())
    segment_of = rng.choice(
        ["Consumer", "Small Business", "Enterprise"], n_customers, p=[0.7, 0.22, 0.08]
    )
    age_of = rng.integers(18, 75, n_customers)
    segment = segment_of[customer_idx]

    channels = ["Organic Search", "Paid Search", "Email", "Social", "Direct", "Affiliate"]
    channel = rng.choice(channels, n, p=[0.24, 0.2, 0.14, 0.16, 0.18, 0.08])
    region = rng.choice(["North", "South", "East", "West"], n, p=[0.26, 0.24, 0.27, 0.23])
    categories = {
        "Electronics": (220, 0.68),
        "Home": (85, 0.58),
        "Apparel": (48, 0.52),
        "Beauty": (32, 0.45),
        "Sports": (70, 0.6),
        "Toys": (38, 0.55),
    }
    category = rng.choice(list(categories), n, p=[0.18, 0.2, 0.22, 0.14, 0.14, 0.12])
    base_price = np.array([categories[c][0] for c in category])
    cost_ratio = np.array([categories[c][1] for c in category])
    unit_price = np.round(base_price * rng.lognormal(0, 0.25, n), 2)

    # Enterprise buys bigger baskets; discount has NO effect on units (planted null).
    units = 1 + rng.poisson(
        np.where(segment == "Enterprise", 4.0, np.where(segment == "Small Business", 1.8, 0.8))
    )
    discount_pct = rng.choice(
        [0, 5, 10, 15, 20, 25, 30], n, p=[0.32, 0.14, 0.16, 0.12, 0.1, 0.09, 0.07]
    )
    gross = units * unit_price
    revenue = np.round(gross * (1 - discount_pct / 100), 2)
    cost = np.round(gross * cost_ratio * rng.normal(1, 0.03, n), 2)
    margin = np.round(revenue - cost, 2)  # deep discounts push margin toward zero or below

    shipping_method = rng.choice(["Standard", "Express", "Economy"], n, p=[0.6, 0.2, 0.2])
    base_days = np.select([shipping_method == "Express", shipping_method == "Economy"], [2, 6], 4)
    shipping_days = np.clip(
        base_days + np.where(region == "West", 3, 0) + rng.poisson(1, n) - 1, 1, None
    )

    # Returns: Social-channel orders are returned ~2.4x as often; Apparel a bit more.
    p_return = (
        0.07 * np.where(channel == "Social", 2.6, 1.0) * np.where(category == "Apparel", 1.4, 1.0)
    )
    returned = rng.random(n) < p_return

    # Ratings fall with slow shipping (so the West rates lower); ~35% of orders aren't rated.
    rating_raw = 4.6 - 0.28 * (shipping_days - 3) - 0.8 * returned + rng.normal(0, 0.6, n)
    rating = np.clip(np.round(rating_raw), 1, 5).astype(float)
    rating[rng.random(n) < 0.35] = np.nan

    first_seen: dict[int, int] = {}
    is_first = []
    for i, c in enumerate(customer_idx):
        is_first.append(c not in first_seen)
        first_seen.setdefault(int(c), i)

    df = pd.DataFrame(
        {
            "order_id": [f"ORD-{i + 1:05d}" for i in range(n)],
            "order_date": order_date.dt.strftime("%Y-%m-%d"),
            "customer_id": [f"C{c + 1:04d}" for c in customer_idx],
            "customer_segment": segment,
            "customer_age": age_of[customer_idx],
            "is_first_order": is_first,
            "channel": channel,
            "device": rng.choice(["Mobile", "Desktop", "Tablet"], n, p=[0.55, 0.38, 0.07]),
            "region": region,
            "product_category": category,
            "unit_price": unit_price,
            "units": units,
            "discount_pct": discount_pct,
            "revenue": revenue,
            "cost": cost,
            "margin": margin,
            "shipping_method": shipping_method,
            "shipping_days": shipping_days,
            "returned": returned,
            "rating": rating,
            "payment_method": rng.choice(
                ["Card", "PayPal", "Apple Pay", "Bank Transfer"], n, p=[0.55, 0.22, 0.15, 0.08]
            ),
            "gift_wrap": rng.random(n) < 0.12,
        }
    )
    manifest = {
        "title": "E-commerce orders",
        "description": (
            "Two years of online orders: channels, regions, products, "
            "discounts, shipping, returns and ratings."
        ),
        "suggested_question": "What is hurting our margin, and where are returns coming from?",
        "suggested_target": "margin",
        "planted": [
            {
                "id": "social_returns",
                "kind": "segment",
                "target": "returned",
                "dimension": "channel",
                "top": "Social",
            },
            {
                "id": "discount_margin",
                "kind": "bins",
                "target": "margin",
                "driver": "discount_pct",
                "direction": "decreasing",
            },
            {
                "id": "west_ratings",
                "kind": "segment",
                "target": "rating",
                "dimension": "region",
                "bottom": "West",
            },
            {
                "id": "west_shipping",
                "kind": "segment",
                "target": "shipping_days",
                "dimension": "region",
                "top": "West",
                "tier": "secondary",  # one step removed from the outcome; checked directly
            },
            {
                "id": "q4_revenue",
                "kind": "seasonality",
                "target": "revenue",
                "peak_months": [11, 12],
            },
            {
                "id": "customer_concentration",
                "kind": "concentration",
                "target": "revenue",
                "entity": "customer_id",
                "top10_share_min": 0.35,
            },
            {
                "id": "discount_units_null",
                "kind": "null",
                "target": "units",
                "driver": "discount_pct",
            },
        ],
        "noise_columns": ["device", "payment_method", "gift_wrap"],
    }
    return df, manifest


# ---------------------------------------------------------------- SaaS churn


def saas_churn(rng: np.random.Generator) -> tuple[pd.DataFrame, Manifest]:
    n = 3000
    signup_date = _dates(rng, n, "2023-01-01", "2025-06-30", [1] * 12)
    plan = rng.choice(["Basic", "Pro", "Business", "Enterprise"], n, p=[0.4, 0.32, 0.18, 0.1])
    billing = rng.choice(["Monthly", "Annual"], n, p=[0.58, 0.42])
    seats = np.maximum(
        1,
        np.round(
            rng.lognormal(
                np.select(
                    [plan == "Basic", plan == "Pro", plan == "Business"], [0.7, 1.6, 2.6], 3.6
                ),
                0.5,
                n,
            )
        ),
    ).astype(int)
    price = np.select([plan == "Basic", plan == "Pro", plan == "Business"], [12, 29, 49], 89)
    monthly_revenue = np.round(seats * price * np.where(billing == "Annual", 0.83, 1.0), 2)
    tenure = np.clip(np.round(rng.gamma(2.2, 7.5, n)), 1, 48).astype(int)
    logins = np.round(np.clip(rng.gamma(2.0, 2.4, n), 0, 30), 1)
    tickets = rng.negative_binomial(2, np.where(plan == "Basic", 0.42, 0.38), n)  # long tail
    nps = np.clip(np.round(rng.normal(7.2, 2.2, n)), 0, 10)
    onboarding = rng.random(n) < 0.72

    logit = (
        -2.6
        + 1.4 * (logins < 2)
        + 1.0 * (tickets > 5)
        + 0.9 * (billing == "Monthly")
        + 0.6 * (plan == "Basic")
        + 1.0 * (tenure < 6)
        + 0.7 * (nps <= 6)
        - 0.7 * onboarding
    )
    churned = rng.random(n) < _logistic(logit)
    nps_obs = nps.astype(float)
    nps_obs[rng.random(n) < 0.35] = np.nan  # many customers never answer the survey

    df = pd.DataFrame(
        {
            "customer_id": [f"ACC-{i + 1:05d}" for i in range(n)],
            "signup_date": signup_date.dt.strftime("%Y-%m-%d"),
            "plan": plan,
            "billing_cycle": billing,
            "seats": seats,
            "monthly_revenue": monthly_revenue,
            "industry": rng.choice(
                ["Software", "Retail", "Healthcare", "Finance", "Education", "Manufacturing"], n
            ),
            "company_size": np.select(
                [seats < 5, seats < 25, seats < 100], ["1-4", "5-24", "25-99"], "100+"
            ),
            "region": rng.choice(["NA", "EMEA", "APAC", "LATAM"], n, p=[0.45, 0.3, 0.17, 0.08]),
            "tenure_months": tenure,
            "avg_weekly_logins": logins,
            "feature_adoption_pct": np.round(
                np.clip(rng.normal(45, 18, n) + 2 * logins, 0, 100), 1
            ),
            "support_tickets_90d": tickets,
            "avg_resolution_hours": np.round(rng.gamma(2, 9, n), 1),
            "nps_score": nps_obs,
            "last_login_days_ago": np.clip(
                np.round(rng.exponential(6, n) + 12 * (logins < 2)), 0, 120
            ).astype(int),
            "onboarding_completed": onboarding,
            "discount_applied": rng.random(n) < 0.2,
            "has_account_manager": (plan == "Enterprise") & (rng.random(n) < 0.8),
            "churned": churned,
        }
    )
    manifest = {
        "title": "SaaS subscriptions",
        "description": (
            "B2B SaaS accounts: plan, billing, usage, support load, NPS and whether they churned."
        ),
        "suggested_question": "Which customers churn, and what warning signs show up first?",
        "suggested_target": "churned",
        "planted": [
            {
                "id": "monthly_billing",
                "kind": "segment",
                "target": "churned",
                "dimension": "billing_cycle",
                "top": "Monthly",
            },
            {
                "id": "basic_plan",
                "kind": "segment",
                "target": "churned",
                "dimension": "plan",
                "top": "Basic",
            },
            {
                "id": "low_logins",
                "kind": "bins",
                "target": "churned",
                "driver": "avg_weekly_logins",
                "direction": "decreasing",
            },
            {
                "id": "support_tickets",
                "kind": "bins",
                "target": "churned",
                "driver": "support_tickets_90d",
                "direction": "increasing",
            },
            {
                "id": "early_tenure",
                "kind": "bins",
                "target": "churned",
                "driver": "tenure_months",
                "direction": "decreasing",
            },
        ],
        "noise_columns": ["industry", "region", "discount_applied", "avg_resolution_hours"],
    }
    return df, manifest


# ---------------------------------------------------------------- HR attrition


def hr_attrition(rng: np.random.Generator) -> tuple[pd.DataFrame, Manifest]:
    n = 2000
    dept = rng.choice(
        ["Sales", "Engineering", "Operations", "Support", "Finance", "HR", "Marketing"],
        n,
        p=[0.22, 0.26, 0.16, 0.14, 0.08, 0.05, 0.09],
    )
    level = rng.choice([1, 2, 3, 4, 5], n, p=[0.3, 0.3, 0.22, 0.12, 0.06])
    tenure = np.round(np.clip(rng.gamma(2, 2.2, n), 0.2, 30), 1)
    since_promo = np.round(np.minimum(tenure, rng.gamma(1.6, 1.4, n)), 1)
    salary_vs_band = np.round(rng.normal(0, 11, n), 1)
    base_salary = np.array([3800, 5200, 7000, 9500, 13000])[level - 1]
    overtime = rng.random(n) < np.where(dept == "Sales", 0.4, 0.25)
    satisfaction = rng.choice([1, 2, 3, 4, 5], n, p=[0.08, 0.14, 0.3, 0.32, 0.16])
    commute = np.round(np.clip(rng.gamma(2, 9, n), 1, 90), 1)
    remote_days = rng.choice([0, 1, 2, 3, 4, 5], n, p=[0.3, 0.15, 0.2, 0.2, 0.1, 0.05])

    logit = (
        -2.7
        + 1.1 * overtime
        + 1.2 * (satisfaction <= 2)
        + 0.8 * (salary_vs_band < -10)
        + 0.7 * (since_promo >= 3)
        + 0.6 * (dept == "Sales")
        + 0.6 * (commute > 30)
        - 0.4 * (remote_days >= 2)
    )
    left = rng.random(n) < _logistic(logit)

    df = pd.DataFrame(
        {
            "employee_id": [f"E{i + 1:05d}" for i in range(n)],
            "department": dept,
            "job_level": level,
            "age": np.clip(np.round(22 + tenure + rng.normal(8, 6, n)), 20, 65).astype(int),
            "gender": rng.choice(["Female", "Male", "Non-binary"], n, p=[0.47, 0.5, 0.03]),
            "education": rng.choice(
                ["High school", "Bachelor", "Master", "PhD"], n, p=[0.15, 0.55, 0.26, 0.04]
            ),
            "tenure_years": tenure,
            "years_since_promotion": since_promo,
            "monthly_salary": np.round(
                base_salary * (1 + salary_vs_band / 100) * rng.normal(1, 0.03, n), 0
            ),
            "salary_vs_band_pct": salary_vs_band,
            "overtime": overtime,
            "satisfaction_score": satisfaction,
            "work_life_balance": np.clip(5 - overtime * 1 - rng.integers(1, 3, n), 1, 4),
            "performance_rating": rng.choice([2, 3, 4, 5], n, p=[0.08, 0.5, 0.32, 0.1]),
            "commute_km": commute,
            "remote_days_per_week": remote_days,
            "training_hours_last_year": rng.integers(0, 60, n),
            "left_company": left,
        }
    )
    manifest = {
        "title": "Employee attrition",
        "description": (
            "One snapshot of 2,000 employees: department, pay versus "
            "band, overtime, satisfaction, commute and who left."
        ),
        "suggested_question": "Why are people leaving, and which teams are most at risk?",
        "suggested_target": "left_company",
        "planted": [
            {
                "id": "overtime",
                "kind": "segment",
                "target": "left_company",
                "dimension": "overtime",
                "top": "True",
            },
            {
                "id": "sales_dept",
                "kind": "segment",
                "target": "left_company",
                "dimension": "department",
                "top": "Sales",
            },
            {
                "id": "satisfaction",
                "kind": "bins",
                "target": "left_company",
                "driver": "satisfaction_score",
                "direction": "decreasing",
            },
            {
                "id": "commute",
                "kind": "bins",
                "target": "left_company",
                "driver": "commute_km",
                "direction": "increasing",
            },
            {
                "id": "underpaid",
                "kind": "bins",
                "target": "left_company",
                "driver": "salary_vs_band_pct",
                "direction": "decreasing",
            },
        ],
        "noise_columns": ["gender", "education", "training_hours_last_year", "performance_rating"],
    }
    return df, manifest


# ---------------------------------------------------------------- hospital readmissions


def hospital_readmissions(rng: np.random.Generator) -> tuple[pd.DataFrame, Manifest]:
    n = 4000
    admit_date = _dates(
        rng,
        n,
        "2024-01-01",
        "2025-12-31",
        [1.2, 1.15, 1.05, 0.95, 0.9, 0.85, 0.85, 0.85, 0.9, 1.0, 1.05, 1.2],
    )
    diagnoses = {
        "Heart failure": "Cardiology",
        "COPD": "Pulmonology",
        "Pneumonia": "Pulmonology",
        "Diabetes complication": "General Medicine",
        "Hip fracture": "Orthopedics",
        "Sepsis": "General Medicine",
        "Chemotherapy complication": "Oncology",
        "Kidney disease": "Nephrology",
    }
    diagnosis = rng.choice(list(diagnoses), n, p=[0.18, 0.13, 0.15, 0.1, 0.1, 0.12, 0.1, 0.12])
    department = np.array([diagnoses[d] for d in diagnosis])
    age = np.clip(np.round(rng.normal(68, 13, n)), 18, 99).astype(int)
    prior = rng.poisson(0.9, n)
    los = np.clip(np.round(rng.gamma(2.2, 2.3, n)), 1, 30).astype(int)
    diabetes = (diagnosis == "Diabetes complication") | (rng.random(n) < 0.22)
    hba1c = np.where(
        diabetes, np.round(rng.normal(7.8, 1.4, n), 1), np.round(rng.normal(5.5, 0.4, n), 1)
    ).astype(float)
    # Lab values are mostly measured for diabetic patients; missing for most others.
    hba1c[(~diabetes & (rng.random(n) < 0.85)) | (diabetes & (rng.random(n) < 0.15))] = np.nan
    follow_up = rng.random(n) < 0.62
    disposition = rng.choice(
        ["Home", "Home with services", "Skilled nursing facility", "Rehab"],
        n,
        p=[0.55, 0.2, 0.17, 0.08],
    )
    emergency = rng.random(n) < 0.64

    logit = (
        -2.4
        + 0.4 * np.minimum(prior, 5)
        - 1.0 * follow_up
        + 0.6 * (los <= 1)
        + 0.8 * (los >= 10)
        + 0.9 * (diabetes & (np.nan_to_num(hba1c, nan=0) > 8))
        + 0.9 * (diagnosis == "Heart failure")
        + 0.3 * (disposition == "Skilled nursing facility")
    )
    readmitted = rng.random(n) < _logistic(logit)

    df = pd.DataFrame(
        {
            "admission_id": [f"ADM-{i + 1:05d}" for i in range(n)],
            "patient_id": [f"P{p:05d}" for p in rng.integers(1, 3200, n)],
            "admission_date": admit_date.dt.strftime("%Y-%m-%d"),
            "age": age,
            "sex": rng.choice(["F", "M"], n),
            "department": department,
            "primary_diagnosis": diagnosis,
            "emergency_admission": emergency,
            "prior_admissions_12m": prior,
            "length_of_stay_days": los,
            "num_medications": np.clip(rng.poisson(9 + 2 * diabetes, n), 0, None),
            "num_procedures": rng.poisson(1.4, n),
            "diabetes": diabetes,
            "hba1c": hba1c,
            "insurance_type": rng.choice(
                ["Medicare", "Medicaid", "Private", "Uninsured"], n, p=[0.52, 0.18, 0.25, 0.05]
            ),
            "discharge_disposition": disposition,
            "follow_up_scheduled": follow_up,
            "total_charges": np.round(
                los * rng.normal(3100, 600, n) + rng.normal(4000, 1500, n), 2
            ),
            "readmitted_30d": readmitted,
        }
    )
    manifest = {
        "title": "Hospital readmissions",
        "description": (
            "Two years of inpatient admissions: diagnosis, history, "
            "length of stay, labs, discharge plan and 30-day readmission."
        ),
        "suggested_question": (
            "Which patients are readmitted within 30 days, and what could prevent it?"
        ),
        "suggested_target": "readmitted_30d",
        "planted": [
            {
                "id": "no_follow_up",
                "kind": "segment",
                "target": "readmitted_30d",
                "dimension": "follow_up_scheduled",
                "top": "False",
            },
            {
                "id": "prior_admissions",
                "kind": "bins",
                "target": "readmitted_30d",
                "driver": "prior_admissions_12m",
                "direction": "increasing",
            },
            {
                "id": "heart_failure",
                "kind": "segment",
                "target": "readmitted_30d",
                "dimension": "primary_diagnosis",
                "top": "Heart failure",
            },
            {
                "id": "high_hba1c",
                "kind": "bins",
                "target": "readmitted_30d",
                "driver": "hba1c",
                "direction": "increasing",
            },
        ],
        "noise_columns": ["sex", "num_procedures"],
    }
    return df, manifest


DATASETS: dict[str, Callable[[np.random.Generator], tuple[pd.DataFrame, Manifest]]] = {
    "ecommerce_orders": ecommerce,
    "saas_churn": saas_churn,
    "hr_attrition": hr_attrition,
    "hospital_readmissions": hospital_readmissions,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, build) in enumerate(DATASETS.items()):
        df, manifest = build(np.random.default_rng(20260926 + i))
        df.to_csv(OUT / f"{name}.csv", index=False)
        manifest = {"name": name, "rows": len(df), "columns": len(df.columns), **manifest}
        (OUT / f"{name}.expected.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{name}: {len(df)} rows × {len(df.columns)} columns")


if __name__ == "__main__":
    main()
