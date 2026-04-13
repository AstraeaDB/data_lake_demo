#!/usr/bin/env python3
"""Generate all data lake files for the demo.

Creates 8 data sources across 4 domains:
  Security:       logon_events.csv, http_access.jsonl, email_activity.parquet
  Communications: teams_calls_2018_2021.csv, zoom_meetings_2020_2024.json
  HR:             legacy_hris_2017_2021.csv, modern_hcm_2021_2024.json
  Projects:       project_tickets.parquet

Uses the CERT Insider Threat dataset schema for security sources if available,
otherwise generates synthetic data following the same schema.
"""

import csv
import json
import math
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from faker import Faker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

fake = Faker()
Faker.seed(config.SEED)
random.seed(config.SEED)


# ---------------------------------------------------------------------------
# User Universe
# ---------------------------------------------------------------------------

SKILLS_POOL = [
    "Python", "Java", "Go", "Rust", "JavaScript", "TypeScript", "SQL",
    "Kubernetes", "Docker", "AWS", "Azure", "GCP", "Terraform",
    "React", "Angular", "Node.js", "PostgreSQL", "MongoDB", "Redis",
    "Machine Learning", "Data Analysis", "Project Management",
    "Technical Writing", "Agile", "Scrum", "CI/CD", "Linux",
    "Networking", "Security", "Compliance", "Financial Modeling",
    "Salesforce", "HubSpot", "Tableau", "Power BI", "Excel",
]

JOB_TITLES = {
    "Engineering": [
        "Software Engineer", "Senior Software Engineer", "Staff Engineer",
        "Engineering Manager", "Principal Engineer", "DevOps Engineer",
        "QA Engineer", "Site Reliability Engineer",
    ],
    "Sales": [
        "Account Executive", "Sales Representative", "Sales Manager",
        "Business Development Rep", "Sales Engineer", "VP Sales",
    ],
    "Marketing": [
        "Marketing Analyst", "Content Strategist", "Marketing Manager",
        "Growth Engineer", "Brand Manager", "Digital Marketing Specialist",
    ],
    "Finance": [
        "Financial Analyst", "Controller", "Accountant",
        "Finance Manager", "Accounts Payable Specialist",
    ],
    "Human Resources": [
        "HR Generalist", "Recruiter", "HR Manager",
        "Compensation Analyst", "HR Business Partner",
    ],
    "IT": [
        "Systems Administrator", "Help Desk Analyst", "Network Engineer",
        "IT Manager", "Database Administrator", "Security Analyst",
    ],
    "Operations": [
        "Operations Analyst", "Supply Chain Manager", "Logistics Coordinator",
        "Operations Manager", "Process Improvement Specialist",
        "Facilities Manager",
    ],
    "Legal": [
        "Corporate Counsel", "Paralegal", "Compliance Officer",
        "Legal Analyst", "Contract Manager",
    ],
}

COMPUTERS = [f"PC-{i:04d}" for i in range(1, 301)]


def generate_user_universe():
    """Create the master user registry with consistent IDs across all systems."""
    users = []
    user_num = 1

    # Assign users to departments proportionally
    dept_assignments = []
    for dept, count in config.DEPARTMENTS.items():
        dept_assignments.extend([dept] * count)
    random.shuffle(dept_assignments)

    for i in range(config.USER_COUNT):
        dept = dept_assignments[i] if i < len(dept_assignments) else random.choice(
            list(config.DEPARTMENTS.keys())
        )
        hire_year = random.randint(2015, 2023)
        hire_month = random.randint(1, 12)
        hire_day = random.randint(1, 28)
        hire_date = date(hire_year, hire_month, hire_day)

        # ~15% of employees have left
        terminated = random.random() < 0.15
        term_date = None
        if terminated:
            months_after = random.randint(6, 48)
            term_date = hire_date + timedelta(days=months_after * 30)
            if term_date > date(2024, 12, 31):
                term_date = None
                terminated = False

        title = random.choice(JOB_TITLES.get(dept, ["Associate"]))
        base_salary = _salary_for_title(title)

        # ~5% are "interesting" users (insider threat candidates)
        is_interesting = i < 10

        users.append({
            "cert_id": f"U{user_num:04d}",
            "email": f"U{user_num:04d}@acmecorp.com",
            "legacy_emp_id": f"EMP-{user_num:04d}",
            "modern_worker_id": f"WKR-{user_num:04d}",
            "name": fake.name(),
            "department": dept,
            "job_title": title,
            "hire_date": hire_date.isoformat(),
            "termination_date": term_date.isoformat() if term_date else None,
            "base_salary": base_salary,
            "primary_pc": random.choice(COMPUTERS),
            "manager_num": max(1, user_num - random.randint(1, 20)),
            "skills": random.sample(SKILLS_POOL, k=random.randint(3, 8)),
            "is_interesting": is_interesting,
        })
        user_num += 1

    return users


def _salary_for_title(title):
    """Generate a realistic salary based on title seniority."""
    if any(w in title.lower() for w in ["vp", "director", "principal", "staff"]):
        return random.randint(150000, 250000)
    if any(w in title.lower() for w in ["senior", "manager", "lead"]):
        return random.randint(110000, 180000)
    return random.randint(65000, 130000)


def _active_at(user, dt):
    """Check if a user was active (employed) at a given date."""
    hire = date.fromisoformat(user["hire_date"])
    if dt < hire:
        return False
    if user["termination_date"]:
        term = date.fromisoformat(user["termination_date"])
        if dt > term:
            return False
    return True


def _workdays_in_range(start, end):
    """Generate workday dates in the given range."""
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            yield current
        current += timedelta(days=1)


# ---------------------------------------------------------------------------
# Security Domain (CERT-schema)
# ---------------------------------------------------------------------------

def _load_or_skip_cert(filename):
    """Try to load a CERT raw file. Returns None if unavailable."""
    path = config.CERT_RAW_DIR / filename
    if path.exists():
        try:
            df = pd.read_csv(path)
            print(f"  Loaded CERT {filename}: {len(df)} rows")
            return df
        except Exception as e:
            print(f"  Failed to parse CERT {filename}: {e}")
    return None


def generate_logon_events(users):
    """Generate logon/logoff events → CSV (CERT schema).

    Columns: id, date, user, pc, activity
    """
    print("Generating logon_events.csv...")

    cert_df = _load_or_skip_cert("logon.csv")
    if cert_df is not None:
        return _subset_cert_logon(cert_df, users)

    output_path = config.SECURITY_DIR / "logon_events.csv"
    start = date.fromisoformat(config.SECURITY_START)
    end = date.fromisoformat(config.SECURITY_END)

    rows = []
    event_id = 1

    for day in _workdays_in_range(start, end):
        active_users = [u for u in users if _active_at(u, day)]

        for user in active_users:
            # Normal users: 1-2 logon/logoff pairs per day
            # Interesting users: occasional extra sessions (after-hours)
            n_sessions = random.randint(1, 2)
            if user["is_interesting"] and random.random() < 0.3:
                n_sessions += random.randint(1, 3)

            for _ in range(n_sessions):
                login_hour = random.gauss(8.5, 1.5)
                login_hour = max(6, min(22, login_hour))
                login_min = random.randint(0, 59)
                login_time = datetime(
                    day.year, day.month, day.day,
                    int(login_hour), login_min, random.randint(0, 59),
                )
                duration_hours = random.gauss(4, 2)
                duration_hours = max(0.5, min(12, duration_hours))
                logoff_time = login_time + timedelta(hours=duration_hours)

                pc = user["primary_pc"]
                if random.random() < 0.1:
                    pc = random.choice(COMPUTERS)

                rows.append({
                    "id": f"EVT-{event_id:07d}",
                    "date": login_time.strftime("%m/%d/%Y %H:%M:%S"),
                    "user": user["cert_id"],
                    "pc": pc,
                    "activity": "Logon",
                })
                event_id += 1
                rows.append({
                    "id": f"EVT-{event_id:07d}",
                    "date": logoff_time.strftime("%m/%d/%Y %H:%M:%S"),
                    "user": user["cert_id"],
                    "pc": pc,
                    "activity": "Logoff",
                })
                event_id += 1

            if len(rows) >= config.SECURITY_LOGON_TARGET:
                break
        if len(rows) >= config.SECURITY_LOGON_TARGET:
            break

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"  Written {len(df)} rows to {output_path}")
    return df


def _subset_cert_logon(cert_df, users):
    """Subset real CERT logon data to our user set."""
    output_path = config.SECURITY_DIR / "logon_events.csv"
    cert_users = cert_df["user"].unique()
    our_cert_ids = {u["cert_id"] for u in users}

    # Map CERT user IDs to our user IDs
    mapping = {}
    for i, cert_user in enumerate(cert_users[:config.USER_COUNT]):
        if i < len(users):
            mapping[cert_user] = users[i]["cert_id"]

    subset = cert_df[cert_df["user"].isin(mapping.keys())].copy()
    subset["user"] = subset["user"].map(mapping)
    subset = subset.head(config.SECURITY_LOGON_TARGET)
    subset.to_csv(output_path, index=False)
    print(f"  Written {len(subset)} rows to {output_path}")
    return subset


def generate_http_access(users):
    """Generate HTTP browsing activity → JSONL (CERT schema).

    Fields: id, date, user, pc, url, content_type, bytes_transferred
    """
    print("Generating http_access.jsonl...")

    output_path = config.SECURITY_DIR / "http_access.jsonl"
    start = date.fromisoformat(config.SECURITY_START)
    end = date.fromisoformat(config.SECURITY_END)

    domains_normal = [
        "docs.google.com", "github.com", "stackoverflow.com", "slack.com",
        "confluence.acmecorp.com", "jira.acmecorp.com", "outlook.office.com",
        "drive.google.com", "zoom.us", "teams.microsoft.com",
        "linkedin.com", "medium.com", "dev.to", "aws.amazon.com",
        "console.cloud.google.com", "portal.azure.com",
    ]
    domains_suspicious = [
        "dropbox.com", "mega.nz", "pastebin.com", "indeed.com",
        "glassdoor.com", "linkedin.com/jobs", "monster.com",
        "wetransfer.com", "onedrive.live.com",
    ]
    content_types = [
        "text/html", "application/json", "text/plain",
        "application/pdf", "image/png", "application/javascript",
    ]

    event_id = 1
    row_count = 0

    with open(output_path, "w") as f:
        for day in _workdays_in_range(start, end):
            active_users = [u for u in users if _active_at(u, day)]

            for user in active_users:
                n_requests = random.randint(5, 25)
                if user["is_interesting"] and random.random() < 0.4:
                    n_requests += random.randint(10, 40)

                for _ in range(n_requests):
                    hour = random.gauss(12, 3)
                    hour = max(7, min(21, hour))
                    ts = datetime(
                        day.year, day.month, day.day,
                        int(hour), random.randint(0, 59), random.randint(0, 59),
                    )

                    if user["is_interesting"] and random.random() < 0.25:
                        domain = random.choice(domains_suspicious)
                    else:
                        domain = random.choice(domains_normal)

                    path = "/" + "/".join(
                        fake.words(nb=random.randint(1, 3))
                    )

                    record = {
                        "id": f"HTTP-{event_id:07d}",
                        "date": ts.strftime("%m/%d/%Y %H:%M:%S"),
                        "user": user["cert_id"],
                        "pc": user["primary_pc"],
                        "url": f"https://{domain}{path}",
                        "content_type": random.choice(content_types),
                        "bytes_transferred": random.randint(500, 5000000),
                    }
                    f.write(json.dumps(record) + "\n")
                    event_id += 1
                    row_count += 1

                if row_count >= config.SECURITY_HTTP_TARGET:
                    break
            if row_count >= config.SECURITY_HTTP_TARGET:
                break

    print(f"  Written {row_count} rows to {output_path}")


def generate_email_activity(users):
    """Generate email send/receive records → Parquet (CERT schema).

    Columns: id, date, user, pc, to_addresses, cc_addresses, bcc_addresses,
             from_address, size_bytes, has_attachments, attachment_count
    """
    print("Generating email_activity.parquet...")

    output_path = config.SECURITY_DIR / "email_activity.parquet"
    start = date.fromisoformat(config.SECURITY_START)
    end = date.fromisoformat(config.SECURITY_END)

    rows = []
    event_id = 1
    user_emails = {u["cert_id"]: u["email"] for u in users}
    all_emails = list(user_emails.values())
    external_domains = [
        "gmail.com", "yahoo.com", "outlook.com", "partner-corp.com",
        "vendor-inc.com", "consulting-llc.com",
    ]

    for day in _workdays_in_range(start, end):
        active_users = [u for u in users if _active_at(u, day)]

        for user in active_users:
            n_emails = random.randint(2, 12)
            if user["is_interesting"] and random.random() < 0.3:
                n_emails += random.randint(5, 15)

            for _ in range(n_emails):
                hour = random.gauss(11, 3)
                hour = max(7, min(20, hour))
                ts = datetime(
                    day.year, day.month, day.day,
                    int(hour), random.randint(0, 59), random.randint(0, 59),
                )

                # To: 1-5 recipients, mix of internal and external
                n_to = random.randint(1, 5)
                to_addrs = []
                for _ in range(n_to):
                    if random.random() < 0.7:
                        to_addrs.append(random.choice(all_emails))
                    else:
                        to_addrs.append(
                            f"{fake.user_name()}@{random.choice(external_domains)}"
                        )

                # CC: 0-3 recipients
                n_cc = random.choices([0, 1, 2, 3], weights=[60, 25, 10, 5])[0]
                cc_addrs = [random.choice(all_emails) for _ in range(n_cc)]

                # BCC: rare, more common for interesting users
                n_bcc = 0
                if user["is_interesting"] and random.random() < 0.15:
                    n_bcc = random.randint(1, 2)
                bcc_addrs = [
                    f"{fake.user_name()}@{random.choice(external_domains)}"
                    for _ in range(n_bcc)
                ]

                has_attach = random.random() < 0.2
                if user["is_interesting"]:
                    has_attach = random.random() < 0.4
                attach_count = random.randint(1, 5) if has_attach else 0

                size = random.randint(1000, 50000)
                if has_attach:
                    size += random.randint(50000, 5000000)

                rows.append({
                    "id": f"EML-{event_id:07d}",
                    "date": ts.strftime("%m/%d/%Y %H:%M:%S"),
                    "user": user["cert_id"],
                    "pc": user["primary_pc"],
                    "to_addresses": ";".join(to_addrs),
                    "cc_addresses": ";".join(cc_addrs),
                    "bcc_addresses": ";".join(bcc_addrs),
                    "from_address": user["email"],
                    "size_bytes": size,
                    "has_attachments": has_attach,
                    "attachment_count": attach_count,
                })
                event_id += 1

            if len(rows) >= config.SECURITY_EMAIL_TARGET:
                break
        if len(rows) >= config.SECURITY_EMAIL_TARGET:
            break

    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_path)
    print(f"  Written {len(df)} rows to {output_path}")


# ---------------------------------------------------------------------------
# Communications Domain
# ---------------------------------------------------------------------------

def _call_volume_weight(dt):
    """Return a multiplier for call volume based on date (pandemic effect)."""
    # Pre-pandemic baseline
    if dt < date(2020, 3, 1):
        return 1.0
    # Pandemic surge (March-June 2020)
    if dt < date(2020, 7, 1):
        return 3.5
    # Stabilized elevated (2020 H2)
    if dt < date(2021, 1, 1):
        return 2.8
    # New normal (2021+)
    if dt < date(2022, 1, 1):
        return 2.5
    # Slight decline as hybrid settles
    return 2.2


def generate_teams_calls(users):
    """Generate MS Teams call logs 2018-2021 → CSV.

    Columns: call_id, call_date, organizer_email, duration_minutes,
             participant_count, call_type, department
    """
    print("Generating teams_calls_2018_2021.csv...")

    output_path = config.COMMS_DIR / "teams_calls_2018_2021.csv"
    start = date.fromisoformat(config.TEAMS_START)
    end = date.fromisoformat(config.TEAMS_END)

    call_types = ["audio", "video", "screen_share"]
    call_type_weights = [30, 50, 20]

    rows = []
    call_id = 1

    for day in _workdays_in_range(start, end):
        weight = _call_volume_weight(day)
        active_users = [u for u in users if _active_at(u, day)]
        if not active_users:
            continue

        # Number of calls this day scales with weight and user count
        n_calls = int(random.gauss(len(active_users) * 0.15 * weight, 3))
        n_calls = max(0, n_calls)

        for _ in range(n_calls):
            organizer = random.choice(active_users)
            hour = random.gauss(13, 2.5)
            hour = max(8, min(18, hour))
            ts = datetime(
                day.year, day.month, day.day,
                int(hour), random.randint(0, 59), 0,
            )

            duration = max(5, int(random.gauss(35, 20)))
            participants = random.choices(
                range(2, 25), weights=[30, 25, 15, 10, 5, 3, 3, 2, 2, 1,
                                       1, 1, 1, 0, 0, 0, 0, 0, 0, 0,
                                       0, 0, 0]
            )[0]
            call_type = random.choices(call_types, weights=call_type_weights)[0]

            rows.append({
                "call_id": f"TEAMS-{call_id:06d}",
                "call_date": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "organizer_email": organizer["email"],
                "duration_minutes": duration,
                "participant_count": participants,
                "call_type": call_type,
                "department": organizer["department"],
            })
            call_id += 1

        if len(rows) >= config.TEAMS_TARGET:
            break

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"  Written {len(df)} rows to {output_path}")


def generate_zoom_meetings(users):
    """Generate Zoom meeting logs 2020-2024 → JSON array.

    Fields: meeting_id, meeting_start (ISO 8601), host (email),
            length_minutes, attendees (array of emails), meeting_type,
            recording_available, org_unit
    """
    print("Generating zoom_meetings_2020_2024.json...")

    output_path = config.COMMS_DIR / "zoom_meetings_2020_2024.json"
    start = date.fromisoformat(config.ZOOM_START)
    end = date.fromisoformat(config.ZOOM_END)

    meeting_types = ["instant", "scheduled", "recurring"]
    meeting_type_weights = [20, 55, 25]

    meetings = []
    meeting_id = 1

    for day in _workdays_in_range(start, end):
        weight = _call_volume_weight(day)
        active_users = [u for u in users if _active_at(u, day)]
        if not active_users:
            continue

        n_meetings = int(random.gauss(len(active_users) * 0.18 * weight, 4))
        n_meetings = max(0, n_meetings)

        for _ in range(n_meetings):
            host = random.choice(active_users)
            hour = random.gauss(13, 2.5)
            hour = max(8, min(18, hour))
            ts = datetime(
                day.year, day.month, day.day,
                int(hour), random.randint(0, 59), 0,
            )

            length = max(5, int(random.gauss(40, 20)))
            n_attendees = random.choices(
                range(2, 30),
                weights=[25, 20, 15, 10, 8, 5, 4, 3, 2, 2,
                         1, 1, 1, 1, 0, 0, 0, 0, 0, 0,
                         0, 0, 0, 0, 0, 0, 0, 0],
            )[0]

            attendee_pool = [u for u in active_users if u != host]
            if len(attendee_pool) >= n_attendees:
                attendees = random.sample(attendee_pool, n_attendees)
            else:
                attendees = attendee_pool
            attendee_emails = [host["email"]] + [a["email"] for a in attendees]

            mtype = random.choices(meeting_types, weights=meeting_type_weights)[0]

            meetings.append({
                "meeting_id": f"ZM-{meeting_id:07d}",
                "meeting_start": ts.isoformat(),
                "host": host["email"],
                "length_minutes": length,
                "attendees": attendee_emails,
                "meeting_type": mtype,
                "recording_available": random.random() < 0.3,
                "org_unit": host["department"],
            })
            meeting_id += 1

        if len(meetings) >= config.ZOOM_TARGET:
            break

    with open(output_path, "w") as f:
        json.dump(meetings, f, indent=2)
    print(f"  Written {len(meetings)} records to {output_path}")


# ---------------------------------------------------------------------------
# HR Domain
# ---------------------------------------------------------------------------

def generate_legacy_hris(users):
    """Generate legacy HRIS records 2017-2021 → CSV.

    Columns: employee_id, name, department, job_role, hire_date,
             termination_date, salary, performance_rating (1-5),
             years_at_company, overtime_flag, snapshot_date
    """
    print("Generating legacy_hris_2017_2021.csv...")

    output_path = config.HR_DIR / "legacy_hris_2017_2021.csv"

    rows = []
    for year in range(2017, 2022):
        snapshot_date = date(year, 12, 31)

        for user in users:
            hire = date.fromisoformat(user["hire_date"])
            if hire > snapshot_date:
                continue
            if user["termination_date"]:
                term = date.fromisoformat(user["termination_date"])
                if term < date(year, 1, 1):
                    continue

            years = (snapshot_date - hire).days / 365.25
            salary = user["base_salary"] + int(years * random.randint(2000, 5000))

            # Performance rating: 1-5 integer scale
            base_perf = random.gauss(3.5, 0.8)
            if user["is_interesting"]:
                # Interesting users trend downward over time
                base_perf -= years * 0.15
            perf = max(1, min(5, round(base_perf)))

            overtime = random.random() < 0.2
            if user["is_interesting"]:
                overtime = random.random() < 0.5

            rows.append({
                "employee_id": user["legacy_emp_id"],
                "name": user["name"],
                "department": user["department"],
                "job_role": user["job_title"],
                "hire_date": user["hire_date"],
                "termination_date": user["termination_date"] or "",
                "salary": salary,
                "performance_rating": perf,
                "years_at_company": round(years, 1),
                "overtime_flag": "Y" if overtime else "N",
                "snapshot_date": snapshot_date.isoformat(),
            })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"  Written {len(df)} rows to {output_path}")


def generate_modern_hcm(users):
    """Generate modern HCM platform records 2021-2024 → JSON array.

    Fields: worker_id, full_name, business_unit, position_title,
            start_date (ISO 8601), end_date, base_compensation,
            performance_score (0.0-5.0), engagement_index (0-100),
            skills (array), manager_worker_id, learning_completions,
            effective_date
    """
    print("Generating modern_hcm_2021_2024.json...")

    output_path = config.HR_DIR / "modern_hcm_2021_2024.json"

    records = []
    # Quarterly snapshots from 2021-Q3 through 2024-Q4
    quarters = []
    for year in range(2021, 2025):
        start_q = 3 if year == 2021 else 1
        for q in range(start_q, 5):
            month = (q - 1) * 3 + 3  # End of quarter: Mar, Jun, Sep, Dec
            quarters.append(date(year, month, 28))

    for snapshot in quarters:
        for user in users:
            hire = date.fromisoformat(user["hire_date"])
            if hire > snapshot:
                continue
            if user["termination_date"]:
                term = date.fromisoformat(user["termination_date"])
                if term < date(snapshot.year, snapshot.month - 2, 1):
                    continue

            years = (snapshot - hire).days / 365.25
            compensation = user["base_salary"] + int(years * random.randint(2500, 6000))

            # Performance score: 0.0-5.0 float scale
            base_perf = random.gauss(3.6, 0.7)
            if user["is_interesting"]:
                base_perf -= years * 0.12
            perf_score = round(max(0.0, min(5.0, base_perf)), 2)

            # Engagement index: 0-100
            engagement = int(random.gauss(72, 15))
            if user["is_interesting"]:
                engagement -= 15
            engagement = max(0, min(100, engagement))

            learning = random.randint(0, 8)

            manager_id = f"WKR-{user['manager_num']:04d}"

            records.append({
                "worker_id": user["modern_worker_id"],
                "full_name": user["name"],
                "business_unit": user["department"],
                "position_title": user["job_title"],
                "start_date": user["hire_date"],
                "end_date": user["termination_date"],
                "base_compensation": compensation,
                "performance_score": perf_score,
                "engagement_index": engagement,
                "skills": user["skills"],
                "manager_worker_id": manager_id,
                "learning_completions": learning,
                "effective_date": snapshot.isoformat(),
            })

    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"  Written {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# Project Management Domain
# ---------------------------------------------------------------------------

PROJECTS = [
    "ENG", "PLATFORM", "INFRA", "DATA", "MOBILE",
    "WEB", "SEC", "DEVOPS", "QA", "DOCS",
]

TICKET_LABELS = [
    "bug", "feature", "improvement", "task", "tech-debt",
    "security", "performance", "ux", "documentation", "infrastructure",
]

COMPONENTS = [
    "api", "frontend", "backend", "database", "auth",
    "notifications", "search", "analytics", "billing", "admin",
]


def generate_project_tickets(users):
    """Generate Jira-style project tickets → Parquet.

    Columns: ticket_key, summary, description, status, priority,
             assignee_email, reporter_email, project, sprint,
             created_date, resolved_date, story_points, labels, components
    """
    print("Generating project_tickets.parquet...")

    output_path = config.PROJECTS_DIR / "project_tickets.parquet"
    start = date.fromisoformat(config.PM_START)
    end = date.fromisoformat(config.PM_END)

    statuses = ["Open", "In Progress", "Done", "Closed"]
    priorities = ["Critical", "High", "Medium", "Low"]
    priority_weights = [5, 15, 50, 30]

    ticket_counters = {p: 0 for p in PROJECTS}
    rows = []

    summaries = [
        "Fix {component} error handling for edge cases",
        "Add pagination to {component} list endpoint",
        "Update {component} unit tests for new schema",
        "Refactor {component} to use async patterns",
        "Investigate {component} performance degradation",
        "Add logging to {component} service",
        "Migrate {component} to new database schema",
        "Implement caching for {component} queries",
        "Fix {component} authentication bypass",
        "Add monitoring alerts for {component}",
        "Update {component} documentation",
        "Optimize {component} database queries",
        "Add rate limiting to {component} API",
        "Fix {component} memory leak in production",
        "Implement {component} retry logic",
    ]

    eng_users = [u for u in users if u["department"] in (
        "Engineering", "IT", "Operations"
    )]

    for day in _workdays_in_range(start, end):
        active_eng = [u for u in eng_users if _active_at(u, day)]
        if not active_eng:
            continue

        # 2-6 tickets created per day
        n_tickets = random.randint(2, 6)
        for _ in range(n_tickets):
            project = random.choice(PROJECTS)
            ticket_counters[project] += 1
            ticket_key = f"{project}-{ticket_counters[project]}"

            reporter = random.choice(active_eng)
            assignee = random.choice(active_eng)
            component = random.choice(COMPONENTS)
            summary = random.choice(summaries).format(component=component)

            priority = random.choices(priorities, weights=priority_weights)[0]
            story_pts = random.choices(
                [1, 2, 3, 5, 8, 13],
                weights=[15, 25, 30, 20, 8, 2],
            )[0]

            # Sprint: 2-week sprints
            sprint_num = ((day - start).days // 14) + 1
            sprint = f"Sprint {sprint_num}"

            # Resolution: older tickets more likely to be done
            age_days = (end - day).days
            if age_days > 90:
                status = random.choices(
                    statuses, weights=[5, 5, 50, 40]
                )[0]
            elif age_days > 30:
                status = random.choices(
                    statuses, weights=[10, 20, 40, 30]
                )[0]
            else:
                status = random.choices(
                    statuses, weights=[30, 30, 25, 15]
                )[0]

            resolved_date = None
            if status in ("Done", "Closed"):
                resolve_days = random.randint(1, min(60, age_days or 1))
                resolved_date = (day + timedelta(days=resolve_days)).isoformat()

            n_labels = random.randint(1, 3)
            labels = random.sample(TICKET_LABELS, k=n_labels)
            n_components = random.randint(1, 2)
            comps = random.sample(COMPONENTS, k=n_components)

            rows.append({
                "ticket_key": ticket_key,
                "summary": summary,
                "description": f"Detailed description for {ticket_key}: {summary}",
                "status": status,
                "priority": priority,
                "assignee_email": assignee["email"],
                "reporter_email": reporter["email"],
                "project": project,
                "sprint": sprint,
                "created_date": day.isoformat(),
                "resolved_date": resolved_date or "",
                "story_points": story_pts,
                "labels": ",".join(labels),
                "components": ",".join(comps),
            })

        if len(rows) >= config.PM_TARGET:
            break

    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_path)
    print(f"  Written {len(df)} rows to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def save_user_mapping(users):
    """Save the user mapping for internal reference (not part of the 'lake')."""
    mapping_path = config.METADATA_DIR / "user_mapping.json"
    with open(mapping_path, "w") as f:
        json.dump(users, f, indent=2)
    print(f"  Saved user mapping ({len(users)} users) to {mapping_path}")


def main():
    print("=" * 60)
    print("Data Lake Demo: Data Generation")
    print("=" * 60)

    # Ensure directories exist
    for d in [config.SECURITY_DIR, config.COMMS_DIR, config.HR_DIR,
              config.PROJECTS_DIR, config.METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Generate user universe
    print("\n--- User Universe ---")
    users = generate_user_universe()
    save_user_mapping(users)

    # Generate all data sources
    print("\n--- Security Domain (CERT-schema) ---")
    generate_logon_events(users)
    generate_http_access(users)
    generate_email_activity(users)

    print("\n--- Communications Domain ---")
    generate_teams_calls(users)
    generate_zoom_meetings(users)

    print("\n--- HR Domain ---")
    generate_legacy_hris(users)
    generate_modern_hcm(users)

    print("\n--- Project Management Domain ---")
    generate_project_tickets(users)

    print("\n" + "=" * 60)
    print("Data generation complete!")
    print("=" * 60)

    # Summary
    print("\nGenerated files:")
    for dirpath in [config.SECURITY_DIR, config.COMMS_DIR, config.HR_DIR,
                    config.PROJECTS_DIR]:
        for f in sorted(dirpath.iterdir()):
            size_kb = f.stat().st_size / 1024
            if size_kb > 1024:
                print(f"  {f.relative_to(config.DATA_DIR)}: {size_kb/1024:.1f} MB")
            else:
                print(f"  {f.relative_to(config.DATA_DIR)}: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
